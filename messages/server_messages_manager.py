import queue
import threading

from loguru import logger

import constants


class ServerMessagesManager:

    def __init__(self):
        self.queues = {
            'discovery': queue.Queue(),
            'heartbeat': queue.Queue(),
            'election': queue.Queue(),
            'client': queue.Queue(),
            'replication': queue.Queue(),
        }
        self.handlers = {}

    def register(self, message_type, handler):
        self.handlers[message_type] = handler

    def enqueue(self, message):
        match message['type']:
            case constants.DISCOVERY_REQUEST | constants.DISCOVERY_RESPONSE:
                self.queues['discovery'].put(message)
            case constants.LEADER_ACK_RESPONSE \
                | constants.LEADER_ELECTION_REQUEST \
                | constants.LEADER_ELECTION_RESPONSE \
                | constants.LEADER_ELECTION_COORDINATION_REQUEST:
                self.queues['election'].put(message)
            case constants.HEART_BEAT | constants.HEART_BEAT_ACK:
                self.queues['heartbeat'].put(message)
            case constants.AUCTION_CREATE_REQUEST \
                | constants.AUCTION_LIST_REQUEST \
                | constants.AUCTION_JOIN_REQUEST \
                | constants.AUCTION_READY_CONFIRM \
                | constants.BID_SUBMIT \
                | constants.BID_SUBMIT_RETRANSMIT:
                self.queues['client'].put(message)
            case constants.STATE_REPLICATE \
                | constants.STATE_REPLICATION_REQUEST:
                self.queues['replication'].put(message)

    def start(self):
        for queue_name in self.queues:
            threading.Thread(
                target=self.handle_queue_messages,
                args=(queue_name,),
                daemon=True
            ).start()

    def handle_queue_messages(self, queue_name):
        logger.debug("Messages manager queue {} started", queue_name)
        q = self.queues[queue_name]
        try:
            while True:
                message = q.get()
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
