from loguru import logger
import queue
import threading

class MessageHandler:

    def __init__(self, server):
        self.message_queue = queue.Queue()
        self.worker_thread = None 
        self.server = server

    def add_message(self, msg):
        self.message_queue.put(msg)

    def start_message_handler(self):
        self.worker_thread = threading.Thread(target=self._process_message, daemon=True)
        self.worker_thread.start()

    def _process_message(self):
        while True:
            try:
                msg = self.message_queue.get(timeout=1.0)
                self._handle_message(msg)
            except queue.Empty:
                continue

    def _handle_message(self, msg):
        if msg["id"] != str(self.server.server_id):
            if msg["type"] == "DISC":
                logger.info(f"Handling message: {msg}")
                if self.server.peer_list.get_node(msg["id"]) == None:
                    self.server.peer_list.add_node(msg["id"], {"ip": msg["ip"], "port": msg["port"]})
                    return_messge = {
                        "type": "DISC_RESP",
                        "ip": self.server.server_ip,
                        "port": self.server.server_port,
                        "id": str(self.server.server_id)
                    }
                    self.server.unicast.send_message(return_messge, msg["ip"], msg["port"])
            elif msg["type"] == "DISC_RESP":
                logger.info(f"Handling message: {msg}")
                if self.server.peer_list.get_node(msg["id"]) == None:
                    self.server.peer_list.add_node(msg["id"], {"ip": msg["ip"], "port": msg["port"]})
            elif msg["type"] == "VOTE_REQ":
                self.server.handle_request_vote(msg)
            elif msg["type"] == "VOTE_RESP":
                self.server.handle_vote_resp(msg)
            elif msg["type"] == "APPEND_ENTRIES":
                self.server.handle_append_entries(msg)