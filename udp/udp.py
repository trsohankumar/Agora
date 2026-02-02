import json
import socket
import struct
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
        self.multicast_setup = False
        self.multicast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.multicast_ip = None
        self.multicast_port = None
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

    def setup_multicast(self, multicast_ip, multicast_port):
        if self.multicast_setup:
            self.multicast_socket.close()

        self.multicast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.multicast_ip = multicast_ip
        self.multicast_port = multicast_port
        try:
            self.multicast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.multicast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            logger.warning("No attribute SO_REUSEPORT/SO_REUSEADDR, skipping setting them")
        self.multicast_socket.bind(('', multicast_port))

        # Join the multicast group
        mreq = struct.pack("4sl", socket.inet_aton(multicast_ip), socket.INADDR_ANY)
        self.multicast_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        logger.info("Joined multicast group {}:{}", multicast_ip, multicast_port)
        self.multicast_setup = True

    def multicast(self, message, multicast_ip, multicast_port):
        if not self.multicast_socket:
            logger.error("Multicast socket is not set up. Call setup_multicast() first.")
            return
        logger.debug("Multicasting message : {}", message)
        self.multicast_socket.sendto(json.dumps(message).encode(), (multicast_ip, multicast_port))

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

    def listen_multicast(self):
        try:
            while not self.multicast_setup:
                time.sleep(1)
            while True:
                try:
                    data, client_address = self.multicast_socket.recvfrom(8192)
                    message = json.loads(data.decode())
                    logger.debug("Received multicast from {} for {}", client_address, self.component.uuid)
                    request_response_handler.resolve_and_put_in_queue(message, self.component)
                except OSError as e:
                    if e.errno == 9:  # Bad file descriptor - socket was replaced
                        logger.debug("Multicast socket was replaced, waiting for new socket...")
                        time.sleep(0.5)
                        continue
                    raise
        except Exception as e:
            logger.error("Caught exception in multicast listener: {}", e)
            raise KeyboardInterrupt
        finally:
            logger.critical("Multicast listener for {} shutting down", self.component.uuid)
