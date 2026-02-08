import threading

from loguru import logger

import constants


class ServerMessagesManager:

    def __init__(self):
        self.queues = {
            'discovery': [],
            'heartbeat': [],
            'election': [],
            'client': [],
            'replication': [],
        }
        self.handlers = {}

    def register(self, message_type, handler):
        self.handlers[message_type] = handler

    def enqueue(self, message):
        match message['type']:
            case constants.DISCOVERY_REQUEST | constants.DISCOVERY_RESPONSE:
                self.queues['discovery'].append(message)
            case constants.LEADER_ACK_RESPONSE \
                | constants.LEADER_ELECTION_REQUEST \
                | constants.LEADER_ELECTION_RESPONSE \
                | constants.LEADER_ELECTION_COORDINATION_REQUEST:
                self.queues['election'].append(message)
            case constants.HEART_BEAT | constants.HEART_BEAT_ACK:
                self.queues['heartbeat'].append(message)
            case constants.AUCTION_CREATE_REQUEST \
                | constants.AUCTION_LIST_REQUEST \
                | constants.AUCTION_JOIN_REQUEST \
                | constants.AUCTION_READY_CONFIRM \
                | constants.BID_SUBMIT \
                | constants.BID_SUBMIT_RETRANSMIT:
                self.queues['client'].append(message)
            case constants.STATE_REPLICATE \
                | constants.STATE_REPLICATION_REQUEST \
                | constants.REASSIGNMENT:
                self.queues['replication'].append(message)

    def start(self):
        for queue_name in self.queues:
            threading.Thread(
                target=self.handle_queue_messages,
                args=(queue_name,),
                daemon=True
            ).start()

    def handle_queue_messages(self, queue_name):
        logger.debug("Messages manager queue {} started", queue_name)
        queue = self.queues[queue_name]
        try:
            while True:
                if queue:
                    message = queue.pop(0)
                    logger.debug("Message Manager queue: {} recieved a message: {}", queue_name, message)
                    self.resolve_message(message)
        except Exception as e:
            logger.error("Encountered exception while handling server messages : {}", e)
            raise KeyboardInterrupt
        finally:
            logger.error("Shutting down Messages Manager thread for queue {}", queue_name)

    def resolve_message(self, message):
        handler = self.handlers.get(message["type"])
        if handler:
            handler(message)
        else:
            logger.debug("Unknown message type: {}", message)
