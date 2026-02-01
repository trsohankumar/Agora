from loguru import logger

from util import request_response_handler, uuid_util


class ElectionManager:

    def __init__(self, component):
        self.component = component
        self.elections = {}

    def count_election_message(self, message, response_message):
        if self.elections.get(message["election_uuid"]):
            self.elections[message["election_uuid"]].append(response_message)
        else:
            self.elections[message["election_uuid"]] = [response_message]

    def send_election_request(self, server):
        logger.debug("Starting election")
        if server.discovered_servers:
            logger.debug("Other servers were discovered by {}", server.uuid)
            election_uuid = uuid_util.get_uuid()
            logger.info("Starting election {}, triggered by {}", election_uuid, server.uuid)
            servers_with_larger_uuids = [
                discovered_server
                for discovered_server in server.discovered_servers.values()
                if uuid_util.get_uuid_int(discovered_server.get("uuid")) > uuid_util.get_uuid_int(server.uuid)
            ]

            logger.debug("Server {} have others {}", server.uuid, servers_with_larger_uuids)

            if servers_with_larger_uuids:
                logger.info("Server {} - Found {} servers with higher IDs", server.uuid, len(servers_with_larger_uuids))
                for target in servers_with_larger_uuids:
                    server.udp.unicast(request_response_handler.leader_election_request(server, election_uuid),
                                       target["ip_address"],
                                       target["port"])
                # time.sleep(UNICAST_TIMEOUT)
                if self.elections.get(election_uuid):
                    logger.info("Server {} - Got response from {}, waiting", self.component.uuid,
                                self.elections.get(election_uuid))
                else:
                    logger.info("Server {} - Got no response from other servers, declare self as the leader",
                                self.component.uuid)
                    self.declare_self_as_leader(server, election_uuid)
            else:
                logger.info("Server {} - No servers with larger uuids, declaring self as leader", self.component.uuid)
                self.declare_self_as_leader(server, election_uuid)
        else:
            logger.info("Server {} - No other servers were discovered, declaring self as leader", self.component.uuid)
            self.declare_self_as_leader(server, uuid_util.get_uuid())

    def declare_self_as_leader(self, server, election_uuid):
        server.is_leader = True
        restore_snapshot = False
        if server.leader:
            server.prev_leader = server.leader
            restore_snapshot = True
        server.leader = server.uuid
        server.broadcast.broadcast(request_response_handler.leader_election_coordination_request(election_uuid, server))
        server.messages_manager.heartbeat_manager.election_triggered = False
        if restore_snapshot:
            snapshots_manager = server.messages_manager.snapshots_manager
            if snapshots_manager.is_snapshot_local(server.prev_leader):
                snapshots_manager.restore_latest_snapshot(server.prev_leader, False)
            else:
                snapshots_manager.snapshot_restored = True
                snapshots_manager.restore_latest_snapshot(server.prev_leader, True)

            # Notify known clients about the new leader
            self.notify_clients_of_new_leader(server)

            # Resume any active auctions
            server.messages_manager.auction_manager.resume_active_auctions()

    def notify_clients_of_new_leader(self, server):
        """Notify all known clients about the new leader."""
        leader_details = {
            "uuid": server.uuid,
            "hostname": server.udp.host_name,
            "ip_address": server.udp.ip_address,
            "port": server.udp.port,
            "type": server.type
        }
        for client_uuid, client in dict(server.discovered_clients).items():
            logger.info("Notifying client {} about new leader", client_uuid)
            server.udp.unicast(
                request_response_handler.leader_info_response(server, leader_details),
                client["ip_address"],
                client["port"]
            )

    # def declare_self_as_leader_without_restore(self, server, election_uuid):
    #     server.is_leader = True
    #     server.leader = server.uuid
    #     server.broadcast.broadcast(request_response_handler.leader_election_coordination_request(election_uuid, server))

    def respond_to_election(self, message, server):
        logger.info("Responding to election request from {}", message["requester_uuid"])
        requester_uuid = message["requester_uuid"]
        requester_details = [
            x for x in server.discovered_servers.values()
            if x["uuid"] == requester_uuid and x["uuid"] != server.uuid
        ]
        if requester_uuid != server.uuid and uuid_util.get_uuid_int(requester_uuid) < uuid_util.get_uuid_int(
                server.uuid) and requester_details:
            server.udp.unicast(request_response_handler.leader_election_response(server, message),
                               requester_details[0]["ip_address"], requester_details[0]["port"])
        self.declare_self_as_leader(server, uuid_util.get_uuid())

    def track_election_status(self, message, server):
        if message["response_to"] != server.uuid:
            return
        if self.elections.get(message["election_uuid"]):
            self.elections[message["election_uuid"]].append(message["respondent_uuid"])
        else:
            self.elections[message["election_uuid"]] = [message["respondent_uuid"]]

    def handle_coordination_request(self, message, server):
        if message["requester_uuid"] == server.uuid:
            return
        if uuid_util.get_uuid_int(message["requester_uuid"]) > uuid_util.get_uuid_int(server.uuid):
            server.is_leader = False
            if server.leader:
                if uuid_util.get_uuid_int(message["requester_uuid"]) > uuid_util.get_uuid_int(server.leader):
                    server.leader = message["requester_uuid"]
            else:
                server.leader = message["requester_uuid"]
        else:
            server.broadcast.broadcast(
                request_response_handler.leader_election_coordination_request(uuid_util.get_uuid(), server))
