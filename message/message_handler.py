from loguru import logger
import queue
import threading

class MessageHandler:

    def __init__(self):
        self.message_queue = queue.Queue()
        self.worker_thread = None 
        pass

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
        logger.info(f"Handling message: {msg}")
        
