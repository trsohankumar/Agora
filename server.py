import argparse
import uuid
import time
import threading

from loguru import logger
from enum import Enum
from typing import Dict

from auction.auction_room import AuctionRoom, AuctionRoomStatus, RoundState
from unicast.unicast import Unicast
from broadcast.broadcast import Broadcast
from message.message_handler import MessageHandler
from message.outgoing_message import OutgoingMessageHandler
from message.message_types import ServerMessageType, ClientMessageType
from message.message import Message
from node_list import NodeList, Node
from utils.common import DisconnectedError, RequestTimeoutError, get_ip_port
from utils.pending_requests import PendingRequest


class ServerState(Enum):
    FOLLOWER = "FOLLOWER"
    ELECTION = "ELECTION"
    COORDINATOR = "COORDINATOR"


class Server:
    def __init__(self, server_name, port):
        ip, _ = get_ip_port()

        self.server_node = Node(
            _id=str(uuid.uuid5(uuid.NAMESPACE_DNS, server_name)), ip=ip, port=port
        )
        self.state = ServerState.FOLLOWER
        self.peer_list = NodeList()
        self.client_list = NodeList()
        self.coordinator_node: Node = None

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

        # Bully algorithm state
        self.election_in_progress = False
        self.received_alive = False
        self.election_timeout = 2.0  # Time to wait for ALIVE responses
        self.coordinator_timeout = 3.0  # Time to wait for COORDINATOR after ALIVE
        self.heartbeat_timeout = 5.0  # Time to consider coordinator dead

        self.state_lock = threading.Lock()
        self.heartbeat_interval = 0.5
        self.client_heartbeat_timeout = 3.0
        self.last_coordinator_heartbeat = time.time()

        # Threads
        self.monitor_client_list_thread = threading.Thread(
            target=self.remove_timeout_client_from_list, daemon=True
        )
        self.follower_heartbeat_thread = threading.Thread(
            target=self.send_heartbeat_to_peers, daemon=True
        )
        self.client_heartbeat_thread = threading.Thread(
            target=self.send_heartbeat_to_clients, daemon=True
        )
        self.state_sync_thread = threading.Thread(
            target=self.sync_state_to_followers, daemon=True
        )

        self.monitor_client_list_thread.start()
        self.follower_heartbeat_thread.start()
        self.client_heartbeat_thread.start()
        self.state_sync_thread.start()

        # Auction state
        self.auction_list: Dict[str, AuctionRoom] = dict()
        self.active_rounds: Dict[str, RoundState] = dict()
        self.round_lock = threading.Lock()

        # State version for replication
        self.state_version = 0

        # Request/response tracking
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

    def handle_disc_resp(self, msg):
        """Handle discovery response from other servers"""
        if msg.sender._id == self.server_node._id:
            return

        logger.info(f"Discovery response from: {msg.sender._id}")
        if self.peer_list.get_node(msg.sender._id) is None:
            self.peer_list.add_node(msg.sender._id, msg.sender)

    def handle_disc_req(self, msg):
        """Handle discovery request from other servers"""
        sender_id = msg.sender._id
        if sender_id == self.server_node._id:
            return

        logger.info(f"Discovery request from: {sender_id}")

        if self.peer_list.get_node(sender_id) is None:
            self.peer_list.add_node(sender_id, msg.sender)

        self._send_message(
            Message(
                message_type=ServerMessageType.RES_DISC.value,
                sender=self.server_node,
                receiver=msg.sender,
            )
        )

    def register_callbacks(self):
        """Register message handlers"""
        # Server discovery
        self.message_handler.register_handler(
            ServerMessageType.REQ_DISC.value, self.handle_disc_req
        )
        self.message_handler.register_handler(
            ServerMessageType.RES_DISC.value, self.handle_disc_resp
        )

        # Bully algorithm messages
        self.message_handler.register_handler(
            ServerMessageType.ELECTION.value, self.handle_election
        )
        self.message_handler.register_handler(
            ServerMessageType.ALIVE.value, self.handle_alive
        )
        self.message_handler.register_handler(
            ServerMessageType.COORDINATOR.value, self.handle_coordinator
        )

        # State replication
        self.message_handler.register_handler(
            ServerMessageType.STATE_SYNC.value, self.handle_state_sync
        )
        self.message_handler.register_handler(
            ServerMessageType.STATE_ACK.value, self.handle_state_ack
        )
        self.message_handler.register_handler(
            ServerMessageType.HEARTBEAT.value, self.handle_heartbeat
        )

        # Client messages
        self.message_handler.register_handler(
            ClientMessageType.REQ_DISC.value, self.handle_client_discovery
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_JOIN_AUCTION.value, self.handle_join_auction
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_CREATE_AUCTION.value, self.handle_create_auction
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_START_AUCTION.value, self.handle_start_auction
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_MAKE_BID.value, self.handle_make_bid
        )
        self.message_handler.register_handler(
            ClientMessageType.CLIENT_HEART_BEAT.value, self.handle_client_heartbeat
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value,
            self.handle_retrieve_auction_list_req,
        )

    # ==================== BULLY ALGORITHM ====================

    def start_election(self):
        """Start a Bully election by sending ELECTION to all higher-ID nodes"""
        with self.state_lock:
            if self.election_in_progress:
                return
            self.election_in_progress = True
            self.received_alive = False
            self.state = ServerState.ELECTION

        logger.info(f"Starting election. My ID: {self.server_node._id}")

        # Get all peers with higher IDs
        higher_peers = []
        for peer_id, peer_info in self.peer_list.get_all_node().items():
            if peer_id > self.server_node._id:
                higher_peers.append(peer_info)

        if not higher_peers:
            # No higher peers - I become coordinator immediately
            logger.info("No higher-ID peers found. Becoming coordinator.")
            self.become_coordinator()
            return

        # Send ELECTION to all higher-ID peers
        for peer in higher_peers:
            self._send_message(
                Message(
                    message_type=ServerMessageType.ELECTION.value,
                    sender=self.server_node,
                    receiver=peer,
                )
            )

        # Wait for ALIVE response
        time.sleep(self.election_timeout)

        with self.state_lock:
            if not self.received_alive:
                # No ALIVE received - become coordinator
                logger.info("No ALIVE response received. Becoming coordinator.")
                self.become_coordinator()
            else:
                # Wait for COORDINATOR message
                logger.info("Received ALIVE, waiting for COORDINATOR announcement.")
                self.election_in_progress = False

    def become_coordinator(self):
        """Transition to coordinator state and announce to all peers"""
        with self.state_lock:
            self.state = ServerState.COORDINATOR
            self.coordinator_node = self.server_node
            self.election_in_progress = False
            # Clear stale client list - clients must re-register with new coordinator
            self.client_list = NodeList()

        logger.info(f"I am now the COORDINATOR: {self.server_node._id}")

        # Broadcast COORDINATOR to all peers
        for peer_id, peer_info in self.peer_list.get_all_node().items():
            self._send_message(
                Message(
                    message_type=ServerMessageType.COORDINATOR.value,
                    sender=self.server_node,
                    receiver=peer_info,
                )
            )

    def handle_election(self, msg):
        """Handle ELECTION message from a lower-ID node"""
        if msg.sender._id == self.server_node._id:
            return

        logger.info(f"Received ELECTION from {msg.sender._id}")

        # If I have higher ID, send ALIVE and start my own election
        if self.server_node._id > msg.sender._id:
            self._send_message(
                Message(
                    message_type=ServerMessageType.ALIVE.value,
                    sender=self.server_node,
                    receiver=msg.sender,
                )
            )
            # Start my own election in a separate thread
            threading.Thread(target=self.start_election, daemon=True).start()

    def handle_alive(self, msg):
        """Handle ALIVE response from a higher-ID node"""
        if msg.sender._id == self.server_node._id:
            return

        logger.info(f"Received ALIVE from {msg.sender._id}")

        with self.state_lock:
            self.received_alive = True
            self.state = ServerState.FOLLOWER

    def handle_coordinator(self, msg):
        """Handle COORDINATOR announcement from the new leader"""
        if msg.sender._id == self.server_node._id:
            return

        logger.info(f"Received COORDINATOR announcement from {msg.sender._id}")

        with self.state_lock:
            self.coordinator_node = msg.sender
            self.state = ServerState.FOLLOWER
            self.election_in_progress = False
            self.last_coordinator_heartbeat = time.time()

    def handle_heartbeat(self, msg):
        """Handle heartbeat from coordinator"""
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                self.last_coordinator_heartbeat = time.time()
                # Ensure we recognize the sender as coordinator
                if self.coordinator_node is None or self.coordinator_node._id != msg.sender._id:
                    self.coordinator_node = msg.sender

    # ==================== STATE REPLICATION ====================

    def handle_state_sync(self, msg):
        """Handle state synchronization from coordinator"""
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state == ServerState.COORDINATOR:
                return  # I'm the coordinator, ignore

            received_version = msg.data.get("version", 0)
            if received_version <= self.state_version:
                return  # Already have this or newer state

            logger.info(f"Receiving state sync v{received_version} from coordinator")

            # Update client list
            client_data = msg.data.get("clients", {})
            for client_id, client_info in client_data.items():
                node = Node.from_json(client_info)
                self.client_list.add_node(client_id, node)

            # Update auction list
            auction_data = msg.data.get("auctions", {})
            for auction_id, auction_info in auction_data.items():
                if auction_id not in self.auction_list:
                    auction_room = AuctionRoom.from_json(auction_info)
                    self.auction_list[auction_id] = auction_room

            self.state_version = received_version

        # Send ACK
        self._send_message(
            Message(
                message_type=ServerMessageType.STATE_ACK.value,
                sender=self.server_node,
                receiver=msg.sender,
                data={"version": received_version},
            )
        )

    def handle_state_ack(self, msg):
        """Handle state acknowledgment from followers (coordinator only)"""
        # Just log the acknowledgment - can be used for tracking replication status
        if msg.sender._id == self.server_node._id:
            return
        logger.debug(f"Received STATE_ACK v{msg.data.get('version')} from {msg.sender._id}")

    def sync_state_to_followers(self):
        """Periodically sync state to followers (only when coordinator)"""
        while True:
            time.sleep(1.0)

            with self.state_lock:
                if self.state != ServerState.COORDINATOR:
                    continue

                # Prepare state data
                client_data = {}
                for client_id, client_node in self.client_list.get_all_node().items():
                    client_data[client_id] = client_node.dict()

                auction_data = {}
                for auction_id, auction in self.auction_list.items():
                    auction_data[auction_id] = auction.to_json()

                self.state_version += 1
                state_data = {
                    "version": self.state_version,
                    "clients": client_data,
                    "auctions": auction_data,
                }

                peers = self.peer_list.get_all_node().copy()

            # Send state to all followers
            for peer_id, peer_info in peers.items():
                self._send_message(
                    Message(
                        message_type=ServerMessageType.STATE_SYNC.value,
                        sender=self.server_node,
                        receiver=peer_info,
                        data=state_data,
                    )
                )

    # ==================== CLIENT HANDLING ====================

    def handle_client_discovery(self, msg):
        """Handle client discovery request - only coordinator responds"""
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                return

            node = msg.sender.copy()
            node.last_heartbeat = time.time()
            self.client_list.add_node(msg.sender._id, node)

        logger.info(f"Client discovered: {msg.sender._id}")

        self._send_coordinator_message(
            Message(
                message_type=ClientMessageType.RES_DISC.value,
                sender=self.server_node,
                receiver=msg.sender,
            )
        )

    def handle_client_heartbeat(self, message):
        """Handle heartbeat from client"""
        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                return

            client = self.client_list.get_node(message.sender._id)
            if client is not None:
                client.last_heartbeat = time.time()

    def remove_timeout_client_from_list(self):
        """Remove timed-out clients from the list"""
        while True:
            time.sleep(self.client_heartbeat_timeout)

            with self.state_lock:
                if self.state != ServerState.COORDINATOR:
                    continue
                client_list = self.client_list.get_all_node().copy()
                current_time = time.time()

                clients_to_remove = []
                for client_id, client_info in client_list.items():
                    last_heartbeat = client_info.last_heartbeat
                    if current_time - last_heartbeat > self.client_heartbeat_timeout:
                        clients_to_remove.append(client_id)

                for client_id in clients_to_remove:
                    logger.warning(f"Client {client_id} timed out, removing")
                    self.client_list.remove_node(client_id)
                    # Remove from auctions
                    for _, auction in self.auction_list.items():
                        if auction.get_auctioneer()._id == client_id:
                            logger.info("Auctioneer no longer alive")
                        else:
                            auction.bidders.remove_node(client_id)

    # ==================== AUCTION HANDLING ====================

    def handle_create_auction(self, msg):
        """Handle auction creation request"""
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                return

            auction_room = AuctionRoom(
                auctioneer=msg.sender,
                rounds=msg.data.get("rounds"),
                item=msg.data.get("item"),
                min_bid=msg.data.get("min_bid"),
                min_bidders=msg.data.get("min_bidders"),
            )
            self.auction_list[auction_room.get_id()] = auction_room

        logger.debug(f"Created auction: {auction_room.to_json()}")

        data = {
            "auction_id": auction_room.get_id(),
            "msg": f"Auction room created, awaiting bidders to join {auction_room.get_min_number_bidders() - auction_room.get_bidder_count()}",
        }

        self._send_coordinator_message(
            Message(
                message_type=ClientMessageType.RES_CREATE_AUCTION.value,
                sender=self.server_node,
                receiver=msg.sender,
                data=data,
            )
        )

    def handle_join_auction(self, msg):
        """Handle auction join request"""
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                return

            auction_id = msg.data.get("auction_id")
            logger.info(f"Join request for auction: {auction_id}")
            status = False
            auction = self.auction_list.get(auction_id)
            if (
                auction is not None
                and auction.status == AuctionRoomStatus.AWAITING_PEEERS
            ):
                auction.add_participant(msg.sender._id, msg.sender)
                status = True

        self._send_coordinator_message(
            Message(
                message_type=ClientMessageType.RES_JOIN_AUCTION.value,
                receiver=msg.sender,
                sender=self.server_node,
                data={"status": status},
            )
        )

        if status and auction.get_bidder_count() >= auction.get_min_number_bidders():
            # Notify that auction room is ready
            room_enabled_msg_data = {
                "message": "Auction room ready",
                "status": "Success",
            }

            self._send_coordinator_message(
                Message(
                    message_type=ClientMessageType.RES_AUCTION_ROOM_ENABLED.value,
                    sender=self.server_node,
                    receiver=auction.get_auctioneer(),
                    data=room_enabled_msg_data,
                )
            )

            for _, bidder in auction.bidders.get_all_node().items():
                self._send_coordinator_message(
                    Message(
                        message_type=ClientMessageType.RES_AUCTION_ROOM_ENABLED.value,
                        sender=self.server_node,
                        receiver=bidder,
                        data=room_enabled_msg_data,
                    )
                )

    def handle_start_auction(self, msg):
        """Handle auction start request"""
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                return

            auction_room = self.auction_list.get(msg.data.get("auction_id"))

        if auction_room is not None:
            threading.Thread(
                target=self.auction_process,
                args=(auction_room,),
                daemon=True,
            ).start()
            self._send_coordinator_message(
                Message(
                    message_type=ClientMessageType.RES_START_AUCTION.value,
                    sender=self.server_node,
                    receiver=msg.sender,
                    data={
                        "status": "Success",
                        "message": "Auction started",
                    },
                )
            )
        else:
            self._send_coordinator_message(
                Message(
                    message_type=ClientMessageType.RES_START_AUCTION.value,
                    sender=self.server_node,
                    receiver=msg.sender,
                    data={
                        "status": "Failed",
                        "message": "Auction not found",
                    },
                )
            )

    def handle_make_bid(self, msg):
        """Handle bid from client"""
        if msg.sender._id == self.server_node._id:
            return

        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                return

            auction_id = msg.data.get("auction_id")
            if auction_id in self.active_rounds:
                self.active_rounds[auction_id].add_bid(
                    msg.sender._id, msg.data.get("bid")
                )

    def handle_retrieve_auction_list_req(self, message):
        """Handle request for available auctions"""
        with self.state_lock:
            if self.state != ServerState.COORDINATOR:
                return

            auctions = []
            for auction in self.auction_list.values():
                if auction.status == AuctionRoomStatus.AWAITING_PEEERS:
                    auctions.append(auction.to_json())

        logger.info(f"Available auctions: {auctions}")
        self._send_coordinator_message(
            Message(
                message_type=ClientMessageType.RES_RETRIEVE_AUCTION_LIST.value,
                sender=self.server_node,
                receiver=message.sender,
                data={"available_auctions": auctions},
            )
        )

    def auction_process(self, auction_room):
        """Run the auction rounds"""
        round_num = 1
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
                self._send_coordinator_message(
                    Message(
                        message_type=ClientMessageType.REQ_MAKE_BID.value,
                        sender=self.server_node,
                        receiver=bidder,
                        data=bid_request_data,
                    )
                )

            # Wait for all responses
            round_state.wait_for_all()

            # Process bids
            highest_bidder, highest_amount = self._get_highest_bid(round_state.bids)
            auction_room.min_bid = highest_amount
            auction_room.max_bidder = highest_bidder

            is_final_round = round_num == auction_room.get_rounds()

            result_data = {
                "auction_id": auction_room.get_id(),
                "round": round_num,
                "highest_bid": highest_amount,
                "highest_bidder": highest_bidder,
                "is_final_round": is_final_round,
            }

            # Send result to all bidders
            for _, bidder in auction_room.bidders.get_all_node().items():
                self._send_coordinator_message(
                    Message(
                        message_type=ClientMessageType.RES_ROUND_RESULT.value,
                        sender=self.server_node,
                        receiver=bidder,
                        data=result_data,
                    )
                )

            # Send result to auctioneer
            auctioneer = auction_room.get_auctioneer()
            self._send_coordinator_message(
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

    # ==================== MESSAGING ====================

    def _send_coordinator_message(self, msg):
        """Send message only if this server is the coordinator"""
        if self.state == ServerState.COORDINATOR:
            self.outgoing_handler.add_message(msg)

    def _send_message(self, msg):
        """Send message unconditionally"""
        self.outgoing_handler.add_message(msg)

    def send_heartbeat_to_clients(self):
        """Send heartbeat to all connected clients"""
        while True:
            time.sleep(self.heartbeat_interval)

            with self.state_lock:
                if self.state != ServerState.COORDINATOR:
                    continue
                clients = self.client_list.get_all_node().copy()

            for _, client_info in clients.items():
                self._send_coordinator_message(
                    Message(
                        message_type=ClientMessageType.SERVER_HEART_BEAT.value,
                        sender=self.server_node,
                        receiver=client_info,
                    )
                )

    def send_heartbeat_to_peers(self):
        """Send heartbeat to peer servers (only when coordinator)"""
        while True:
            time.sleep(self.heartbeat_interval)

            with self.state_lock:
                if self.state != ServerState.COORDINATOR:
                    continue
                peers = self.peer_list.get_all_node().copy()

            for peer_id, peer_info in peers.items():
                self._send_message(
                    Message(
                        message_type=ServerMessageType.HEARTBEAT.value,
                        sender=self.server_node,
                        receiver=peer_info,
                    )
                )

    # ==================== SERVER LIFECYCLE ====================

    def start_server(self):
        """Initialize and start the server"""
        self.message_handler.start_message_handler()
        self.outgoing_handler.start_message_handler()
        self.unicast.start_unicast_listen(self.message_handler)
        self.broadcast.start_broadcast_listen(self.message_handler)

        # Discovery phase
        for _ in range(5):
            self.broadcast.send_broadcast(ServerMessageType.REQ_DISC.value)
            time.sleep(1)

        self.discovery_complete = True
        logger.info(
            f"Discovery complete: {len(self.peer_list.get_all_node())} peers found"
        )

        with self.state_lock:
            self.last_coordinator_heartbeat = time.time()

        # Start initial election
        threading.Thread(target=self.start_election, daemon=True).start()

        self.run_server_loop()

    def run_server_loop(self):
        """Main server loop - monitors coordinator health and triggers elections"""
        while True:
            time.sleep(1.0)

            with self.state_lock:
                current_state = self.state
                time_since_heartbeat = time.time() - self.last_coordinator_heartbeat
                election_in_progress = self.election_in_progress

            # If we're a follower and haven't heard from coordinator
            if current_state == ServerState.FOLLOWER:
                if (
                    self.discovery_complete
                    and not election_in_progress
                    and time_since_heartbeat > self.heartbeat_timeout
                ):
                    logger.warning(
                        f"Coordinator timeout ({time_since_heartbeat:.2f}s). Starting election."
                    )
                    threading.Thread(target=self.start_election, daemon=True).start()


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog="Agora Server",
        description="Distributed auction server using Bully algorithm",
    )
    parser.add_argument("-n", "--name", required=True)
    parser.add_argument("-p", "--port", required=True, type=int)
    args = parser.parse_args()
    return args.name, args.port


if __name__ == "__main__":
    name, port = parse_arguments()
    server = Server(name, port)
    server.start_server()
