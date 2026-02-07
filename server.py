import multiprocessing
import threading
import time

from loguru import logger

import constants
from broadcast.broadcast import Broadcast
from constants import SERVER
from messages.server_messages_manager import ServerMessagesManager
from udp.udp import UDP
from util import request_response_handler, uuid_util


def require_initialization(func):
    def wrapper(self, *args, **kwargs):
        if self.manager is None:
            logger.info("No manager, initializing...")
            self.initialize()
        return func(self, *args, **kwargs)

    return wrapper


class Server:

    def __init__(self):
        self.uuid = uuid_util.get_uuid()
        self.manager = None
        self.discovered_servers = {}
        self.discovered_clients = {}
        self.type = SERVER
        self.is_leader = False
        self.leader = None
        self.queues = None
        self.broadcast = Broadcast(self)
        self.udp = UDP(self)
        self.messages_manager = ServerMessagesManager(self)
        self.round_tracker = 0
        self.prev_leader = None
        logger.debug("Server {} initialized", self.uuid)

    def initialize(self):
        self.manager = multiprocessing.Manager()
        self.discovered_servers = self.manager.dict()
        self.discovered_clients = self.manager.dict()
        self.queues = request_response_handler.setup_queues(self, self.manager)

    def start_servers(self):
        logger.info("Server {} started", self.uuid)
        # self.udp.setup_multicast(multicast_ip="224.1.1.1", multicast_port=5007)
        # Start normal UDP object
        self.start_chores()

    @require_initialization
    def start_chores(self):
        threading.Thread(target=self.udp.listen, daemon=True).start()
        threading.Thread(target=self.udp.listen_multicast, daemon=True).start()
        threading.Thread(target=self.broadcast.listen, daemon=True).start()
        [threading.Thread(target=self.messages_manager.handle_queue_messages, args=(queue_name,),
                          daemon=True).start()
         for queue_name in list(self.queues.keys())]
        # Initial Broadcast for discovering other servers
        logger.info("Server {} initiating discovery", self.uuid)
        t = time.time()
        self.messages_manager.initiate_discovery()
        logger.info("Server {} waited {} seconds for discovering other servers", self.uuid, time.time() - t)
        logger.info("Server {} - Discovered {} other servers", self.uuid, len(self.discovered_servers))

        # If other servers exist, wait for state sync before election
        if len(self.discovered_servers) > 0:
            logger.info("Server {} waiting for state sync before election", self.uuid)
            self.wait_for_state_sync()

        # Trigger election
        self.messages_manager.election_manager.send_election_request(self)
        logger.info("Server {} - Leader status: {} (leader={})", self.uuid, self.is_leader, self.leader)
        print(f"Server {self.uuid[:8]}... ready")
        print(f"Is leader: {self.is_leader}")
        print(f"Listening on: {self.udp.ip_address}:{self.udp.port}")
        self.messages_manager.heartbeat_manager.send_heartbeat()
        # Period debug task to print the elected leaders
        self.print_debug_info()
        while True:
            try:
                # Optional: Add periodic logging or status checks here if needed
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
        replication_manager = self.messages_manager.replication_manager
        max_wait_time = 10  # seconds
        start_time = time.time()

        # Request state from each discovered server
        for server_uuid, server_details in dict(self.discovered_servers).items():
            logger.info("Requesting state from server {}", server_uuid)
            self.udp.unicast(
                request_response_handler.request_state_replication(self),
                server_details["ip_address"],
                server_details["port"]
            )

        # Wait for state to arrive
        while time.time() - start_time < max_wait_time:
            if replication_manager.has_replicated_state():
                logger.info("Received replicated state, ready for election")
                return True
            time.sleep(0.5)

        logger.warning("Timeout waiting for state sync after {}s", max_wait_time)
        return False

    def print_debug_info(self):
        try:
            self.round_tracker += 1
            logger.info("Server {} - Debug Info - {}", self.uuid, self.round_tracker)
            logger.info("Server {} is leader {}", self.uuid, self.is_leader)
            logger.info("Server {} - leader is {}", self.uuid, self.leader)
            logger.info("Server {} - leader details {}", self.uuid, self.discovered_servers.get(self.leader, None))
            logger.info("Server {} - discovered servers {}", self.uuid, len(list(self.discovered_servers.keys())))
            logger.info("Server {} - discovered servers list {}", self.uuid, self.discovered_servers)
            logger.info("Server {} - discovered clients {}", self.uuid, len(list(self.discovered_clients.keys())))
            logger.info("Server {} - discovered clients list {}", self.uuid, self.discovered_clients)
            logger.info("Server {} - {}:{}", self.uuid, self.udp.ip_address, self.udp.port)

            # Print the auction sessions managed by this server
            self.messages_manager.auction_manager.print_auction_sessions()

            threading.Timer(40, self.print_debug_info).start()
        except Exception as e:
            raise KeyboardInterrupt


if __name__ == "__main__":
    server = Server()
    server.start_servers()