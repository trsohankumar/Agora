import time

from loguru import logger

from util import request_response_handler, uuid_util
import constants

class ElectionManager:

    def __init__(self, component):
        self.component = component
        self.elections = {}

    def count_election_message(self, message, response_message):
        if self.elections.get(message["election_uuid"]):
            self.elections[message["election_uuid"]].append(response_message)
        else:
            self.elections[message["election_uuid"]] = [response_message]

    def send_election_request(self):
        server = self.component
        election_uuid = uuid_util.get_uuid()
        logger.info("Starting election with id {}", election_uuid)
        if len(server.discovered_servers) > 0:
            servers_with_larger_uuids = [
                discovered_server
                for discovered_server in server.discovered_servers.values()
                if uuid_util.get_uuid_int(discovered_server.get("uuid")) > uuid_util.get_uuid_int(server.uuid)
            ]

            if servers_with_larger_uuids:
                logger.info("Found {} servers with higher IDs", server.uuid, len(servers_with_larger_uuids))

                for target in servers_with_larger_uuids:
                    server.unicast.unicast(request_response_handler.leader_election_request(server, election_uuid), target["ip_address"], target["port"])

                # sleep to ensure that enough time has passed till we receive responses
                time.sleep(constants.ELECTION_TIMEOUT_INTERVAL)

                if self.elections.get(election_uuid):
                    logger.info("Got response from {}, waiting", self.elections.get(election_uuid))
                else:
                    logger.info("Got no response from other servers, declare self as the leader")
                    self.declare_self_as_leader(election_uuid)
            else:
                logger.info("No servers with larger uuids, declaring self as leader")
                self.declare_self_as_leader(election_uuid)
        else:
            logger.info("No other servers were discovered, declaring self as leader")
            self.declare_self_as_leader(uuid_util.get_uuid())

    def declare_self_as_leader(self, election_uuid):
        server = self.component

        if server.is_leader and server.leader == server.uuid:
            logger.debug("Already declared as leader, skipping duplicate declaration")
            return

        server.is_leader = True
        server.prev_leader = server.leader
        server.leader = server.uuid

        logger.info("Sending coordination message to other servers")
        server.broadcast.broadcast(request_response_handler.leader_election_coordination_request(election_uuid, server))

        server.heartbeat_manager.election_triggered = False

        state_restored = self.restore_state()

        if state_restored:
            logger.info("State restoration successful")
        else:
            logger.warning("No state to restore - starting with empty state")

        # Always notify known clients about the new leader
        self.notify_clients_of_new_leader()

        # Always resume any active auctions (if any exist after restoration)
        server.auction_manager.resume_active_auctions()

        # Start periodic state replication to backup servers
        logger.info("Starting periodic state replication as leader")
        server.replication_manager.start_periodic_replication()

        # Start periodic heartbeat checking for client/server failures
        server.heartbeat_manager.start_leader_heartbeat_check()

    def restore_state(self):
        server = self.component
        replication_manager = server.replication_manager

        # Try to restore from in-memory replicated state
        if replication_manager.has_replicated_state():
            logger.info("Restoring state from Primary-Backup replication")
            return replication_manager.restore_from_replicated_state()

        # Request state from peer servers if we have peers
        if len(server.discovered_servers) > 0:
            logger.info("No local state available, requesting state from peers")
            return self.request_state_from_peers()

        logger.warning("No state sources available as there are no peers")
        return False

    def request_state_from_peers(self):
        server = self.component
        replication_manager = server.replication_manager

        # Request state replication from peer servers
        for server_uuid, server_details in dict(server.discovered_servers).items():
            if server_uuid == server.uuid:
                continue

            logger.info("Requesting state replication from peer server {}", server_uuid)

            # Send a request for state replication
            server.unicast.unicast(
                request_response_handler.request_state_replication(server),
                server_details["ip_address"],
                server_details["port"]
            )

            # Wait briefly for state to arrive
            time.sleep(constants.REPLICATION_DATA_AWAIT)

            # Check if we received replicated state
            if replication_manager.has_replicated_state():
                logger.info("Received replicated state from peer {}", server_uuid)
                return replication_manager.restore_from_replicated_state()

        return False

    def notify_clients_of_new_leader(self):
        server = self.component

        leader_details = {
            "uuid": server.uuid,
            "hostname": server.unicast.host_name,
            "ip_address": server.unicast.ip_address,
            "port": server.unicast.port,
            "type": server.type
        }

        for client_uuid, client in dict(server.discovered_clients).items():
            logger.info("Notifying client {} about new leader", client_uuid)
            server.unicast.unicast(
                request_response_handler.leader_info_response(server, leader_details),
                client["ip_address"],
                client["port"]
            )

    def respond_to_election(self, message):
        server = self.component
        logger.info("Responding to election request from {}", message["requester_uuid"])
        requester_uuid = message["requester_uuid"]
        requester_details = [
            x for x in server.discovered_servers.values()
            if x["uuid"] == requester_uuid and x["uuid"] != server.uuid
        ]
        if requester_uuid != server.uuid and uuid_util.get_uuid_int(requester_uuid) < uuid_util.get_uuid_int(server.uuid) and requester_details:
            server.unicast.unicast(request_response_handler.leader_election_response(server, message), requester_details[0]["ip_address"], requester_details[0]["port"])
            # Start own election — there may be even higher-ranked servers
            self.send_election_request()

    def track_election_status(self, message):
        server = self.component
        if message["response_to"] != server.uuid:
            return
        if self.elections.get(message["election_uuid"]):
            self.elections[message["election_uuid"]].append(message["respondent_uuid"])
        else:
            self.elections[message["election_uuid"]] = [message["respondent_uuid"]]

    def handle_coordination_request(self, message):
        server = self.component
        if message["requester_uuid"] == server.uuid:
            return
        if uuid_util.get_uuid_int(message["requester_uuid"]) > uuid_util.get_uuid_int(server.uuid):
            server.is_leader = False
            if server.leader is None or uuid_util.get_uuid_int(message["requester_uuid"]) > uuid_util.get_uuid_int(server.leader):
                server.leader = message["requester_uuid"]
        else:
            server.broadcast.broadcast(request_response_handler.leader_election_coordination_request(uuid_util.get_uuid(), server))
