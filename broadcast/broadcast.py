import json
import socket
import time

from loguru import logger

from constants import BROADCAST_ADDRESS, BROADCAST_PORT, BROADCAST_TIMEOUT
from util import request_response_handler, uuid_util


class Broadcast:

    def __init__(self, component):
        self.uuid = uuid_util.get_uuid()
        self.component = component
        self.timeout = BROADCAST_TIMEOUT
        logger.debug("Broadcast Thread {} for Server {} up", self.uuid, component.uuid)

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
            logger.debug("Listening to broadcast address at port {}", BROADCAST_PORT)
            try:
                while True:
                    data, addr = broadcast_socket.recvfrom(8192)
                    if data:
                        message = json.loads(data.decode())
                        logger.debug("Received message from {} : {}", str(addr), message)
                        request_response_handler.resolve_and_put_in_queue(message, self.component)
            except Exception as e:
                raise KeyboardInterrupt
            finally:
                logger.critical("Broadcast listener shutting down")
