from loguru import logger

import constants
from discovery.discovery_handler import DiscoveryHandler
from auction.client_auction_manager import ClientAuctionManager
from heartbeat.hearbeat import Heartbeat
from util import request_response_handler


class ClientMessagesManager:

    def __init__(self, client):
        self.client = client
        self.discovery_handler = DiscoveryHandler(self.client)
        self.heartbeat_manager = Heartbeat(self.client, constants.HEART_BEAT_INTERVAL)
        self.auction_manager = ClientAuctionManager(self.client)
        logger.debug("Messages manager for {} initialized", self.client.uuid)

    def handle_queue_messages(self, queue_name):
        logger.info("Messages manager - {} Consumer for Client {} started", self.client.uuid, queue_name)
        queue = self.client.queues[queue_name]
        try:
            while True:
                if queue:
                    message = queue.pop(0)
                    logger.info("Client {} - Messages Manager - {} Consumer recv type: {}", self.client.uuid, queue_name,
                                 message.get("type", "unknown"))
                    try:
                        self.resolve_broadcast(message)
                        self.resolve_unicast(message)
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
            logger.error("Shutting down Messages Manager thread for handling client messages for {}", self.client.uuid)

    def resolve_broadcast(self, message):
        match message["type"]:
            case default:
                logger.debug("Unknown message type: {}", message)

    def resolve_unicast(self, message):
        logger.info("Client {} processing message type: {}", self.client.uuid, message.get("type"))
        match message["type"]:
            case constants.DISCOVERY_RESPONSE:
                self.discovery_handler.process_discovery_response(message)
                self.client.leader = message["respondent_uuid"]
            case constants.HEART_BEAT_ACK:
                self.heartbeat_manager.process_heartbeat_ack(message)
            # Auction creation and joining
            case constants.AUCTION_CREATE_ACK:
                self.auction_manager.handle_create_ack(message)
            case constants.AUCTION_CREATE_DENY:
                self.auction_manager.handle_create_deny(message)
            case constants.AUCTION_LIST_RESPONSE:
                self.auction_manager.handle_list_response(message)
            case constants.AUCTION_JOIN_ACK:
                self.auction_manager.handle_join_ack(message)
            case constants.AUCTION_JOIN_DENY:
                self.auction_manager.handle_join_deny(message)
            # Auction lifecycle
            case constants.AUCTION_READY_CHECK:
                self.auction_manager.handle_ready_check(message)
            case constants.AUCTION_START:
                self.auction_manager.handle_auction_start(message)
            case constants.AUCTION_CANCEL:
                self.auction_manager.handle_auction_cancel(message)
            # Bidding
            case constants.ROUND_START:
                logger.info("Client {} received ROUND_START, calling handle_round_start", self.client.uuid)
                self.auction_manager.handle_round_start(message)
                logger.info("Client {} after handle_round_start: is_bidding={}", self.client.uuid, self.auction_manager.is_bidding)
            case constants.BID_BROADCAST:
                self.auction_manager.handle_bid_broadcast(message)
            case constants.ROUND_COMPLETE:
                self.auction_manager.handle_round_complete(message)
            # Auction completion
            case constants.AUCTION_WINNER:
                self.auction_manager.handle_auction_winner(message)
            case constants.AUCTION_LOSER:
                self.auction_manager.handle_auction_loser(message)
            # Leader updates
            case constants.LEADER_DETAILS:
                leader_server = message["leader_details"]
                self.client.leader = leader_server["uuid"]
                if self.client.leader not in self.client.discovered_servers:
                    self.client.discovered_servers[leader_server["uuid"]] = leader_server
                # Set server in auction manager
                self.auction_manager.set_server(leader_server)
                # Reset heartbeat election flag since we found a new leader
                self.heartbeat_manager.election_triggered = False
                logger.info("Received new leader info: {}", leader_server["uuid"])
            case constants.REASSIGNMENT:
                self.auction_manager.reassign(message)
            case _:
                logger.debug("Unknown message type: {}", message)

    def initiate_discovery(self):
        self.client.broadcast.broadcast(request_response_handler.discovery_request(self.client))
