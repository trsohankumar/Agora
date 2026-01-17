import uuid
import random
import time
import threading
import json

from loguru import logger
from enum import Enum
from collections import defaultdict
from typing import Dict

from auction.auction_room import AuctionRoom, AuctionRoomStatus, RoundState
from unicast.unicast import Unicast
from broadcast.broadcast import Broadcast
from message.message_handler import MessageHandler
from message.message_types import ServerMessageType, ClientMessageType
from node_list import NodeList, Node
from log.log_entries import LogEntries
from utils.common import DisconnectedError, RequestTimeoutError, get_ip_port
from utils.pending_requests import PendingRequest


class ServerState(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


class Server:
    def __init__(self):
        self.server_id = uuid.uuid4()
        self.state = ServerState.FOLLOWER
        self.server_ip, self.server_port = get_ip_port()
        self.peer_list = NodeList()
        self.client_list = NodeList()
        logger.info(
            f"Server starting with id: {self.server_id}, ip: {self.server_ip}, port: {self.server_port}"
        )

        # setup message resolver for the server
        self.message_handler = MessageHandler()
        self.discovery_complete = False
        self.register_callbacks()
        # setup unicast communication for the server
        self.unicast = Unicast(unicast_ip=self.server_ip, unicast_port=self.server_port)
        # setup broadcast communication for the server
        self.broadcast = Broadcast(self.server_ip)

        self.term = 0
        self.voted_for = None
        self.log = []

        self.commit_index = 0
        self.last_applied = -1

        self.next_index = {}
        self.match_index = {}

        self.state_lock = threading.Lock()
        self.heartbeat_interval = 0.1  # Match client's heartbeat interval (100ms)
        # Client sends every 0.1s, so timeout should be longer (e.g., 5-6 missed heartbeats)
        self.client_heartbeat_timeout = 1.0  # Increased to match new interval
        self.monitor_client_list_thread = threading.Thread(
            target=self.remove_timeout_client_from_list, daemon=True
        )
        self.monitor_client_list_thread.start()

        self.election_timeout = self._get_random_election_timeout()
        self.last_heartbeat_time = time.time()
        self.votes_received = set()

        self.auction_list = dict()
        self.active_rounds = dict()
        self.round_lock = threading.Lock()
        # request/resp tracking
        self.pending_requests: dict[str, PendingRequest] = {}
        self.pending_lock = threading.Lock()

    def _send_request(self, msg, ip, port, timeout: float = 10.0):

        request_type = msg["type"]
        pending = PendingRequest()

        with self.pending_lock:
            self.pending_requests[request_type] = pending

        try:
            self.unicast.send_message(msg, ip, port)
            pending.event.wait(timeout=timeout)

            if pending.disconnected:
                raise DisconnectedError("Not connected to server")
            if pending.response is None:
                raise RequestTimeoutError(f"Request {request_type} timed out")

            return pending.response
        finally:
            with self.pending_lock:
                self.pending_requests.pop(request_type, None)

    def _complete_request(self, request_type, response):
        with self.pending_lock:
            pending = self.pending_requests.get(request_type)

        if pending:
            pending.response = response
            pending.event.set()

    def _get_random_election_timeout(self):
        return random.uniform(0.15, 0.30)

    def handle_disc_resp(self, msg):

        if msg["id"] == str(self.server_id):
            return

        logger.info(f"Handling message: {msg}")
        if self.peer_list.get_node(msg["id"]) == None:
            self.peer_list.add_node(msg["id"], {"ip": msg["ip"], "port": msg["port"]})
            # Initialize next_index and match_index for new peer
            with self.state_lock:
                if self.state == ServerState.LEADER:
                    self.next_index[msg["id"]] = len(self.log)
                    self.match_index[msg["id"]] = -1

    def handle_disc_req(self, msg):
        if msg["id"] == str(self.server_id):
            return
        logger.info(f"Handling message: {msg}")
        if self.peer_list.get_node(msg["id"]) == None:
            self.peer_list.add_node(msg["id"], {"ip": msg["ip"], "port": msg["port"]})
            # Initialize next_index and match_index for new peer
            with self.state_lock:
                if self.state == ServerState.LEADER:
                    self.next_index[msg["id"]] = len(self.log)
                    self.match_index[msg["id"]] = -1
            return_messge = {
                "type": ServerMessageType.RES_DISC.value,
                "ip": self.server_ip,
                "port": self.server_port,
                "id": str(self.server_id),
            }
            self.unicast.send_message(return_messge, msg["ip"], msg["port"])

    def register_callbacks(self):
        self.message_handler.register_handler(
            ServerMessageType.REQ_DISC.value, self.handle_disc_req
        )
        self.message_handler.register_handler(
            ServerMessageType.RES_DISC.value, self.handle_disc_resp
        )
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
            ServerMessageType.RES_APPEND_ENTRIES.value, self.handle_append_entries_resp
        )
        self.message_handler.register_handler(
            ClientMessageType.CLIENT_HEART_BEAT.value, self.handle_client_heartbeat
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value,
            self.handle_retrieve_auction_list_req,
        )

    def append_log(self, message):
        if message["id"] == str(self.server_id):
            return

        with self.state_lock:
            if self.state != ServerState.LEADER:
                return
            self.log.append(LogEntries(self.term, message))

    def remove_timeout_client_from_list(self):
        clients_pending_removal = (
            set()
        )  # Track clients we've already queued for removal
        while True:
            # Check less frequently than the timeout period
            time.sleep(self.heartbeat_interval)
            with self.state_lock:
                if self.state != ServerState.LEADER:
                    continue
                client_list = self.client_list.get_all_node().copy()
                current_time = time.time()

            # Check each client outside the lock to avoid holding it too long
            for client_id, client_info in client_list.items():
                last_heartbeat = client_info.get("last_heartbeat", 0)
                if current_time - last_heartbeat > self.client_heartbeat_timeout:
                    # Only log removal once per client
                    if client_id not in clients_pending_removal:
                        logger.warning(
                            f"Client {client_id} timed out. Last heartbeat: {current_time - last_heartbeat:.2f}s ago"
                        )
                        clients_pending_removal.add(client_id)
                        with self.state_lock:
                            self.log.append(
                                LogEntries(
                                    self.term,
                                    {
                                        "type": ClientMessageType.REQ_REMOVE_CLIENT.value,
                                        "ip": client_info.get("ip"),
                                        "id": client_id,
                                        "port": client_info.get("port"),
                                    },
                                )
                            )

    def handle_client_heartbeat(self, message):
        """
        Handle heartbeat from client (unidirectional - no response sent).
        Updates last_heartbeat timestamp for known clients.
        """
        with self.state_lock:
            if self.state != ServerState.LEADER:
                return

            client = self.client_list.get_node(message.get("id"))
            if client is not None:
                # Update heartbeat timestamp for known clients
                self.client_list.add_node(
                    message.get("id"),
                    {
                        "ip": message.get("ip"),
                        "port": message.get("port"),
                        "last_heartbeat": time.time(),
                    },
                )

    def start_server(self):
        self.message_handler.start_message_handler()
        self.unicast.start_unicast_listen(self.message_handler)
        self.broadcast.start_broadcast_listen(self.message_handler)
        broadcast_message = {
            "type": ServerMessageType.REQ_DISC.value,
            "id": str(self.server_id),
            "ip": self.server_ip,
            "port": self.server_port,
        }
        for _ in range(5):
            self.broadcast.send_broadcast(broadcast_message)
            time.sleep(1)

        self.discovery_complete = True
        logger.info(
            f"Discovery complete: No of peers found{len(self.peer_list.get_all_node())}"
        )

        self.last_heartbeat_time = time.time()

        self.run_server_loop()

    def run_server_loop(self):
        while True:
            with self.state_lock:
                current_state = self.state
                timeout_since_heartbeat = time.time() - self.last_heartbeat_time
            if current_state == ServerState.FOLLOWER:
                if (
                    self.discovery_complete
                    and timeout_since_heartbeat > self.election_timeout
                ):
                    logger.info("Election timeout occurred")
                    self.transiton_to_candidate()
                time.sleep(self.heartbeat_interval)
            elif current_state == ServerState.CANDIDATE:
                if timeout_since_heartbeat > self.election_timeout:
                    logger.info("Candidate timeout occurred. Starting new election")
                    self.transiton_to_candidate()
                time.sleep(self.heartbeat_interval)
            elif current_state == ServerState.LEADER:
                self.send_heartbeat_to_peers()
                self.send_heartbeat_to_clients()
                time.sleep(self.heartbeat_interval)

                # Single-server optimization: commit all logs immediately
                with self.state_lock:
                    if len(self.peer_list.get_all_node()) == 0 and len(self.log) > 0:
                        self.commit_index = len(self.log) - 1

            # Process one log entry per iteration to avoid holding lock too long
            response_to_send = None
            with self.state_lock:
                if (
                    self.commit_index > self.last_applied
                    and self.last_applied + 1 < len(self.log)
                ):
                    # apply the logs to state machine
                    self.last_applied += 1
                    entry = self.log[self.last_applied]
                    logger.info(f"[STATE] Applying log entry {self.last_applied}/{len(self.log)-1} | Term: {entry.term} | Type: {entry.command.get('type')} | Client: {entry.command.get('id', 'N/A')[:8]}...")
                    message = entry.command
                    match message.get("type"):
                        case ClientMessageType.REQ_DISC.value:
                            #
                            self.client_list.add_node(
                                message.get("id"),
                                {
                                    "ip": message.get("ip"),
                                    "port": message.get("port"),
                                    "last_heartbeat": time.time(),
                                },
                            )

                            if self.state == ServerState.LEADER:
                                logger.info(
                                    f"Sending RES_DISC to client {ClientMessageType.RES_DISC.value} {message.get('id')} {message.get('ip')} {message.get('port')}"
                                )
                                response_to_send = (
                                    {
                                        "type": ClientMessageType.RES_DISC.value,
                                        "id": str(self.server_id),
                                        "ip": self.server_ip,
                                        "port": self.server_port,
                                    },
                                    message.get("ip"),
                                    message.get("port"),
                                )
                        case ClientMessageType.REQ_REMOVE_CLIENT.value:
                            self.client_list.remove_node(message.get("id"))
                            logger.info(
                                f"Removed client {message.get('id')} from client list"
                            )

                            for auction_id, auction in self.auction_list.items():
                                if auction.get_auctioneer()._id == message.get("id"):
                                    logger.info(f"auctioneer no longer alive")
                                else:
                                    auction.bidders.remove_node(message.get("id"))

                        case ClientMessageType.REQ_JOIN_AUCTION.value:
                            auction_id = message.get("auction_id")
                            status = False
                            auction = self.auction_list.get(auction_id)
                            if (
                                auction is not None
                                and auction.status == AuctionRoomStatus.AWAITING_PEEERS
                            ):
                                auction.add_participant(
                                    message.get("id"),
                                    {
                                        "id": message.get("id"),
                                        "ip": message.get("ip"),
                                        "port": message.get("port"),
                                    },
                                )
                                self.auction_list[auction_id] = auction
                                status = True

                            response_to_send = (
                                {
                                    "type": ClientMessageType.RES_JOIN_AUCTION.value,
                                    "id": str(self.server_id),
                                    "ip": self.server_ip,
                                    "port": self.server_port,
                                    "status": status,
                                },
                                message.get("ip"),
                                message.get("port"),
                            )

                            if (
                                auction.get_bidder_count()
                                >= auction.get_min_number_bidders()
                            ):
                                # Send message to auctioneer and all bidders that auction room is ready
                                room_enabled_msg = {
                                    "type": ClientMessageType.RES_AUCTION_ROOM_ENABLED.value,
                                    "id": str(self.server_id),
                                    "message": "Auction room ready",
                                    "status": "Success",
                                }

                                # Send to auctioneer
                                self.unicast.send_message(
                                    room_enabled_msg,
                                    auction.get_auctioneer().ip,
                                    auction.get_auctioneer().port,
                                )

                                # Send to all bidders
                                for _, bidder in auction.bidders.get_all_node().items():
                                    self.unicast.send_message(
                                        room_enabled_msg,
                                        bidder.get("ip"),
                                        bidder.get("port"),
                                    )

                        case ClientMessageType.REQ_CREATE_AUCTION.value:
                            auction_room = AuctionRoom(
                                auctioneer=Node(
                                    _id=message.get("id"),
                                    ip=message.get("ip"),
                                    port=message.get("port"),
                                ),
                                rounds=message.get("rounds"),
                                item=message.get("item"),
                                min_bid=message.get("min_bid"),
                                min_bidders=message.get("min_bidders"),
                            )
                            self.auction_list[auction_room.get_id()] = auction_room
                            # format string to retrieve status and bidders from room
                            response_to_send = (
                                {
                                    "type": ClientMessageType.RES_CREATE_AUCTION.value,
                                    "id": str(self.server_id),
                                    "ip": self.server_ip,
                                    "port": self.server_port,
                                    "auction_id": auction_room.get_id(),
                                    "msg": f"Auction room created, awaiting bidders to join {auction_room.get_min_number_bidders() - auction_room.get_bidder_count()}",
                                },
                                message.get("ip"),
                                message.get("port"),
                            )
                        case ClientMessageType.REQ_START_AUCTION.value:
                            auction_room = self.auction_list.get(
                                message.get("auction_id")
                            )
                            if auction_room is not None:
                                threading.Thread(
                                    target=self.auction_process,
                                    args=(auction_room,),
                                    daemon=True,
                                ).start()
                                response_to_send = (
                                    {
                                        "type": ClientMessageType.RES_START_AUCTION.value,
                                        "id": str(self.server_id),
                                        "ip": self.server_ip,
                                        "port": self.server_port,
                                        "status": "Success",
                                        "message": "Auction started",
                                    },
                                    message.get("ip"),
                                    message.get("port"),
                                )
                            else:
                                response_to_send = (
                                    {
                                        "type": ClientMessageType.RES_START_AUCTION.value,
                                        "id": str(self.server_id),
                                        "ip": self.server_ip,
                                        "port": self.server_port,
                                        "status": "Failed",
                                        "message": "Auction not found",
                                    },
                                    message.get("ip"),
                                    message.get("port"),
                                )
                        case ClientMessageType.RES_MAKE_BID.value:
                            self.active_rounds[message.get("auction_id")].add_bid(
                                message.get("id"), message.get("bid")
                            )
                        case _:
                            logger.info("default case")

            # Send response outside the lock to avoid blocking heartbeats
            if response_to_send is not None:
                self.unicast.send_message(
                    response_to_send[0], response_to_send[1], response_to_send[2]
                )

    def transiton_to_candidate(self):
        with self.state_lock:
            self.term += 1
            self.state = ServerState.CANDIDATE
            self.voted_for = str(self.server_id)
            self.votes_received = {str(self.server_id)}
            self.election_timeout = self._get_random_election_timeout()
            self.last_heartbeat_time = time.time()

        self.send_request_vote()
        self.check_election_won()

    def send_request_vote(self):
        peers = self.peer_list.get_all_node()
        for peer_id, peer_info in peers.items():
            vote_request = {
                "type": ServerMessageType.REQ_VOTE.value,
                "term": self.term,
                "id": str(self.server_id),
                "ip": self.server_ip,
                "port": self.server_port,
                "last_log_index": len(self.log) - 1,
                "last_log_term": self.log[-1].term if len(self.log) > 0 else 0,
            }
            self.unicast.send_message(vote_request, peer_info["ip"], peer_info["port"])

    def check_election_won(self):
        with self.state_lock:
            if self.state != ServerState.CANDIDATE:
                return

            total_nodes = len(self.peer_list.get_all_node()) + 1
            if len(self.votes_received) > (total_nodes // 2):
                logger.info(
                    f"Server: {self.server_id} has won the election for term: {self.term}"
                )
                self.state = ServerState.LEADER
                peers = self.peer_list.get_all_node()
                for peer_id in peers.keys():
                    self.next_index[peer_id] = len(self.log)
                    self.match_index[peer_id] = -1

    def handle_request_vote(self, msg):
        if msg["id"] == str(self.server_id):
            return
        with self.state_lock:
            grant_vote = False

            if msg["term"] > self.term:
                self.term = msg["term"]
                self.state = ServerState.FOLLOWER
                self.voted_for = None

            if msg["term"] == self.term:
                if self.voted_for is None or self.voted_for == msg["id"]:
                    server_last_log_term = self.log[-1].term if len(self.log) > 0 else 0
                    server_last_log_index = len(self.log) - 1

                    vote_possible = msg["last_log_term"] > server_last_log_term or (
                        msg["last_log_term"] == server_last_log_term
                        and msg["last_log_index"] >= server_last_log_index
                    )

                    if vote_possible:
                        grant_vote = True
                        self.voted_for = msg["id"]
                        self.last_heartbeat_time = time.time()

            term = self.term
        vote_response = {
            "type": ServerMessageType.RES_VOTE.value,
            "id": str(self.server_id),
            "term": term,
            "vote_granted": grant_vote,
            "voter_id": str(self.server_id),
        }

        self.unicast.send_message(vote_response, msg["ip"], msg["port"])
        logger.info(
            f"Vote {'GRANTED' if grant_vote else 'DENIED'} for {msg['id']} for term: {self.term}"
        )

    def handle_vote_resp(self, msg):
        if msg["id"] == str(self.server_id):
            return
        with self.state_lock:
            if self.state != ServerState.CANDIDATE or msg["term"] != self.term:
                return

            if msg["vote_granted"]:
                self.votes_received.add(msg["voter_id"])
                logger.info(
                    f"Received vote from {msg['voter_id']}. Total: {len(self.votes_received)}"
                )

        self.check_election_won()

    def send_heartbeat_to_clients(self):
        """Send heartbeat to all connected clients (unidirectional - no response expected)"""
        with self.state_lock:
            if self.state != ServerState.LEADER:
                return
            clients = self.client_list.get_all_node().copy()

        heartbeat_msg = {
            "type": ClientMessageType.SERVER_HEART_BEAT.value,
            "id": str(self.server_id),
            "ip": self.server_ip,
            "port": self.server_port,
        }

        for client_id, client_info in clients.items():
            self.unicast.send_message(
                heartbeat_msg, client_info.get("ip"), client_info.get("port")
            )

    def send_heartbeat_to_peers(self):
        """Send heartbeat/log replication to peer servers"""
        peers = self.peer_list.get_all_node()

        with self.state_lock:
            for peer_id, peer_info in peers.items():
                # edge case to be handled
                prev_log_idx = self.next_index[peer_id] - 1
                prev_log_term = 0
                if prev_log_idx >= 0 and prev_log_idx < len(self.log):
                    prev_log_term = self.log[prev_log_idx].term

                # Convert LogEntries to dicts for JSON serialization
                # Limit entries per message to avoid UDP size limits (typically 65KB)
                max_entries_per_msg = 10
                start_idx = self.next_index.get(peer_id)
                end_idx = min(start_idx + max_entries_per_msg, len(self.log))
                entries_to_send = [
                    entry.to_dict() for entry in self.log[start_idx:end_idx]
                ]

                heartbeat_msg = {
                    "type": ServerMessageType.REQ_APPEND_ENTRIES.value,
                    "term": self.term,
                    "id": str(self.server_id),
                    "ip": self.server_ip,
                    "port": self.server_port,
                    "prev_log_index": prev_log_idx,
                    "prev_log_term": prev_log_term,
                    "leader_commit": self.commit_index,
                    "entries": entries_to_send,
                }
                self.unicast.send_message(
                    heartbeat_msg, peer_info["ip"], peer_info["port"]
                )

    def handle_append_entries(self, msg):
        if msg["id"] == str(self.server_id):
            return

        with self.state_lock:

            if msg["term"] > self.term:
                self.term = msg["term"]
                self.state = ServerState.FOLLOWER
                self.voted_for = None

            if msg["term"] < self.term:
                resp = False
            elif msg["prev_log_index"] >= len(self.log):
                resp = False
            elif (
                msg["prev_log_index"] >= 0
                and msg["prev_log_term"] != self.log[msg["prev_log_index"]].term
            ):
                resp = False
            else:
                try:
                    del self.log[msg["prev_log_index"] + 1 :]
                except IndexError:
                    pass
                # Convert dict entries back to LogEntries objects
                for entry_dict in msg["entries"]:
                    self.log.append(LogEntries.from_dict(entry_dict))

                if msg["leader_commit"] > self.commit_index:
                    self.commit_index = min(msg["leader_commit"], len(self.log) - 1)
                resp = True
            append_entries_response = {
                "type": ServerMessageType.RES_APPEND_ENTRIES.value,
                "term": self.term,
                "success": resp,
                "id": str(self.server_id),
            }
            self.election_timeout = self._get_random_election_timeout()
            self.last_heartbeat_time = time.time()
        self.unicast.send_message(append_entries_response, msg["ip"], msg["port"])

    def handle_append_entries_resp(self, msg):
        if msg["id"] == str(self.server_id):
            return

        with self.state_lock:
            if self.term < msg.get("term"):
                self.term = msg.get("term")
                self.state = ServerState.FOLLOWER
                return

            if msg.get("success") == False:
                self.next_index[msg.get("id")] -= 1

            if msg["success"] == True and msg["term"] == self.term:
                self.match_index[msg.get("id")] = self.next_index[msg.get("id")]
                self.next_index[msg.get("id")] += 1

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

        logger.info(f"{auction}")
        self.unicast.send_message(
            {
                "type": ClientMessageType.RES_RETRIEVE_AUCTION_LIST.value,
                "available_auctions": auctions,  # Fixed: was "auction", should be "available_auctions"
            },
            message.get("ip"),
            message.get("port"),
        )

    def auction_process(self, auction_room):
        """
        responsible for the entire round based bidding process
        """
        # round initialized to 1
        # Send message to all clients in the room that request bid for round 1
        # Await all responses
        # Once we receive responses, send the highest bid to all clients
        # Increment round
        round_num = 1
        is_final_round = False
        while round_num <= auction_room.get_rounds():
            bidders_count = set(auction_room.bidders.get_all_node().keys())
            round_state = RoundState(round_num, expected_bidders=bidders_count)
            with self.state_lock:
                self.active_rounds[auction_room.get_id()] = round_state

            msg = {
                "type": ClientMessageType.REQ_MAKE_BID.value,
                "auction_id": auction_room.get_id(),
                "item": auction_room.item,
                "round": round_num,
                "current_highest": auction_room.min_bid,
            }

            for _, bidder in auction_room.bidders.get_all_node().items():
                self.unicast.send_message(msg, bidder.get("ip"), bidder.get("port"))

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
            result_msg = {
                "type": ClientMessageType.RES_ROUND_RESULT.value,
                "auction_id": auction_room.get_id(),
                "round": round_num,
                "highest_bid": highest_amount,
                "highest_bidder": highest_bidder,
                "is_final_round": is_final_round,
            }

            # Send result to all bidders
            for _, bidder in auction_room.bidders.get_all_node().items():
                self.unicast.send_message(result_msg, bidder["ip"], bidder["port"])

            # Send result to auctioneer
            auctioneer = auction_room.get_auctioneer()
            self.unicast.send_message(result_msg, auctioneer.ip, auctioneer.port)

            with self.round_lock:
                del self.active_rounds[auction_room.get_id()]

            round_num += 1

    def _get_highest_bid(self, bids: Dict[str, int]) -> tuple[str, int]:
        if not bids:
            return None, 0
        highest_bidder = max(bids, key=bids.get)
        return highest_bidder, bids[highest_bidder]


if __name__ == "__main__":

    server = Server()
    server.start_server()
