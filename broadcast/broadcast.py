import socket
import json
from message.message_handler import MessageHandler
import threading
from loguru import logger
from node_list import Node
from message.message import Message

class Broadcast:
    def __init__(self, node: Node):
        self.node: Node = node
        self.broadcast_address = self._get_broadcast_ip(self.node.ip)
        self.broadcast_port    = 5000
        self.broadcast_timeout = 5
        self.broadcast_recv_buffer_size = 1024
        self.worker_thread = None,


    def _get_broadcast_ip(self, node_ip):
        address = ".".join(node_ip.split(".")[:3]) + "." + "255"
        return address


    def start_broadcast_listen(self, msg_handler: MessageHandler):
        self.worker_thread = threading.Thread(target=self._listen_broadcast, args=(msg_handler, ), daemon=True)
        self.worker_thread.start()

    def send_broadcast(self, message_type):
        message = Message(
            message_type=message_type,
            sender=self.node,
        )

        broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        logger.info(f"Sending broadcast on ip:{self.broadcast_address}, port: {self.broadcast_port}")

        broadcast_sock.sendto(json.dumps(message).encode(), (self.broadcast_address, self.broadcast_port))
        broadcast_sock.close()

    def _listen_broadcast(self, message_queue: MessageHandler):
        broadcast_listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        broadcast_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        broadcast_listen_sock.bind(('', self.broadcast_port))
        logger.info(f"Started listening for broadcast on ip:{self.broadcast_address}, port: {self.broadcast_port}")
        while True:
            data, addr = broadcast_listen_sock.recvfrom(self.broadcast_recv_buffer_size)
            msg = json.loads(data.decode())
            message_queue.add_message(msg)

        broadcast_listen_sock.close()