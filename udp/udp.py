import json
import socket
import time

from loguru import logger

import constants
from util import request_response_handler
from util.network_util import get_ip_address
from util.uuid_util import get_uuid


class UDP:

    def __init__(self, component):
        self.uuid = get_uuid()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host_name = constants.SERVER_ADDRESS
        self.socket.bind((constants.SERVER_ADDRESS, 0))
        self.ip_address = get_ip_address()
        self.port = self.socket.getsockname()[1]
        self.component = component
        logger.debug("UDP Server Thread {} for Server {} up at {}/ {}", self.uuid, component.uuid,
                     constants.SERVER_ADDRESS + ":" + str(self.port), self.ip_address + ":" + str(self.port))

    def unicast(self, message, target_address, target_port, wait=True):
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
                data, client_address = self.socket.recvfrom(8192)
                message = json.loads(data.decode())
                logger.info("Received unicast message type {} from {} for {}", message.get("type", "unknown"), client_address, self.component.uuid)
                request_response_handler.resolve_and_put_in_queue(message, self.component)
        except Exception as e:
            logger.error("Caught exception {}", e)
            logger.error("[SHUTTING DOWN] UDP Server is stopping...")
            raise KeyboardInterrupt
        finally:
            logger.critical("UDP listener for {} shutting down", self.component.uuid)
