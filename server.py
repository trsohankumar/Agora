from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from message.message_handler import MessageHandler
from node_list import NodeList

from loguru import logger
import uuid
import threading
import socket

def get_ip_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(("8.8.8.8", 80))
    return {
        "ip" : sock.getsockname()[0],
        "port" : sock.getsockname()[1]
    }

class Server:
    def __init__(self):
        self.server_id = uuid.uuid4()
        res = get_ip_port()
        self.server_ip = res["ip"]
        self.server_port = res["port"]
        self.peer_list = NodeList()
        logger.info(f"Server starting with id: {self.server_id}, ip: k{self.server_ip}, port: {self.server_port}")
        # setup message resolver for the server
        self.message_queue = MessageHandler(self)

        # setup unicast communication for the server
        self.unicast = Unicast(unicast_ip= self.server_ip, unicast_port=self.server_port)

        # setup broadcast communication for the server
        self.broadcast = Broadcast()


    def start_server(self):
        self.message_queue.start_message_handler()
        self.unicast.start_unicast_listen(self.message_queue)
        self.broadcast.start_broadcast_listen(self.message_queue)
        broadcast_message = {
            "type": "DISC",
            "id": str(self.server_id),
            "ip": self.server_ip,
            "port": self.server_port
        }
        self.broadcast.send_broadcast(broadcast_message)


if __name__ == "__main__":

    server = Server()
    server.start_server()

    while True:
        pass