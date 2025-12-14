from loguru import logger
from message.message_handler import MessageHandler
import threading
import json
import socket

class Unicast:
    def __init__(self):
        self.worker_thread = None
        self.unicast_port = 1234
        pass

    def setup_unicast(self):
        pass

    def send_message(self, msg):
        # will receive dest addr and port from the message and send a UDP message to that ip and port
        pass

    def listen_message(self, msg_handler: MessageHandler):
        # will listen for unicast message and when a message is received will add to the messge queue

        pass