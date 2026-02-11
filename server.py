import sys
import threading
import time

from loguru import logger

import constants
from auction.server_auction_manager import ServerAuctionManager
from broadcast.broadcast import Broadcast
from constants import SERVER
from discovery.discovery_handler import DiscoveryHandler
from election.election_manager import ElectionManager
from heartbeat.hearbeat import Heartbeat
from messages.server_messages_manager import ServerMessagesManager
from replication.state_replication_manager import StateReplicationManager
from unicast.unicast import Unicast
from util import request_response_handler, uuid_util


logger.remove()
logger.add(sys.stderr, level=20)


class Server:

    def __init__(self):
        self.uuid = uuid_util.get_uuid()
        self.discovered_servers = {}
        self.discovered_clients = {}
        self.type = SERVER
        self.is_leader = False
        self.leader = None
        self.discovery_handler = DiscoveryHandler(self)
        self.election_manager = ElectionManager(self)
        self.heartbeat_manager = Heartbeat(self, constants.HEART_BEAT_INTERVAL)
        self.auction_manager = ServerAuctionManager(self)
        self.replication_manager = StateReplicationManager(self)
        self.messages_manager = ServerMessagesManager()
        self.broadcast = Broadcast(self.messages_manager)
        self.unicast = Unicast(self.messages_manager)
        self.round_tracker = 0
        self.prev_leader = None
        logger.debug("Server {} initialized", self.uuid)

    def _register_message_handlers(self):
        mm = self.messages_manager
        # Discovery
        mm.register(constants.DISCOVERY_REQUEST, self.discovery_handler.process_discovery_request)
        mm.register(constants.DISCOVERY_RESPONSE, self.discovery_handler.process_discovery_response)
        # Election
        mm.register(constants.LEADER_ELECTION_COORDINATION_REQUEST, self.election_manager.handle_coordination_request)
        mm.register(constants.LEADER_ELECTION_REQUEST, self.election_manager.respond_to_election)
        mm.register(constants.LEADER_ELECTION_RESPONSE, self.election_manager.track_election_status)
        # Heartbeat
        mm.register(constants.HEART_BEAT, self.heartbeat_manager.process_heartbeat)
        mm.register(constants.HEART_BEAT_ACK, self.heartbeat_manager.process_heartbeat_ack)
        # Auction
        mm.register(constants.AUCTION_CREATE_REQUEST, self.auction_manager.create_auction)
        mm.register(constants.AUCTION_LIST_REQUEST, self.auction_manager.list_auctions)
        mm.register(constants.AUCTION_JOIN_REQUEST, self.auction_manager.join_auction)
        mm.register(constants.AUCTION_READY_CONFIRM, self.auction_manager.handle_ready_confirm)
        mm.register(constants.BID_SUBMIT, self.auction_manager.receive_bid)
        mm.register(constants.BID_SUBMIT_RETRANSMIT, self.auction_manager.receive_bid)
        # Replication
        mm.register(constants.STATE_REPLICATE, self.replication_manager.receive_replicated_state)
        mm.register(constants.STATE_REPLICATION_REQUEST, self.replication_manager.handle_state_request)

    def start_server(self):
        logger.info("Server {} started", self.uuid)
        self._register_message_handlers()
        self.start_chores()

    def start_chores(self):
        threading.Thread(target=self.unicast.listen, daemon=True).start()
        threading.Thread(target=self.broadcast.listen, daemon=True).start()
        
        self.messages_manager.start()


        # Initial Broadcast for discovering other servers
        logger.info("Server {} initiating discovery", self.uuid)
        t = time.time()
        self.initiate_discovery()
        
        logger.info("Server {} waited {} seconds for discovering other servers", self.uuid, time.time() - t)
        logger.info("Discovery Complete")
        logger.info("Discovered {} other servers", len(self.discovered_servers))

        # If other servers exist, wait for state sync before election
        if len(self.discovered_servers) > 0:
            logger.info("Server {} waiting for state sync before election", self.uuid)
            self.wait_for_state_sync()

        # Trigger election
        self.election_manager.send_election_request()
        logger.info("Server {} - Leader status: {} (leader={})", self.uuid, self.is_leader, self.leader)


        # start sending heartbeats now
        self.heartbeat_manager.send_heartbeat()


        while True:
            try:
                time.sleep(1)
                logger.trace("Main is running")
            except KeyboardInterrupt:
                logger.info("Main thread caught KeyboardInterrupt. Shutting down gracefully.")
                raise

    def wait_for_state_sync(self):
        """
        Wait to receive state from existing leader before participating in election.
        This prevents a new server with higher UUID from becoming leader without state.
        """
        replication_manager = self.replication_manager
        max_wait_time = 10  # seconds
        start_time = time.time()

        # Request state from each discovered server
        for server_uuid, server_details in dict(self.discovered_servers).items():
            logger.info("Requesting state from server {}", server_uuid)
            self.unicast.unicast(
                request_response_handler.request_state_replication(self),
                server_details["ip_address"],
                server_details["port"]
            )

        # Wait for state to arrive
        while time.time() - start_time < max_wait_time:
            if replication_manager.has_replicated_state():
                logger.info("Received replicated state, ready for election")
                break
            time.sleep(0.5)
        else:
            logger.warning("Timeout waiting for state sync after {}s", max_wait_time)

    def initiate_discovery(self):
        self.broadcast.broadcast(request_response_handler.discovery_request(self))

if __name__ == "__main__":
    server = Server()
    server.start_server()