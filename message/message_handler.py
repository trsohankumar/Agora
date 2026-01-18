import queue
import threading

from loguru import logger

class MessageHandler:
    """
    Class responsible for registering message and dispatching
    messages to their corresponding functions
    """

    def __init__(self):
        self.message_queue = queue.Queue()
        self.worker_thread = None
        self.message_handler = {}

    def register_handler(self, message_type, handler_func):
        """
        This  method is used to register message handlers for various message type
        """
        logger.info(f"registering function for message type {message_type}")
        self.message_handler[message_type] = handler_func

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
                self._dispatch_message(msg)
            except queue.Empty:
                continue

    def _dispatch_message(self, msg):
        if self.message_handler.get(msg.message_type, None) is not None:
            self.message_handler.get(msg.message_type)(msg)
        else:
            logger.info(f"error finding handler for message type {msg.message_type}")
