from loguru import logger

import constants
from util import request_response_handler


class DiscoveryHandler:

    def __init__(self, component):
        self.component = component

    def process_discovery_request(self, discovery_request):
        discovery_response = request_response_handler.discovery_response(discovery_request, self.component)
        requester_uuid = discovery_request["requester_uuid"]
        match discovery_request["requester_type"]:
            case constants.SERVER:
                logger.info("Received discovery request from server {}", requester_uuid)
                if requester_uuid != self.component.uuid and not self.component.discovered_servers.get(requester_uuid):
                    logger.info("Server not known {} to me, adding to list of discovered servers", requester_uuid,self.component.uuid)
                    self.add_discovered_node(requester_uuid, discovery_request, constants.DISCOVERY_REQUEST)
                else:
                    logger.info("Server {} already discovered by me", requester_uuid)
            case constants.CLIENT:
                logger.info("Received discovery request from client {}", requester_uuid)
                # only leader maintains the client list
                if not self.component.is_leader:
                    return
                self.add_discovered_node(requester_uuid, discovery_request, constants.DISCOVERY_REQUEST)
            case _:
                logger.error("Not a valid option for discovery request")
        self.component.unicast.unicast(discovery_response, discovery_request["requester_ip_address"], discovery_request["requester_port"])

    def process_discovery_response(self, discovery_response):
        respondent_uuid = discovery_response["respondent_uuid"]
        if respondent_uuid != self.component.uuid and not self.component.discovered_servers.get(
                respondent_uuid):
            logger.info("Received discovery response from {}", respondent_uuid)
            self.add_discovered_node(respondent_uuid, discovery_response, constants.DISCOVERY_RESPONSE)

        if self.component.type == constants.CLIENT:
            self.component.leader = respondent_uuid

    def add_discovered_node(self, discovered_node_uuid, discovered_node_details, operation_type):
        discovered_node = self.get_server_details(discovered_node_details, operation_type)
        logger.debug("Adding {} to known of {}", discovered_node_uuid, self.component.uuid)
        if discovered_node["type"] == constants.SERVER:
            self.component.discovered_servers[discovered_node_uuid] = discovered_node
        else:
            self.component.discovered_clients[discovered_node_uuid] = discovered_node
            # Trigger replication when a new client is discovered
            self._trigger_replication()

    def _trigger_replication(self):
        if hasattr(self.component, 'is_leader') and self.component.is_leader:
            try:
                replication_manager = self.component.replication_manager
                replication_manager.trigger_replication()
            except Exception as e:
                logger.debug("Could not trigger replication: {}", e)

    def get_server_details(self, discovered_node_details, operation_type):

        requester_types = [
            constants.DISCOVERY_REQUEST,
            constants.AUCTION_CREATE_REQUEST,
            constants.AUCTION_LIST_REQUEST,
            constants.AUCTION_JOIN_REQUEST
        ]

        return {
            "uuid": discovered_node_details["requester_uuid"]
            if operation_type in requester_types else
            discovered_node_details["respondent_uuid"],
            "hostname": discovered_node_details["requester_hostname"]
            if operation_type in requester_types else
            discovered_node_details["respondent_hostname"],
            "ip_address": discovered_node_details["requester_ip_address"]
            if operation_type in requester_types else
            discovered_node_details["respondent_ip_address"],
            "port": discovered_node_details["requester_port"]
            if operation_type in requester_types else
            discovered_node_details["respondent_port"],
            "type": discovered_node_details["requester_type"]
            if operation_type in requester_types else
            discovered_node_details["respondent_type"]
        }
