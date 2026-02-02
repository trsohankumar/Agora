from loguru import logger

import constants
from discovery.discovery_handler import DiscoveryHandler
from election.election_manager import ElectionManager
from auction.server_auction_manager import ServerAuctionManager
from heartbeat.hearbeat import Heartbeat
from replication.state_replication_manager import StateReplicationManager
from snapshots.snapshots_manager import SnapshotsManager
from util import request_response_handler


class ServerMessagesManager:

    def __init__(self, server):
        self.server = server
        self.discovery_handler = DiscoveryHandler(self.server)
        self.election_manager = ElectionManager(self.server)
        self.heartbeat_manager = Heartbeat(self.server, constants.HEART_BEAT_INTERVAL)
        self.auction_manager = ServerAuctionManager(self.server)
        self.snapshots_manager = SnapshotsManager(self.server)
        self.replication_manager = StateReplicationManager(self.server)
        logger.debug("Messages manager for {} initialized", self.server.uuid)

    def handle_queue_messages(self, queue_name):
        logger.debug("Messages manager - {} Consumer for Server {} started", self.server.uuid, queue_name)
        queue = self.server.queues[queue_name]
        try:
            while True:
                if queue:
                    message = queue.pop(0)
                    logger.debug("Server {} - Messages Manager - {} Consumer recv : {}", self.server.uuid, queue_name,
                                 message)
                    self.resolve_broadcast(message)
                    self.resolve_unicast(message)
        except Exception as e:
            logger.error("Encountered exception while handling server messages : {}", e)
            raise KeyboardInterrupt
        finally:
            logger.error("Shutting down Messages Manager thread for handling server messages for {}", self.server.uuid)

    def resolve_broadcast(self, message):
        match message["type"]:
            case constants.DISCOVERY_REQUEST:
                self.discovery_handler.process_discovery_request(message)
            case constants.LEADER_ELECTION_COORDINATION_REQUEST:
                self.election_manager.handle_coordination_request(message, self.server)
            case default:
                logger.debug("Unknown message type: {}", message)

    def resolve_unicast(self, message):
        match message["type"]:
            case constants.LEADER_ELECTION_REQUEST:
                self.election_manager.respond_to_election(message, self.server)
            case constants.DISCOVERY_RESPONSE:
                self.discovery_handler.process_discovery_response(message)
            case constants.LEADER_ELECTION_RESPONSE:
                self.election_manager.track_election_status(message, self.server)
            case constants.HEART_BEAT:
                self.heartbeat_manager.process_heartbeat(message)
            case constants.HEART_BEAT_ACK:
                self.heartbeat_manager.process_heartbeat_ack(message)
            # Auction messages
            case constants.AUCTION_CREATE_REQUEST:
                self.auction_manager.create_auction(message)
                self.auction_manager.print_auction_sessions()
            case constants.AUCTION_LIST_REQUEST:
                self.auction_manager.list_auctions(message)
            case constants.AUCTION_JOIN_REQUEST:
                self.auction_manager.join_auction(message)
                self.auction_manager.print_auction_sessions()
            case constants.AUCTION_READY_CONFIRM:
                self.auction_manager.handle_ready_confirm(message)
            case constants.BID_SUBMIT | constants.BID_SUBMIT_RETRANSMIT:
                logger.info("Received bid from client")
                self.auction_manager.receive_bid(message)
            # Snapshot messages
            case constants.SNAPSHOT_MARKER:
                self.snapshots_manager.handle_marker(message)
                self.auction_manager.print_auction_sessions()
            case constants.SEND_SNAPSHOT:
                self.snapshots_manager.send_snapshot(message["component_uuid"])
            case constants.SEND_SNAPSHOT_RESPONSE:
                self.snapshots_manager.restore_latest_remote_snapshot(message)
            case constants.STATE_REPLICATE:
                self.replication_manager.receive_replicated_state(message)
            case constants.REASSIGNMENT:
                self.auction_manager.start_reassignment(message)
            case _:
                logger.debug("Unknown message type: {}", message)

    def initiate_discovery(self):
        self.server.broadcast.broadcast(request_response_handler.discovery_request(self.server))
