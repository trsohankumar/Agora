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
from utils.pending_requests import PendingRequest
from ui.ui import Ui


class ClientState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1


class Client:
    def __init__(self):
        self.client_id = str(uuid.uuid4())
        self.client_ip, self.client_port = get_ip_port()
        self.client_state = ClientState.DISCONNECTED
        self.state_lock = threading.Lock()
        self.leader_server = None

        self.broadcast = Broadcast(self.client_ip)
        self.message_handler = MessageHandler()
        self.register_callbacks()
        self.message_handler.start_message_handler()
        self.unicast = Unicast(unicast_ip=self.client_ip, unicast_port=self.client_port)
        self.unicast.start_unicast_listen(self.message_handler)

        # Heartbeats
        self.heartbeat_interval = 0.1
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
            f"starting client {self.client_id} @ {self.client_ip} {self.client_port}"
        )

    def _send_request(self, msg, timeout: float = 10.0):

        request_type = msg["type"]
        pending = PendingRequest()

        with self.pending_lock:
            self.pending_requests[request_type] = pending

        try:
            self.unicast.send_message(
                msg, self.leader_server.get("ip"), self.leader_server.get("port")
            )
            pending.event.wait(timeout=timeout)

            if pending.disconnected:
                raise DisconnectedError("Not connected to server")
            if pending.response is None:
                raise RequestTimeoutError(f"Request {request_type} timed out")

            return pending.response
        finally:
            with self.pending_lock:
                self.pending_requests.pop(request_type, None)

    def _await_request(self, msg):
        request_type = msg["type"]
        pending = PendingRequest()

        with self.pending_lock:
            self.pending_requests[request_type] = pending

        try:
            pending.event.wait()
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
            logger.info("leader found at %s %s", message["ip"], message["port"])
            self.leader_server = {
                "id": message["id"],
                "ip": message["ip"],
                "port": message["port"],
            }

            self.client_state = ClientState.CONNECTED

    def search_for_leader(self):
        with self.state_lock:
            logger.info("searching for leader")
            client_message = {
                "type": ClientMessageType.REQ_DISC.value,
                "id": str(self.client_id),
                "ip": self.client_ip,
                "port": self.client_port,
            }
        self.broadcast.send_broadcast(client_message)
        time.sleep(1)

    def start_client(self):

        print("here")
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
                print("here")
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
            msg.get("available_auctions"),
        )

    def _handle_join_auction_response(self, msg):
        self._complete_request(ClientMessageType.REQ_JOIN_AUCTION.value, msg)

    def _handle_create_auction_response(self, msg):
        self._complete_request(ClientMessageType.REQ_CREATE_AUCTION.value, msg)

    def send_heartbeat(self):
        """Send periodic heartbeats to server (no response expected)"""
        while True:
            time.sleep(self.heartbeat_interval)
            with self.state_lock:
                if (
                    self.client_state == ClientState.CONNECTED
                    and self.leader_server is not None
                ):
                    msg = {
                        "type": ClientMessageType.CLIENT_HEART_BEAT.value,
                        "id": self.client_id,
                        "ip": self.client_ip,
                        "port": self.client_port,
                    }
                    leader_ip = self.leader_server.get("ip")
                    leader_port = self.leader_server.get("port")
                else:
                    continue

            # Send message outside the lock (no response expected)
            self.unicast.send_message(msg, ip=leader_ip, port=leader_port)

    def recv_server_heartbeat(self, message):
        """Receive heartbeat from server (no response needed)"""
        with self.state_lock:
            # Update last heartbeat time to detect server failures
            self.last_heartbeat_time = time.time()

            # Update leader info if it changed
            if self.leader_server is None or self.leader_server.get(
                "id"
            ) != message.get("id"):
                self.leader_server = {
                    "id": message.get("id"),
                    "ip": message.get("ip"),
                    "port": message.get("port"),
                }
                logger.info(f"Updated leader info from heartbeat: {message.get('id')}")

    def get_auctions_list(self):
        with self.state_lock:
            msg = {
                "type": ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port,
            }

        return self._send_request(msg)

    def create_new_auction(
        self, item: str, min_bid_amt: int, min_bidders: int, no_of_rounds: int
    ):
        with self.state_lock:
            msg = {
                "type": ClientMessageType.REQ_CREATE_AUCTION.value,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port,
                "item": item,
                "min_bid": min_bid_amt,
                "min_bidders": min_bidders,
                "rounds": no_of_rounds,
            }

        return self._send_request(msg=msg)

    def await_make_bid(self):
        msg = {"type": ClientMessageType.REQ_MAKE_BID.value}
        return self._await_request(msg)

    def await_round_result(self):
        msg = {"type": ClientMessageType.RES_ROUND_RESULT.value}
        return self._await_request(msg)

    def make_bid(self, auction_id, bid):
        with self.state_lock:
            msg = {
                "type": ClientMessageType.RES_MAKE_BID.value,
                "auction_id": auction_id,
                "bid": bid,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port,
            }
            (ip, port) = (self.leader_server.get("ip"), self.leader_server.get("port"))
        self.unicast.send_message(msg, ip, port)

    def join_auction(self, auction_id):
        with self.state_lock:
            msg = {
                "type": ClientMessageType.REQ_JOIN_AUCTION.value,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port,
                "auction_id": auction_id,
            }

        return self._send_request(msg)

    def _handle_auction_room_enabled(self, msg):
        if msg.get("status") == "Success":
            with self.state_lock:
                self.is_auction_room_enabled = True

    def start_auction(self, auction_id):
        with self.state_lock:
            msg = {
                "type": ClientMessageType.REQ_START_AUCTION.value,
                "id": self.client_id,
                "auction_id": auction_id,
                "ip": self.client_ip,
                "port": self.client_port,
            }
        return self._send_request(msg)

    def _handle_make_bid(self, msg):
        self._complete_request(ClientMessageType.REQ_MAKE_BID.value, msg)

    def _handle_start_auction_result(self, msg):
        self._complete_request(ClientMessageType.REQ_START_AUCTION.value, msg)

    def _handle_round_result(self, msg):
        self._complete_request(ClientMessageType.RES_ROUND_RESULT.value, msg)


def main():
    # 1. broadcasts itself to the network
    # 2. awaits response from leader
    # 3. starts heartbeat to leader
    # 4. no response from leader -> broadcast
    client = Client()

    ui = Ui(client=client)
    ui_thread = threading.Thread(target=ui.start, daemon=True)

    ui_thread.start()
    client.start_client()


if __name__ == "__main__":
    main()
