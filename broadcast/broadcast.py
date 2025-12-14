import socket
import json
from message.message_handler import MessageHandler
from loguru import logger

class Broadcast:
    def __init__(self):
        self.broadcast_address = "192.168.0.255"
        self.broadcast_port    = 5000
        self.broadcast_timeout = 5
        self.broadcast_recv_buffer_size = 1024

    def send_broadcast(self, message):
        broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        logger.info(f"Sending broadcast on ip:{self.broadcast_address}, port: {self.broadcast_port}")
        broadcast_sock.sendto(json.dumps(message).encode(), (self.broadcast_address, self.broadcast_port))

    def listen_broadcast(self, message_queue: MessageHandler):
        broadcast_listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        broadcast_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        broadcast_listen_sock.bind(('', self.broadcast_port))
        logger.info(f"Started listening for broadcast on ip:{self.broadcast_address}, port: {self.broadcast_port}")
        while True:
            data, addr = broadcast_listen_sock.recvfrom(self.broadcast_recv_buffer_size)
            msg = json.loads(data.decode())
            message_queue.add_message(msg)