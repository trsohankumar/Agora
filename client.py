from typing import Any
import uuid
import threading
import time
from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from utils.common import get_ip_port
from message.message_handler import MessageHandler
from enum import Enum
from loguru import logger
from message.message_types import ClientMessageType

class ClientState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1

class Client:
    def __init__(self):
        self.client_id = uuid.uuid4()
        self.client_ip, self.client_port = get_ip_port()
        logger.info(
            f"starting client {self.client_id} @ {self.client_ip} {self.client_port}"
        )

        self.message_handler = MessageHandler()
        self.broadcast = Broadcast(self.client_ip)
        self.unicast = Unicast(unicast_ip= self.client_ip, unicast_port=self.client_port)
        self.client_state = ClientState.DISCONNECTED
        self.leader_server = None
        self.register_callbacks()

        self.req_heartbeat_thread = threading.Timer(interval=self.heartbeat_interval, function=self.send_heartbeat)
        self.req_heartbeat_thread.start()
        self.state_lock = threading.Lock()

        self.heartbeat_interval = 0.05
        self.heartbeat_timeout = 0.1
        self.last_heartbeat_time = time.time()

    def register_callbacks(self):
        self.message_handler.register_handler(ClientMessageType.RES_DISC.value, self.discover_leader)
        self.message_handler.register_handler(ClientMessageType.RES_HEART_BEAT.value, self.recv_heartbeats_resp)

    def discover_leader(self, message):
        with self.state_lock:
            logger.info("leader found at %s %s", message["ip"], message["port"])
            self.leader_server = {
                "id": message["id"],
                "ip": message["ip"],
                "port": message["port"]
            }
            self.client_state = ClientState.CONNECTED

    def search_for_leader(self):
        while True:
            with self.state_lock:
                if self.leader_server is not None: 
                    break
                logger.info("searching for leader")
                client_message = {
                    "type": ClientMessageType.REQ_DISC.value,
                    "id": str(self.client_id),
                    "ip": self.client_ip,
                    "port": self.client_port
                }
            self.broadcast.send_broadcast(client_message)
            time.sleep(1)

    def start_client(self):
        self.message_handler.start_message_handler()
        self.unicast.start_unicast_listen(self.message_handler)
        while True:
            with self.state_lock:
                time_since_heartbeat = time.time() - self.last_heartbeat_time
                if time_since_heartbeat > self.heartbeat_timeout:
                    self.client_state = ClientState.DISCONNECTED
                    self.leader_server = None
                current_state = self.client_state
            if current_state == ClientState.DISCONNECTED:
                self.search_for_leader()
            elif current_state == ClientState.CONNECTED:
                #self.send_heartbeats()
                continue

    def send_heartbeat(self):
        with self.state_lock:
            if ClientState == ClientState.CONNECTED:
                msg = {
                    "type": ClientMessageType.REQ_HEART_BEAT.value,
                    "id": self.client_id,
                    "ip": self.client_ip,
                    "port": self.client_port
                }
                self.unicast.send_message(msg, ip=self.leader_server.get("ip"), port=self.leader_server.get("port")) 
                
    def recv_heartbeats_resp(self, message):
        with self.state_lock:
            if self.leader_server.get("id") != message.get('id'):
                self.leader_server = {
                    "id": message.get('ip'),
                    "ip": message.get('ip'),
                    "port": message.get('port')
                } 
            self.last_heartbeat_time = time.time()


def main():
    # 1. broadcasts itself to the network
    # 2. awaits response from leader
    # 3. starts heartbeat to leader
    # 4. no response from leader -> broadcast
    client = Client()
    client.start_client()


if __name__ == "__main__":
    main()