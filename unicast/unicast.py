import json
import socket
import time

from loguru import logger

import constants
from util.network_util import get_ip_address
from util.uuid_util import get_uuid


class Unicast:

    def __init__(self, message_manager):
        self.uuid = get_uuid()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host_name = constants.SERVER_ADDRESS
        self.socket.bind((constants.SERVER_ADDRESS, 0))
        self.ip_address = get_ip_address()
        self.port = self.socket.getsockname()[1]
        self.message_manager = message_manager
        logger.info("Server has ip: {} and port: {}", self.ip_address, self.port)
        
    def unicast(self, message, target_address, target_port, wait=False):
        logger.debug("Unicasting message : {}", message)
        self.socket.sendto(json.dumps(message).encode(), (target_address, target_port))
        if wait:
            time.sleep(constants.UNICAST_TIMEOUT)

    def send_to_all(self, message, recipients):
        """Send message to multiple recipients without blocking between sends."""
        for recipient in recipients:
            self.socket.sendto(json.dumps(message).encode(), (recipient["ip_address"], recipient["port"]))

    def listen(self):
        try:
            while True:
                data, client_address = self.socket.recvfrom(65535)
                message = json.loads(data.decode())
                logger.debug("Received unicast message type {} from {}", message.get("type", "unknown"), client_address)
                self.message_manager.enqueue(message)
        except Exception as e:
            logger.error("Caught exception {}", e)
            raise KeyboardInterrupt
        finally:
            logger.critical("UDP listener shutting down")
