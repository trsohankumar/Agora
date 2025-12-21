import socket
import json
from message.message_handler import MessageHandler
import threading
from loguru import logger

class Broadcast:
    def __init__(self, ip_address, port):
        self.broadcast_address = '.'.join(ip_address.split('.')[:-1] + ['255'])
        self.broadcast_port    = port
        self.broadcast_timeout = 5  
        self.broadcast_recv_buffer_size = 1024
        self.worker_thread = None

    def start_broadcast_listen(self, msg_handler: MessageHandler):
        self.worker_thread = threading.Thread(target=self._listen_broadcast, args=(msg_handler, ), daemon=True)
        self.worker_thread.start()

    def send_broadcast(self, message):
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