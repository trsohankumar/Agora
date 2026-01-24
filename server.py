import argparse
import uuid
import random
import time
import threading

from loguru import logger
from enum import Enum
from collections import defaultdict
from typing import Dict

from auction.auction_room import AuctionRoom, AuctionRoomStatus, RoundState
from unicast.unicast import Unicast
from broadcast.broadcast import Broadcast
from message.message_handler import MessageHandler
from message.outgoing_message import OutgoingMessageHandler
from message.message_types import ServerMessageType, ClientMessageType
from message.message import Message
from node_list import NodeList, Node
from log.log_entries import LogEntries
from utils.common import DisconnectedError, RequestTimeoutError, get_ip_port
from utils.pending_requests import PendingRequest


class ServerState(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


class Server:
    def __init__(self, server_name, port):
        ip, _ = get_ip_port()

        self.server_node = Node(
            _id=str(uuid.uuid5(uuid.NAMESPACE_DNS, server_name)), ip=ip, port=port
        )
        self.state = ServerState.FOLLOWER
        self.peer_list = NodeList()
        self.client_list = NodeList()  # will need to be removed
        logger.info(
            f"Server starting with id: {self.server_node._id}, ip: {self.server_node.ip}, port: {self.server_node.port}"
        )

        # setup message resolver for the server
        self.message_handler = MessageHandler()

        self.discovery_complete = False
        self.register_callbacks()

        # setup unicast communication for the server
        self.unicast = Unicast(node=self.server_node)
        self.outgoing_handler = OutgoingMessageHandler(self.unicast)
        # setup broadcast communication for the server
        self.broadcast = Broadcast(node=self.server_node)

        self.term = 0
        self.voted_for = None
        self.log = []

        self.commit_index = 0
        self.last_applied = -1

        self.next_index = {}
        self.match_index = {}

        self.state_lock = threading.Lock()
        self.heartbeat_interval = 0.150  # Match client's heartbeat interval (100ms)
        # Client sends every 0.1s, so timeout should be longer (e.g., 5-6 missed heartbeats)
        self.client_heartbeat_timeout = 1.0  # Increased to match new interval
        self.monitor_client_list_thread = threading.Thread(
            target=self.remove_timeout_client_from_list, daemon=True
        )

        self.follower_heartbeat_thread = threading.Thread(
            target=self.send_heartbeat_to_peers, daemon=True
        )

        self.monitor_client_list_thread.start()
        self.follower_heartbeat_thread.start()

        self.election_timeout = self._get_random_election_timeout()
        self.last_heartbeat_time = time.time()
        self.votes_received = set()

        self.auction_list = dict()
        self.active_rounds = dict()
        self.round_lock = threading.Lock()
        # request/resp tracking
        self.pending_requests: dict[str, PendingRequest] = {}
        self.pending_lock = threading.Lock()

    def _send_request(self, msg_type, rec_node, data={}, timeout: float = 10.0):
        pending = PendingRequest()

        with self.pending_lock:
            self.pending_requests[msg_type] = pending

        try:
            self._send_message(
                Message(
                    message_type=msg_type,
                    sender=self.server_node,
                    receiver=rec_node,
                    data=data,
                )
            )
            pending.event.wait(timeout=timeout)

            if pending.disconnected:
                raise DisconnectedError("Not connected to server")
            if pending.response is None:
                raise RequestTimeoutError(f"Request {msg_type} timed out")

            return pending.response
        finally:
            with self.pending_lock:
                self.pending_requests.pop(msg_type, None)

    def _complete_request(self, request_type, response):
        with self.pending_lock:
            pending = self.pending_requests.get(request_type)

        if pending:
            pending.response = response
            pending.event.set()

    def _get_random_election_timeout(self):
        return random.uniform(1, 2.1)

    def handle_disc_resp(self, msg):
        """
        This method is responsible to add new peers after discovery
        """
        if msg.sender._id == self.server_node._id:
            return

        logger.info(f"Handling message: {msg}")
        if self.peer_list.get_node(msg.sender._id) is None:
            self.peer_list.add_node(msg.sender._id, msg.sender)

            # Initialize next_index and match_index for new peer
        with self.state_lock:
            if self.state == ServerState.LEADER:
                self.next_index[msg.sender._id] = len(self.log)
                self.match_index[msg.sender._id] = -1

    def handle_disc_req(self, msg):
        """
        This method is responsible to handle discovery requests from other servers
        """
        sender_id = msg.sender._id
        if sender_id == self.server_node._id:
            return

        logger.info(f"Handling message: {msg}")

        if self.peer_list.get_node(sender_id) is None:
            self.peer_list.add_node(sender_id, msg.sender)

        # Initialize next_index and match_index for new peer
        with self.state_lock:
            if self.state == ServerState.LEADER:
                self.next_index[sender_id] = len(self.log)
                self.match_index[sender_id] = -1

        self._send_message(
            Message(
                message_type=ServerMessageType.RES_DISC.value,
                sender=self.server_node,
                receiver=msg.sender,
            )
        )

    def register_callbacks(self):
        """
        Method to register functions for handling messages
        """

        # Server discovery messages
        self.message_handler.register_handler(
            ServerMessageType.REQ_DISC.value, self.handle_disc_req
        )
        self.message_handler.register_handler(
            ServerMessageType.RES_DISC.value, self.handle_disc_resp
        )

        # Server raft message
        self.message_handler.register_handler(
            ServerMessageType.REQ_VOTE.value, self.handle_request_vote
        )
        self.message_handler.register_handler(
            ServerMessageType.RES_VOTE.value, self.handle_vote_resp
        )
        self.message_handler.register_handler(
            ServerMessageType.REQ_APPEND_ENTRIES.value, self.handle_append_entries
        )
        self.message_handler.register_handler(
            ServerMessageType.RES_APPEND_ENTRIES.value, self.handle_append_entries_resp
        )

        # Client messages sent to server
        self.message_handler.register_handler(
            ClientMessageType.REQ_DISC.value, self.append_log
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_JOIN_AUCTION.value, self.append_log
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_CREATE_AUCTION.value, self.append_log
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_START_AUCTION.value, self.append_log
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_MAKE_BID.value, self.append_log
        )
        self.message_handler.register_handler(
            ClientMessageType.CLIENT_HEART_BEAT.value, self.handle_client_heartbeat
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value,
            self.handle_retrieve_auction_list_req,
        )

    def append_log(self, msg):
        """
        This method appends data to the log

        :param message: The message that is to be appended to the log
        """
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state != ServerState.LEADER:
                return
            self.log.append(LogEntries(self.term, msg))

    def remove_timeout_client_from_list(self):
        """
        This function removes a client that has timeout from the client list
        """
        clients_pending_removal = set()

        # Track clients we've already queued for removal
        while True:
            # Check less frequently than the timeout period
            time.sleep(self.heartbeat_interval)

            with self.state_lock:
                if self.state != ServerState.LEADER:
                    continue
                client_list = self.client_list.get_all_node().copy()

            current_time = time.time()

            for client_id, client_info in client_list.items():
                last_heartbeat = client_info.last_heartbeat
                if current_time - last_heartbeat > self.client_heartbeat_timeout:
                    # Only log removal once per client
                    if client_id not in clients_pending_removal:
                        logger.warning(
                            f"Client {client_id} timed out. Last heartbeat: {current_time - last_heartbeat:.2f}s ago"
                        )
                        clients_pending_removal.add(client_id)
                        message = Message(
                            sender=client_info,
                            message_type=ClientMessageType.REQ_REMOVE_CLIENT.value,
                        )
                        with self.state_lock:
                            self.log.append(LogEntries(self.term, message))

    def handle_client_heartbeat(self, message):
        """
        Handle heartbeat from client (unidirectional - no response sent).
        Updates last_heartbeat timestamp for known clients.
        """
        with self.state_lock:
            if self.state != ServerState.LEADER:
                return

            client = self.client_list.get_node(message.sender._id)
            if client is not None:
                # Update heartbeat timestamp for known clients
                self.client_list.add_node(message.sender._id, message.sender)

    def start_server(self):
        """
        method responsible to initialize the server
        """
        self.message_handler.start_message_handler()
        self.outgoing_handler.start_message_handler()
        self.unicast.start_unicast_listen(self.message_handler)
        self.broadcast.start_broadcast_listen(self.message_handler)

        for _ in range(5):
            self.broadcast.send_broadcast(ServerMessageType.REQ_DISC.value)
            time.sleep(1)

        self.discovery_complete = True
        logger.info(
            f"Discovery complete: No of peers found{len(self.peer_list.get_all_node())}"
        )

        with self.state_lock:
            self.last_heartbeat_time = time.time()

        self.run_server_loop()

    def run_server_loop(self):
        """
        mesthod responsible for server state transitions
        """
        while True:
            with self.state_lock:
                current_state = self.state

                time_since_heartbeat = time.time() - self.last_heartbeat_time

            if current_state == ServerState.FOLLOWER:
                if (
                    self.discovery_complete
                    and time_since_heartbeat > self.election_timeout
                ):
                    logger.info(
                        f"Time since last heartbeat: {time_since_heartbeat} greater than election timeout: {self.election_timeout}, election timeout occurred."
                    )
                    self.transiton_to_candidate()

            elif current_state == ServerState.CANDIDATE:
                if time_since_heartbeat > self.election_timeout:
                    logger.info("Candidate timeout occurred. Starting new election")
                    self.transiton_to_candidate()

            elif current_state == ServerState.LEADER:
                # self.send_heartbeat_to_peers()
                self.send_heartbeat_to_clients()

            self._commit_log()
            time.sleep(self.heartbeat_interval)

    def _send_leader_message(self, msg):
        if self.state == ServerState.LEADER:
            self.outgoing_handler.add_message(msg)

    def _send_message(self, msg):
        self.outgoing_handler.add_message(msg)

    def _commit_log(self):
        # Process one log entry per iteration to avoid holding lock too long
        with self.state_lock:
            if (self.commit_index > self.last_applied) and (
                self.last_applied + 1 < len(self.log)
            ):

                # apply the logs to state machine
                self.last_applied += 1
                entry = self.log[self.last_applied]

                logger.info(f"Current Log State - Total Entries: {len(self.log)}")
                for idx, log_entry in enumerate(self.log):
                    status = "[APPLIED]" if idx <= self.last_applied else "[PENDING]"
                    cmd = log_entry.command
                    logger.info(
                        f"  [{idx:3d}] {status:10} | Term: {log_entry.term} | "
                        f"Type: {cmd.message_type} | "
                        f"Client: {cmd.sender._id if cmd.sender else 'N/A'} | "
                    )
                logger.info(f"Now applying entry {self.last_applied}")

                message = entry.command
                match message.message_type:
                    case ClientMessageType.REQ_DISC.value:
                        node = message.sender.copy()
                        node.last_heartbeat = time.time()
                        self.client_list.add_node(message.sender._id, node)

                        if self.state == ServerState.LEADER:
                            logger.info(
                                f"Sending RES_DISC to client {ClientMessageType.RES_DISC.value} "
                                f"{message.sender._id} {message.sender.ip} {message.sender.port}"
                            )

                            msg = Message(
                                message_type=ClientMessageType.RES_DISC.value,
                                sender=self.server_node,
                                receiver=message.sender,
                            )
                            self._send_leader_message(msg)
                    case ClientMessageType.REQ_REMOVE_CLIENT.value:
                        self.client_list.remove_node(message.sender._id)
                        logger.info(
                            f"Removed client {message.sender._id} from client list"
                        )

                        for auction_id, auction in self.auction_list.items():
                            if auction.get_auctioneer()._id == message.sender._id:
                                logger.info(f"auctioneer no longer alive")
                            else:
                                auction.bidders.remove_node(message.sender._id)

                    case ClientMessageType.REQ_JOIN_AUCTION.value:
                        auction_id = message.data.get("auction_id")
                        logger.info(f"The auction id is {auction_id}")
                        status = False
                        auction = self.auction_list.get(auction_id)
                        if (
                            auction is not None
                            and auction.status == AuctionRoomStatus.AWAITING_PEEERS
                        ):
                            auction.add_participant(message.sender._id, message.sender)
                            status = True

                        self._send_leader_message(
                            Message(
                                message_type=ClientMessageType.RES_JOIN_AUCTION.value,
                                receiver=message.sender,
                                sender=self.server_node,
                                data={"status": status},
                            )
                        )

                        if (
                            auction.get_bidder_count()
                            >= auction.get_min_number_bidders()
                        ):
                            # Send message to auctioneer and all bidders that auction room is ready
                            room_enabled_msg_data = {
                                "message": "Auction room ready",
                                "status": "Success",
                            }

                            self._send_leader_message(
                                Message(
                                    message_type=ClientMessageType.RES_AUCTION_ROOM_ENABLED.value,
                                    sender=self.server_node,
                                    receiver=auction.get_auctioneer(),
                                    data=room_enabled_msg_data,
                                )
                            )

                            # Send to all bidders
                            for _, bidder in auction.bidders.get_all_node().items():
                                self._send_leader_message(
                                    Message(
                                        message_type=ClientMessageType.RES_AUCTION_ROOM_ENABLED.value,
                                        sender=self.server_node,
                                        receiver=bidder,
                                        data=room_enabled_msg_data,
                                    )
                                )

                    case ClientMessageType.REQ_CREATE_AUCTION.value:
                        auction_room = AuctionRoom(
                            auctioneer=message.sender,
                            rounds=message.data.get("rounds"),
                            item=message.data.get("item"),
                            min_bid=message.data.get("min_bid"),
                            min_bidders=message.data.get("min_bidders"),
                        )
                        self.auction_list[auction_room.get_id()] = auction_room
                        logger.debug(f"{auction_room.to_json()}")

                        data = {
                            "auction_id": auction_room.get_id(),
                            "msg": f"Auction room created, awaiting bidders to join {auction_room.get_min_number_bidders() - auction_room.get_bidder_count()}",
                        }

                        self._send_leader_message(
                            Message(
                                message_type=ClientMessageType.RES_CREATE_AUCTION.value,
                                sender=self.server_node,
                                receiver=message.sender,
                                data=data,
                            )
                        )
                    case ClientMessageType.REQ_START_AUCTION.value:
                        auction_room = self.auction_list.get(
                            message.data.get("auction_id")
                        )
                        if auction_room is not None:
                            threading.Thread(
                                target=self.auction_process,
                                args=(auction_room,),
                                daemon=True,
                            ).start()
                            self._send_leader_message(
                                Message(
                                    message_type=ClientMessageType.RES_START_AUCTION.value,
                                    sender=self.server_node,
                                    receiver=message.sender,
                                    data={
                                        "status": "Success",
                                        "message": "Auction started",
                                    },
                                )
                            )
                        else:
                            self._send_leader_message(
                                Message(
                                    message_type=ClientMessageType.RES_START_AUCTION.value,
                                    sender=self.server_node,
                                    receiver=message.sender,
                                    data={
                                        "status": "Failed",
                                        "message": "Auction not found",
                                    },
                                )
                            )
                    case ClientMessageType.RES_MAKE_BID.value:
                        self.active_rounds[message.data.get("auction_id")].add_bid(
                            message.sender._id, message.data.get("bid")
                        )
                    case _:
                        logger.info("default case")

    def transiton_to_candidate(self):
        with self.state_lock:
            self.term += 1
            self.state = ServerState.CANDIDATE
            self.voted_for = self.server_node._id
            self.votes_received = {self.server_node._id}
            self.election_timeout = (
                self._get_random_election_timeout()
            )  # should we initialize this only once ?
            self.last_heartbeat_time = time.time()

        self.send_request_vote()
        self.check_election_won()

    def send_request_vote(self):
        peers = self.peer_list.get_all_node()
        for peer_id, peer_info in peers.items():
            data = {
                "term": self.term,
                "last_log_index": len(self.log) - 1,
                "last_log_term": self.log[-1].term if len(self.log) > 0 else 0,
            }
            self._send_message(
                Message(
                    message_type=ServerMessageType.REQ_VOTE.value,
                    sender=self.server_node,
                    receiver=peer_info,
                    data=data,
                )
            )

    def check_election_won(self):
        with self.state_lock:
            if self.state != ServerState.CANDIDATE:
                return

            total_nodes = len(self.peer_list.get_all_node()) + 1
            if len(self.votes_received) > (total_nodes // 2):
                logger.info(
                    f"Server: {self.server_node._id} has won the election for term: {self.term}"
                )
                self.state = ServerState.LEADER
                peers = self.peer_list.get_all_node()
                for peer_id in peers.keys():
                    self.next_index[peer_id] = len(self.log)
                    self.match_index[peer_id] = -1

    def handle_request_vote(self, msg):
        if msg.sender._id == str(self.server_node._id):
            return
        with self.state_lock:
            grant_vote = False

            if msg.data.get("term") > self.term:
                self.term = msg.data.get("term")
                self.state = ServerState.FOLLOWER
                self.voted_for = None

            if msg.data.get("term") == self.term:
                if self.voted_for is None or self.voted_for == msg.sender._id:
                    server_last_log_term = self.log[-1].term if len(self.log) > 0 else 0
                    server_last_log_index = len(self.log) - 1

                    vote_possible = msg.data.get(
                        "last_log_term"
                    ) > server_last_log_term or (
                        msg.data.get("last_log_term") == server_last_log_term
                        and msg.data.get("last_log_index") >= server_last_log_index
                    )

                    if vote_possible:
                        grant_vote = True
                        self.voted_for = msg.sender._id
                        self.last_heartbeat_time = time.time()

            term = self.term
        data = {
            "term": term,
            "vote_granted": grant_vote,
            "voter_id": str(self.server_node._id),
        }
        self._send_message(
            Message(
                message_type=ServerMessageType.RES_VOTE.value,
                sender=self.server_node,
                receiver=msg.sender,
                data=data,
            )
        )
        logger.info(
            f"Vote {'GRANTED' if grant_vote else 'DENIED'} for {msg.sender._id} for term: {self.term}"
        )

    def handle_vote_resp(self, msg):
        if msg.sender._id == str(self.server_node._id):
            return
        with self.state_lock:
            if self.state != ServerState.CANDIDATE or msg.data.get("term") != self.term:
                return

            if msg.data.get("vote_granted"):
                self.votes_received.add(msg.data.get("voter_id"))
                logger.info(
                    f"Received vote from {msg.data.get('voter_id')}. Total: {len(self.votes_received)}"
                )

        self.check_election_won()

    def send_heartbeat_to_clients(self):
        """Send heartbeat to all connected clients (unidirectional - no response expected)"""
        with self.state_lock:
            if self.state != ServerState.LEADER:
                return
            clients = self.client_list.get_all_node().copy()

        for client_id, client_info in clients.items():
            self._send_leader_message(
                Message(
                    message_type=ClientMessageType.SERVER_HEART_BEAT.value,
                    sender=self.server_node,
                    receiver=client_info,
                )
            )

    def send_heartbeat_to_peers(self):
        """Send heartbeat/log replication to peer servers"""

        while True:
            messages = []
            with self.state_lock:
                if self.state != ServerState.LEADER:
                    time.sleep(self.heartbeat_interval)
                    continue

                peers = self.peer_list.get_all_node()
                for peer_id, peer_info in peers.items():
                    prev_log_idx = self.next_index[peer_id] - 1
                    prev_log_term = 0
                    if prev_log_idx >= 0 and prev_log_idx < len(self.log):
                        prev_log_term = self.log[prev_log_idx].term

                    max_entries_per_msg = 10
                    start_idx = self.next_index.get(peer_id)
                    end_idx = min(start_idx + max_entries_per_msg, len(self.log))
                    entries_to_send = [
                        entry.to_dict() for entry in self.log[start_idx:end_idx]
                    ]

                    data = {
                        "term": self.term,
                        "prev_log_index": prev_log_idx,
                        "prev_log_term": prev_log_term,
                        "leader_commit": self.commit_index,
                        "entries": entries_to_send,
                    }
                    messages.append(
                        Message(
                            message_type=ServerMessageType.REQ_APPEND_ENTRIES.value,
                            sender=self.server_node,
                            receiver=peer_info,
                            data=data,
                        )
                    )

            for msg in messages:
                self._send_message(msg)

            time.sleep(self.heartbeat_interval)

    def handle_append_entries(self, msg):
        if msg.sender._id == str(self.server_node._id):
            return

        with self.state_lock:
            if msg.data.get("term") > self.term:
                self.term = msg.data.get("term")
                self.state = ServerState.FOLLOWER
                self.voted_for = None

            if msg.data.get("term") < self.term:
                resp = False
            elif msg.data.get("prev_log_index") >= len(self.log):
                resp = False
            elif (
                msg.data.get("prev_log_index") >= 0
                and msg.data.get("prev_log_term")
                != self.log[msg.data.get("prev_log_index")].term
            ):
                resp = False
            else:
                try:
                    del self.log[msg.data.get("prev_log_index") + 1 :]
                except IndexError:
                    pass
                # Convert dict entries back to LogEntries objects
                for entry_dict in msg.data.get("entries", []):
                    self.log.append(LogEntries.from_dict(entry_dict))

                if msg.data.get("leader_commit") > self.commit_index:
                    self.commit_index = min(
                        msg.data.get("leader_commit"), len(self.log) - 1
                    )
                resp = True

            data = {
                "term": self.term,
                "success": resp,
            }
            self.election_timeout = self._get_random_election_timeout()
            self.last_heartbeat_time = time.time()
        self._send_message(
            Message(
                message_type=ServerMessageType.RES_APPEND_ENTRIES.value,
                sender=self.server_node,
                receiver=msg.sender,
                data=data,
            )
        )

    def handle_append_entries_resp(self, msg):
        if msg.sender._id == str(self.server_node._id):
            return

        with self.state_lock:
            if self.term < msg.data.get("term"):
                self.term = msg.data.get("term")
                self.state = ServerState.FOLLOWER
                return

            if msg.data.get("success") == False:
                self.next_index[msg.sender._id] -= 1

            if msg.data.get("success") == True and msg.data.get("term") == self.term:
                self.match_index[msg.sender._id] = self.next_index[msg.sender._id]
                self.next_index[msg.sender._id] += 1

            index_count = defaultdict(int)
            for ind in self.match_index.values():
                index_count[ind] += 1
            if len(self.log) > 0:
                index_count[len(self.log) - 1] += 1

            for key, val in index_count.items():
                if key >= 0 and key < len(self.log):
                    if (
                        key > self.commit_index
                        and val > (self.peer_list.get_len() + 1) // 2
                        and self.log[key].term == self.term
                    ):
                        self.commit_index = key

    def handle_retrieve_auction_list_req(self, message):
        auctions = []
        with self.state_lock:
            for auction in self.auction_list.values():
                if auction.status == AuctionRoomStatus.AWAITING_PEEERS:
                    auctions.append(auction.to_json())

        logger.info(f"{auctions}")
        self._send_leader_message(
            Message(
                message_type=ClientMessageType.RES_RETRIEVE_AUCTION_LIST.value,
                sender=self.server_node,
                receiver=message.sender,
                data={"available_auctions": auctions},
            )
        )

    def auction_process(self, auction_room):
        """
        responsible for the entire round based bidding process
        """
        round_num = 1
        is_final_round = False
        while round_num <= auction_room.get_rounds():
            bidders_count = set(auction_room.bidders.get_all_node().keys())
            round_state = RoundState(round_num, expected_bidders=bidders_count)
            with self.state_lock:
                self.active_rounds[auction_room.get_id()] = round_state

            bid_request_data = {
                "auction_id": auction_room.get_id(),
                "item": auction_room.item,
                "round": round_num,
                "current_highest": auction_room.min_bid,
            }

            for _, bidder in auction_room.bidders.get_all_node().items():
                self._send_leader_message(
                    Message(
                        message_type=ClientMessageType.REQ_MAKE_BID.value,
                        sender=self.server_node,
                        receiver=bidder,
                        data=bid_request_data,
                    )
                )

            # wait for all responses
            round_state.wait_for_all()

            # process bids
            highest_bidder, highest_amount = self._get_highest_bid(round_state.bids)
            auction_room.min_bid = highest_amount
            auction_room.max_bidder = highest_bidder

            is_final_round = False
            if round_num == auction_room.get_rounds():
                is_final_round = True

            # notify all clients of round result
            result_data = {
                "auction_id": auction_room.get_id(),
                "round": round_num,
                "highest_bid": highest_amount,
                "highest_bidder": highest_bidder,
                "is_final_round": is_final_round,
            }

            # Send result to all bidders
            for _, bidder in auction_room.bidders.get_all_node().items():
                self._send_leader_message(
                    Message(
                        message_type=ClientMessageType.RES_ROUND_RESULT.value,
                        sender=self.server_node,
                        receiver=bidder,
                        data=result_data,
                    )
                )

            # Send result to auctioneer
            auctioneer = auction_room.get_auctioneer()
            self._send_leader_message(
                Message(
                    message_type=ClientMessageType.RES_ROUND_RESULT.value,
                    sender=self.server_node,
                    receiver=auctioneer,
                    data=result_data,
                )
            )

            with self.round_lock:
                del self.active_rounds[auction_room.get_id()]

            round_num += 1

    def _get_highest_bid(self, bids: Dict[str, int]) -> tuple[str, int]:
        if not bids:
            return None, 0
        highest_bidder = max(bids, key=bids.get)
        return highest_bidder, bids[highest_bidder]


def parse_arguements():
    parser = argparse.ArgumentParser(
        prog="",
        description="",
    )
    parser.add_argument("-n", "--name")
    parser.add_argument("-p", "--port")
    args = parser.parse_args()
    return args.name, args.port


if __name__ == "__main__":
    name, port = parse_arguements()
    server = Server(name, port)
    server.start_server()
