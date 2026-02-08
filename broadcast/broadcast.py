import json
import socket
import time

from loguru import logger

from constants import BROADCAST_ADDRESS, BROADCAST_PORT, BROADCAST_TIMEOUT
from util import uuid_util


class Broadcast:

    def __init__(self, message_manager):
        self.uuid = uuid_util.get_uuid()
        self.message_manager = message_manager
        self.timeout = BROADCAST_TIMEOUT

    def broadcast(self, message):
        logger.debug("Broadcasting message : {}", message)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as broadcast_socket:
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            broadcast_socket.sendto(json.dumps(message).encode(), (BROADCAST_ADDRESS, BROADCAST_PORT))
            time.sleep(self.timeout)

    def listen(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as broadcast_socket:
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                logger.warning("No attribute SO_REUSEPORT/SO_REUSEADDR, skipping setting them")
                
            broadcast_socket.bind(('', BROADCAST_PORT))
            logger.info("Listening for broadcast messages at port {}", BROADCAST_PORT)
            try:
                while True:
                    data, addr = broadcast_socket.recvfrom(8192)
                    if data:
                        message = json.loads(data.decode())
                        logger.debug("Received from addr{} : msg {}", str(addr), message)
                        self.message_manager.enqueue(message)
            except Exception:
                raise KeyboardInterrupt
            finally:
                logger.critical("Broadcast listener shutting down")
