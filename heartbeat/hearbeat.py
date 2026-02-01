import threading
import time

from loguru import logger

import constants
from util import request_response_handler


class Heartbeat:

    def __init__(self, component, heartbeat_interval):
        self.component = component
        self.heartbeat_interval = heartbeat_interval
        self.heartbeats = {}
        self.election_triggered = False
        self.failed = []
        self.connected_since = None  # Track when we connected to leader

    def find_latest_heartbeat(self):
        recents = {}
        for (server, _), timestamp in self.heartbeats.items():
            if server not in recents or timestamp > recents[server]:
                recents[server] = timestamp
        return recents

    def leader_heartbeat_info(self):
        threading.Timer(60, self.leader_heartbeat_info).start()
        recent_heartbeats = self.find_latest_heartbeat()
        for server, recent_heartbeat in recent_heartbeats.items():
            if server not in self.failed and time.time() - recent_heartbeat > constants.HEART_BEAT_TIMEOUT:
                self.failed.append(server)
                self.component.messages_manager.auction_manager.reassign_server(server)

    def send_heartbeat(self):
        threading.Timer(self.heartbeat_interval, self.send_heartbeat).start()
        # Leader is not elected or not known
        if self.component.leader is None or self.component.discovered_servers.get(self.component.leader) is None:
            logger.debug("Leader not yet known or selected, skipping heartbeat")
            self.connected_since = None  # Reset connection time
            return
        # You yourself is the leader
        if hasattr(self.component, 'is_leader') and self.component.is_leader is True:
            logger.debug("Server {} is the leader, skipping heartbeat", self.component.uuid)
            return

        # Track when we first connected
        if self.connected_since is None:
            self.connected_since = time.time()

        leader = self.component.discovered_servers.get(self.component.leader)
        heartbeat = request_response_handler.heart_beat(self.component)
        self.heartbeats[(self.component.leader, heartbeat["heart_beat_uuid"])] = heartbeat["timestamp"]
        logger.debug("{} {} -  sent heartbeat ({}) to {}", self.component.type, self.component.uuid,
                     heartbeat["heart_beat_uuid"],
                     self.component.leader)
        self.component.udp.unicast(heartbeat, leader["ip_address"], leader["port"])

        heartbeats_for_leader = [
            (leader, heartbeat_uuid) for leader, heartbeat_uuid in list(self.heartbeats.keys())
            if leader == self.component.leader
        ]
        logger.debug("{} {} has {} pending heartbeats from {}", self.component.type, self.component.uuid,
                     len(self.heartbeats),
                     self.component.leader)

        # Only trigger failure detection for servers
        # Clients will detect failure through connection errors or explicit notification
        if len(heartbeats_for_leader) > constants.MAX_MISSED_HEART_BEATS and self.component.type == constants.SERVER and not self.election_triggered:
            logger.warning("More than {} pending heartbeats, triggering leader election", constants.MAX_MISSED_HEART_BEATS)
            self.election_triggered = True
            self.heartbeats = {}
            self.component.messages_manager.election_manager.send_election_request(self.component)

    def process_heartbeat(self, heartbeat):
        if self.component.type == constants.CLIENT:
            return
        if hasattr(self.component, 'is_leader') and self.component.is_leader is False:
            logger.debug("Server {} is not the leader, skipping heartbeat processing", self.component.uuid)
            return
        self.leader_heartbeat_info()
        requester_uuid = heartbeat["requester_uuid"]
        logger.debug("{} {} got heartbeat ({}) from {}", self.component.type, self.component.uuid,
                     heartbeat["heart_beat_uuid"],
                     requester_uuid)

        # Check both discovered_servers and discovered_clients
        requester = self.component.discovered_servers.get(requester_uuid)
        if requester is None and hasattr(self.component, 'discovered_clients'):
            requester = self.component.discovered_clients.get(requester_uuid)

        if requester is None:
            logger.debug("{} {} not discovered by leader {}", self.component.type, requester_uuid, self.component.uuid)
            return
        self.heartbeats[(requester_uuid, heartbeat["heart_beat_uuid"])] = time.time()
        self.component.udp.unicast(request_response_handler.heart_beat_ack(self.component, heartbeat),
                                   requester["ip_address"], requester["port"])

    def process_heartbeat_ack(self, heartbeat_ack):
        if hasattr(self.component, 'is_leader') and self.component.is_leader is True:
            logger.debug("Server {} is the leader, skipping heartbeat ack processing", self.component.uuid)
            return
        logger.debug("{} {} - got ack heartbeat for {} from {}", self.component.type, self.component.uuid,
                     heartbeat_ack["heart_beat_uuid"], self.component.leader)
        heartbeat_uuid = heartbeat_ack["heart_beat_uuid"]
        self.heartbeats.pop((self.component.leader, heartbeat_uuid), None)

    def check_alive(self, uuid):
        if self.heartbeats.get(uuid) is None:
            return True
        return any(
            time.time() - value <= constants.HEART_BEAT_TIMEOUT for (uuid1, _), value in self.heartbeats.items() if
            uuid1 == uuid)
