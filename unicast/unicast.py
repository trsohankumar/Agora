from loguru import logger
from message.message_handler import MessageHandler
import threading
import json
import socket

class Unicast:
    def __init__(self, unicast_port, unicast_ip):
        self.worker_thread = None
        self.unicast_port = unicast_port
        self.unicast_ip = unicast_ip
        pass

    def start_unicast_listen(self, msg_handler: MessageHandler):
        self.worker_thread = threading.Thread(target=self._listen_message, args=(msg_handler,), daemon=True)
        self.worker_thread.start()

    def send_message(self, msg, ip, port):
        # will receive dest addr and port from the message and send a UDP message to that ip and port
        unicast_send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        unicast_send_socket.sendto(json.dumps(msg).encode(), (ip, port))
        unicast_send_socket.close()

    def _listen_message(self, msg_handler: MessageHandler):
        # will listen for unicast message and when a message is received will add to the messge queue
        unicast_listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        unicast_listen_socket.bind(('', self.unicast_port))

        while True:
            data, addr = unicast_listen_socket.recvfrom(65535)
            message = json.loads(data.decode())
            msg_handler.add_message(message)
