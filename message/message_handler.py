from loguru import logger
import queue
import threading

class MessageHandler:

    def __init__(self):
        self.message_queue = queue.Queue()
        self.worker_thread = None 
        self.message_handler = {}

    def register_handler(self, message_type, handler_func):
        logger.info(f"registering function for message type {message_type}")
        self.message_handler[message_type] = handler_func

    def add_message(self, msg):
        self.message_queue.put(msg)

    def start_message_handler(self):
        self.worker_thread = threading.Thread(target=self._process_message, daemon=True)
        self.worker_thread.start()

    def _process_message(self):
        while True:
            try:
                msg = self.message_queue.get(timeout=1.0)
                # self._handle_message(msg)
                self._dispatch_message(msg)
            except queue.Empty:
                continue
    
    def _dispatch_message(self, msg):
        if self.message_handler.get(msg["type"], None) is not None:
            self.message_handler.get(msg["type"])(msg)
        else:
            logger.info(f"error finding handler for message type {msg['type']}") 