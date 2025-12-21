import uuid
import threading
import socket
import time
from enum import Enum
from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from message.message_handler import MessageHandler
from heartbeat.heartbeat import HeartBeat
from node_list import NodeList
from loguru import logger

def get_ip_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(("8.8.8.8", 80))
    return {
        "ip" : sock.getsockname()[0],
        "port" : sock.getsockname()[1]
    }


class Behavior(Enum):
    Init = 0
    Follower = 1
    Candidate = 2
    Leader = 3


class Server:
    def __init__(self):
        self.server_id = uuid.uuid4()
        res = get_ip_port()
        self.server_ip = res["ip"]
        self.server_port = res["port"]
        self.peer_list = NodeList()
        
        self.term = 0
        logger.info(f"Server starting with id: {self.server_id}, ip: {self.server_ip}, port: {self.server_port}")

                
        # setup message resolver for the server
        self.message_queue = MessageHandler(self)
        # setup unicast communication for the server
        self.unicast = Unicast(unicast_ip= self.server_ip, unicast_port=self.server_port)
        # setup broadcast communication for the server
        self.broadcast = Broadcast(self.server_ip, 5000)
        
        self.heartbeat = HeartBeat(self.unicast, 5)
        self.state = Behavior.Init
        logger.info(f"server in initial state")

    def start_follower(self):
        # Listen to heartbeats from leader and replicate the log from leaders
        self.heartbeat.listen()

    def start_server(self):
        # self.message_queue.start_message_handler()
        # self.unicast.start_unicast_listen(self.message_queue)
        self.broadcast.start_broadcast_listen(self.message_queue)
        broadcast_message = {
            "type": "DISC",
            "id": str(self.server_id),
            "ip": self.server_ip,
            "port": self.server_port
        }
        self.broadcast.send_broadcast(broadcast_message)
        
        # while len(self.peer_list.nodes) < 1:
        # logger.info("waiting for servers to join")
        

        self.state = Behavior.Follower

        while True:
            if self.state == Behavior.Follower:
                self.start_follower()
            elif self.state == Behavior.Candidate:
                self.start_candidate()
            elif self.state == Behavior.Leader:
                self.start_leader()
        

if __name__ == "__main__":

    server = Server()
    server.start_server()

    while True:
        pass