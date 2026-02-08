import threading

from loguru import logger

import constants


class ClientMessagesManager:

    def __init__(self):
        self.queues = {
            'client': [],
        }
        self.handlers = {}

    def register(self, message_type, handler):
        self.handlers[message_type] = handler

    def enqueue(self, message):
        self.queues['client'].append(message)

    def start(self):
        for queue_name in self.queues:
            threading.Thread(
                target=self.handle_queue_messages,
                args=(queue_name,),
                daemon=True
            ).start()

    def handle_queue_messages(self, queue_name):
        logger.info("Messages manager queue {} started", queue_name)
        queue = self.queues[queue_name]
        try:
            while True:
                if queue:
                    message = queue.pop(0)
                    logger.info("Messages Manager queue {} recv type: {}", queue_name,
                                 message.get("type", "unknown"))
                    try:
                        self.resolve_message(message)
                    except Exception as handler_error:
                        logger.error("Exception in message handler for type {}: {}", message.get("type"), handler_error)
                        import traceback
                        traceback.print_exc()
        except Exception as e:
            logger.error("Encountered exception while handling client messages : {}", e)
            import traceback
            traceback.print_exc()
            raise KeyboardInterrupt
        finally:
            logger.error("Shutting down Messages Manager thread for queue {}", queue_name)

    def resolve_message(self, message):
        handler = self.handlers.get(message["type"])
        if handler:
            handler(message)
        else:
            logger.debug("Unknown message type: {}", message)
