import queue
import threading

from unicast.unicast import Unicast

class OutgoingMessageHandler:
    """
    Class responsible for unicasting all outgoing messages
    """

    def __init__(self, unicast_handler):
        self.message_queue = queue.Queue()
        self.worker_thread = None
        self.message_handler = {}
        self.unicast = unicast_handler

    def add_message(self, msg):
        """
        This method adds a message to the message queue
        """
        self.message_queue.put(msg)

    def start_message_handler(self):
        """
        Method spawns a thread for proces_merge (listens on the queue)
        """
        self.worker_thread = threading.Thread(target=self._process_message, daemon=True)
        self.worker_thread.start()

    def _process_message(self):
        while True:
            try:
                msg = self.message_queue.get(timeout=1.0)
                self.unicast.send_message(msg.message_type, msg.receiver, msg.data)
            except queue.Empty:
                
                continue
