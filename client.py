import uuid
import threading
import time
from enum import Enum
from loguru import logger
from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from utils.common import get_ip_port, DisconnectedError, RequestTimeoutError
from message.message_handler import MessageHandler
from message.message_types import ClientMessageType
from node_list import Node
from utils.pending_requests import PendingRequest
from ui.ui import Ui


class ClientState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1


class Client:
    def __init__(self):
        self.client_id = str(uuid.uuid4())
        client_ip, client_port = get_ip_port()
        self.client_node = Node(_id=self.client_id, ip=client_ip, port=client_port)
        self.client_state = ClientState.DISCONNECTED
        self.state_lock = threading.Lock()
        self.leader_server: Node = None

        self.broadcast = Broadcast(node=self.client_node)
        self.message_handler = MessageHandler()
        self.register_callbacks()
        self.message_handler.start_message_handler()
        self.unicast = Unicast(node=self.client_node)
        self.unicast.start_unicast_listen(self.message_handler)

        # Heartbeats
        self.heartbeat_interval = 0.250
        self.heartbeat_timeout = 2.0
        self.last_heartbeat_time = time.time()
        self.req_heartbeat_thread = threading.Thread(
            target=self.send_heartbeat, daemon=True
        )
        self.req_heartbeat_thread.start()

        # auction room
        self.is_auction_room_enabled = False

        # request/resp tracking
        self.pending_requests: dict[str, PendingRequest] = {}
        self.pending_lock = threading.Lock()

        logger.info(
            f"starting client {self.client_id} @ {self.client_node.ip} {self.client_node.port}"
        )

    def _send_request(self, msg_type, data={}, timeout: float = 10.0):
        pending = PendingRequest()

        with self.pending_lock:
            self.pending_requests[msg_type] = pending

        try:
            with self.state_lock:
                leader = self.leader_server
            self.unicast.send_message(msg_type, leader, data)
            pending.event.wait(timeout=timeout)

            if pending.disconnected:
                raise DisconnectedError("Not connected to server")
            if pending.response is None:
                raise RequestTimeoutError(f"Request {msg_type} timed out")

            return pending.response
        finally:
            with self.pending_lock:
                self.pending_requests.pop(msg_type, None)

    def _await_request(self, msg_type):
        pending = PendingRequest()

        with self.pending_lock:
            self.pending_requests[msg_type] = pending

        try:
            pending.event.wait()
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

    def register_callbacks(self):
        self.message_handler.register_handler(
            ClientMessageType.RES_DISC.value, self.discover_leader
        )
        self.message_handler.register_handler(
            ClientMessageType.SERVER_HEART_BEAT.value, self.recv_server_heartbeat
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_RETRIEVE_AUCTION_LIST.value,
            self._handle_auction_list_response,
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_JOIN_AUCTION.value, self._handle_join_auction_response
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_CREATE_AUCTION.value,
            self._handle_create_auction_response,
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_AUCTION_ROOM_ENABLED.value,
            self._handle_auction_room_enabled,
        )
        self.message_handler.register_handler(
            ClientMessageType.REQ_MAKE_BID.value, self._handle_make_bid
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_START_AUCTION.value, self._handle_start_auction_result
        )
        self.message_handler.register_handler(
            ClientMessageType.RES_ROUND_RESULT.value, self._handle_round_result
        )

    def discover_leader(self, message):
        with self.state_lock:
            logger.info("leader found at %s %s", message.sender.ip, message.sender.port)
            self.leader_server = message.sender
            self.client_state = ClientState.CONNECTED

    def search_for_leader(self):
        with self.state_lock:
            logger.info("searching for leader")
        self.broadcast.send_broadcast(ClientMessageType.REQ_DISC.value)
        time.sleep(1)

    def start_client(self):

        while True:
            with self.state_lock:
                current_state = self.client_state
                time_since_heartbeat = time.time() - self.last_heartbeat_time
                should_disconnect = (
                    current_state == ClientState.CONNECTED
                    and time_since_heartbeat > self.heartbeat_timeout
                )

                if should_disconnect:
                    logger.warning(f"Heartbeat timeout")
                    self._on_disconnect()

            if current_state == ClientState.DISCONNECTED:
                self.search_for_leader()

            time.sleep(0.1)

    def _on_disconnect(self):
        with self.state_lock:
            self.client_state = ClientState.DISCONNECTED
            self.leader_server = None

        # wake up all blocked requests
        with self.pending_lock:
            for pending in self.pending_requests.values():
                pending.disconnected = True
                pending.event.set()
            self.pending_requests.clear()

        logger.warning("Disconnected from leader - all pending requests cancelled")

    def is_connected(self):
        with self.state_lock:
            return self.client_state == ClientState.CONNECTED

    def auction_room_enabled(self):
        with self.state_lock:
            return self.is_auction_room_enabled

    def _handle_auction_list_response(self, msg):
        self._complete_request(
            ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value,
            msg.data.get("available_auctions"),
        )

    def _handle_join_auction_response(self, msg):
        self._complete_request(ClientMessageType.REQ_JOIN_AUCTION.value, msg.data)

    def _handle_create_auction_response(self, msg):
        self._complete_request(ClientMessageType.REQ_CREATE_AUCTION.value, msg.data)

    def send_heartbeat(self):
        """Send periodic heartbeats to server (no response expected)"""
        while True:
            time.sleep(self.heartbeat_interval)
            with self.state_lock:
                if (
                    self.client_state == ClientState.CONNECTED
                    and self.leader_server is not None
                ):
                    leader = self.leader_server
                else:
                    continue

            # Send message outside the lock (no response expected)
            self.unicast.send_message(ClientMessageType.CLIENT_HEART_BEAT.value, leader)

    def recv_server_heartbeat(self, message):
        """Receive heartbeat from server (no response needed)"""
        with self.state_lock:
            # Update last heartbeat time to detect server failures
            self.last_heartbeat_time = time.time()

            # Update leader info if it changed
            if (
                self.leader_server is None
                or self.leader_server._id != message.sender._id
            ):
                self.leader_server = message.sender
                logger.info(f"Updated leader info from heartbeat: {message.sender._id}")

    def get_auctions_list(self):
        return self._send_request(ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value)

    def create_new_auction(
        self, item: str, min_bid_amt: int, min_bidders: int, no_of_rounds: int
    ):
        data = {
            "item": item,
            "min_bid": min_bid_amt,
            "min_bidders": min_bidders,
            "rounds": no_of_rounds,
        }
        return self._send_request(ClientMessageType.REQ_CREATE_AUCTION.value, data)

    def await_make_bid(self):
        return self._await_request(ClientMessageType.REQ_MAKE_BID.value)

    def await_round_result(self):
        return self._await_request(ClientMessageType.RES_ROUND_RESULT.value)

    def make_bid(self, auction_id, bid):
        with self.state_lock:
            leader = self.leader_server
        self.unicast.send_message(
            ClientMessageType.RES_MAKE_BID.value,
            leader,
            {"auction_id": auction_id, "bid": bid},
        )

    def join_auction(self, auction_id):
        return self._send_request(
            ClientMessageType.REQ_JOIN_AUCTION.value, {"auction_id": auction_id}
        )

    def _handle_auction_room_enabled(self, msg):
        if msg.data.get("status") == "Success":
            with self.state_lock:
                self.is_auction_room_enabled = True

    def start_auction(self, auction_id):
        return self._send_request(
            ClientMessageType.REQ_START_AUCTION.value, {"auction_id": auction_id}
        )

    def _handle_make_bid(self, msg):
        self._complete_request(ClientMessageType.REQ_MAKE_BID.value, msg.data)

    def _handle_start_auction_result(self, msg):
        self._complete_request(ClientMessageType.REQ_START_AUCTION.value, msg.data)

    def _handle_round_result(self, msg):
        self._complete_request(ClientMessageType.RES_ROUND_RESULT.value, msg.data)


def main():
    client = Client()

    ui = Ui(client=client)
    ui_thread = threading.Thread(target=ui.start, daemon=True)

    ui_thread.start()
    client.start_client()


if __name__ == "__main__":
    main()
