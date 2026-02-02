from loguru import logger

import constants
from util import request_response_handler


class DiscoveryHandler:

    def __init__(self, component):
        self.component = component

    def process_discovery_request(self, discovery_request):
        """
        Function to process a discovery request.
        For servers, it checks whether the incoming component is already known and if not adds the discovered component to it's list of known components.
        For clients, it just sends the discovery response back.
        In both cases, a discover response is sent back to the requester.
        @param discovery_request: Incoming discovery request in JSON format
        @return: NA
        """
        logger.debug("Received message {}", discovery_request)
        discovery_response = request_response_handler.discovery_response(discovery_request, self.component)
        requester_uuid = discovery_request["requester_uuid"]
        match discovery_request["requester_type"]:
            case constants.SERVER:
                logger.debug("Received discovery request from server {} to {}", requester_uuid, self.component.uuid)
                if requester_uuid != self.component.uuid and not self.component.discovered_servers.get(
                        requester_uuid):
                    logger.debug("Server not known {} to {}, adding to list of discovered servers", requester_uuid,
                                 self.component.uuid)
                    self.add_discovered_server(requester_uuid, discovery_request, constants.DISCOVERY_REQUEST)
                else:
                    logger.debug("Server {} already discovered by {}", requester_uuid, self.component.uuid)
            case constants.CLIENT:
                logger.debug("Received discovery request from client {} to {}", requester_uuid, self.component.uuid)
                if not self.component.is_leader:
                    return
                self.add_discovered_server(requester_uuid, discovery_request, constants.DISCOVERY_REQUEST)
            case _:
                logger.error("Not a valid option for discovery request")
        self.component.udp.unicast(discovery_response, discovery_request["requester_ip_address"],
                                   discovery_request["requester_port"])

    def process_discovery_response(self, discovery_response):
        """
        Function to process a discovery response.
        For both servers and clients, it adds the discovered server to the list of known servers if not present already.
        @param component_type:
        @param discovery_response:
        @param component: Incoming discovery response in JSON format
        @return: NA
        """

        respondent_uuid = discovery_response["respondent_uuid"]
        if respondent_uuid != self.component.uuid and not self.component.discovered_servers.get(
                respondent_uuid):
            logger.info("For component {}, received discovery response from {}", self.component.uuid,
                        respondent_uuid)
            self.add_discovered_server(respondent_uuid, discovery_response, constants.DISCOVERY_RESPONSE)

    def add_discovered_server(self, discovered_server_uuid, discovered_server_details, operation_type):
        discovered_server = self.get_server_details(discovered_server_details, operation_type)
        logger.debug("Adding {} to known of {}", discovered_server_uuid, self.component.uuid)
        if discovered_server["type"] == constants.SERVER:
            self.component.discovered_servers[discovered_server_uuid] = discovered_server
        else:
            self.component.discovered_clients[discovered_server_uuid] = discovered_server
            # Trigger replication when a new client is discovered
            self._trigger_replication()

    def _trigger_replication(self):
        """Trigger state replication when new client/server is discovered."""
        if hasattr(self.component, 'is_leader') and self.component.is_leader:
            try:
                replication_manager = self.component.messages_manager.replication_manager
                replication_manager.trigger_replication()
            except Exception as e:
                logger.debug("Could not trigger replication: {}", e)

    def get_server_details(self, discovered_server_details, operation_type):
        # Message types that use requester_* fields
        requester_types = [
            constants.DISCOVERY_REQUEST,
            constants.AUCTION_CREATE_REQUEST,
            constants.AUCTION_LIST_REQUEST,
            constants.AUCTION_JOIN_REQUEST
        ]

        return {
            "uuid": discovered_server_details["requester_uuid"]
            if operation_type in requester_types else
            discovered_server_details["respondent_uuid"],
            "hostname": discovered_server_details["requester_hostname"]
            if operation_type in requester_types else
            discovered_server_details["respondent_hostname"],
            "ip_address": discovered_server_details["requester_ip_address"]
            if operation_type in requester_types else
            discovered_server_details["respondent_ip_address"],
            "port": discovered_server_details["requester_port"]
            if operation_type in requester_types else
            discovered_server_details["respondent_port"],
            "type": discovered_server_details["requester_type"]
            if operation_type in requester_types else
            discovered_server_details["respondent_type"]
        }
