import multiprocessing
import random
import threading
import time

from loguru import logger

import constants
from util import request_response_handler, copy_utils, uuid_util
from util.network_util import get_multicast_address


def require_initialization(func):
    def wrapper(self, *args, **kwargs):
        if self.manager is None:
            logger.info("No manager, initializing...")
            self.initialize()
        return func(self, *args, **kwargs)

    return wrapper


class ServerAuctionManager:

    def __init__(self, server):
        self.server = server
        self.manager = None
        self.auctions = {}  # auction_id -> auction data
        self.clients = {}   # client_uuid -> client connection details
        self.assignments = {}  # server_uuid -> list of auction_ids

    def initialize(self):
        self.manager = multiprocessing.Manager()
        self.auctions = self.manager.dict()
        self.clients = self.manager.dict()
        self.assignments = self.manager.dict()

    @require_initialization
    def create_auction(self, message):
        """Handle auction creation request from client (auctioneer)."""
        client_uuid = message["requester_uuid"]
        logger.info("Received auction create request from client {}", client_uuid)

        if not self.server.is_leader:
            self.send_actual_leader_info_to_client(message)
            return

        # Store client details
        client = self.server.messages_manager.discovery_handler.get_server_details(
            message, constants.AUCTION_CREATE_REQUEST
        )
        self.clients[client_uuid] = client
        self.server.discovered_clients[client_uuid] = client

        # Check if client is already in an active auction
        for auction_id, auction in dict(self.auctions).items():
            if auction["status"] not in ("waiting", "active"):
                continue
            if auction["auctioneer_uuid"] == client_uuid or client_uuid in list(auction["participants"]):
                logger.warning("Client {} is already in auction {}. Denying request.", client_uuid, auction_id)
                self.server.udp.unicast(
                    request_response_handler.auction_create_deny(
                        self.server, "You are already in an active auction."
                    ),
                    client["ip_address"], client["port"]
                )
                return

        # Create new auction
        auction_id = uuid_util.get_uuid()
        multicast_ip = get_multicast_address()
        multicast_port = random.randint(49152, 65535)

        auction = self.manager.dict({
            "auction_id": auction_id,
            "item_name": message["item_name"],
            "min_bid_price": message["min_bid_price"],
            "min_rounds": message["min_rounds"],
            "min_bidders": message["min_bidders"],
            "auctioneer_uuid": client_uuid,
            "participants": self.manager.list([client_uuid]),
            "current_round": 0,
            "bids": self.manager.dict(),
            "status": "waiting",
            "multicast_ip": multicast_ip,
            "multicast_port": multicast_port
        })

        self.auctions[auction_id] = auction
        logger.info("Created auction {} for item '{}' by auctioneer {}",
                   auction_id, message["item_name"], client_uuid)

        # Send acknowledgment to auctioneer
        self.server.udp.unicast(
            request_response_handler.auction_create_ack(
                self.server, auction_id, message["item_name"],
                message["min_bid_price"], message["min_rounds"],
                message["min_bidders"], multicast_ip, multicast_port
            ),
            client["ip_address"], client["port"]
        )

        # Trigger state replication to backups
        self._trigger_replication()

    @require_initialization
    def list_auctions(self, message):
        """Handle auction list request from client."""
        client_uuid = message["requester_uuid"]
        logger.info("Received auction list request from client {}", client_uuid)

        if not self.server.is_leader:
            self.send_actual_leader_info_to_client(message)
            return

        # Store client details
        client = self.server.messages_manager.discovery_handler.get_server_details(
            message, constants.AUCTION_LIST_REQUEST
        )
        self.clients[client_uuid] = client
        self.server.discovered_clients[client_uuid] = client

        # Get available auctions (status = "waiting")
        available_auctions = []
        for auction_id, auction in dict(self.auctions).items():
            if auction["status"] == "waiting":
                available_auctions.append({
                    "auction_id": auction_id,
                    "item_name": auction["item_name"],
                    "min_bid_price": float(auction["min_bid_price"]),
                    "min_rounds": int(auction["min_rounds"]),
                    "min_bidders": int(auction["min_bidders"]),
                    "current_bidders": len(list(auction["participants"])),
                    "auctioneer_uuid": auction["auctioneer_uuid"]
                })

        self.server.udp.unicast(
            request_response_handler.auction_list_response(self.server, available_auctions),
            client["ip_address"], client["port"]
        )

    @require_initialization
    def join_auction(self, message):
        """Handle auction join request from client (bidder)."""
        client_uuid = message["requester_uuid"]
        auction_id = message["auction_id"]
        logger.info("Received auction join request from client {} for auction {}", client_uuid, auction_id)

        if not self.server.is_leader:
            self.send_actual_leader_info_to_client(message)
            return

        # Store client details
        client = self.server.messages_manager.discovery_handler.get_server_details(
            message, constants.AUCTION_JOIN_REQUEST
        )
        self.clients[client_uuid] = client
        self.server.discovered_clients[client_uuid] = client

        # Check if auction exists
        if auction_id not in self.auctions:
            logger.warning("Auction {} not found. Denying join request.", auction_id)
            self.server.udp.unicast(
                request_response_handler.auction_join_deny(self.server, "Auction not found."),
                client["ip_address"], client["port"]
            )
            return

        auction = self.auctions[auction_id]

        # Check if auction is still waiting
        if auction["status"] != "waiting":
            logger.warning("Auction {} is not accepting new bidders. Status: {}", auction_id, auction["status"])
            self.server.udp.unicast(
                request_response_handler.auction_join_deny(
                    self.server, "Auction is no longer accepting new bidders."
                ),
                client["ip_address"], client["port"]
            )
            return

        # Check if client is already in this auction
        if client_uuid in list(auction["participants"]):
            logger.warning("Client {} is already in auction {}.", client_uuid, auction_id)
            self.server.udp.unicast(
                request_response_handler.auction_join_deny(
                    self.server, "You are already in this auction."
                ),
                client["ip_address"], client["port"]
            )
            return

        # Add client to auction
        auction["participants"].append(client_uuid)
        logger.info("Client {} joined auction {}. Current participants: {}",
                   client_uuid, auction_id, len(list(auction["participants"])))

        # Send join acknowledgment
        self.server.udp.unicast(
            request_response_handler.auction_join_ack(
                self.server, auction_id, auction["item_name"],
                auction["min_bid_price"], auction["min_rounds"],
                auction["multicast_ip"], auction["multicast_port"]
            ),
            client["ip_address"], client["port"]
        )

        # Trigger state replication to backups
        self._trigger_replication()

        # Check if we have enough bidders to start
        if len(list(auction["participants"])) >= auction["min_bidders"]:
            self.send_ready_check(auction_id)

    @require_initialization
    def send_ready_check(self, auction_id):
        """Send ready check to auctioneer when minimum bidders reached."""
        auction = self.auctions[auction_id]
        auctioneer_uuid = auction["auctioneer_uuid"]

        if auctioneer_uuid not in self.clients:
            logger.warning("Auctioneer {} not found in clients. Cancelling auction.", auctioneer_uuid)
            self.cancel_auction(auction_id, "Auctioneer is no longer available.")
            return

        auctioneer = self.clients[auctioneer_uuid]

        logger.info("Minimum bidders reached for auction {}. Sending ready check to auctioneer.", auction_id)

        # Record when ready check was sent for timeout tracking
        auction["ready_check_time"] = time.time()

        self.server.udp.unicast(
            request_response_handler.auction_ready_check(
                self.server, auction_id, len(list(auction["participants"]))
            ),
            auctioneer["ip_address"], auctioneer["port"]
        )

        # Start timeout timer - auction will be cancelled if not started within timeout
        threading.Timer(
            constants.AUCTION_START_TIMEOUT,
            self.check_auction_start_timeout,
            args=[auction_id]
        ).start()
        logger.info("Started {}s timeout timer for auction {}", constants.AUCTION_START_TIMEOUT, auction_id)

    @require_initialization
    def check_auction_start_timeout(self, auction_id):
        """Check if auction has timed out waiting for auctioneer to start."""
        if auction_id not in self.auctions:
            logger.debug("Auction {} no longer exists, skipping timeout check", auction_id)
            return

        auction = self.auctions[auction_id]

        # Only cancel if still in waiting status
        if auction.get("status") == "waiting":
            ready_check_time = auction.get("ready_check_time", 0)
            elapsed = time.time() - ready_check_time

            if elapsed >= constants.AUCTION_START_TIMEOUT:
                logger.warning("Auction {} timed out after {}s waiting for auctioneer to confirm start",
                             auction_id, int(elapsed))
                self.cancel_auction(
                    auction_id,
                    f"Auction timed out: Auctioneer did not start the auction within {constants.AUCTION_START_TIMEOUT} seconds."
                )
        else:
            logger.debug("Auction {} already started (status: {}), timeout check passed", auction_id, auction.get("status"))

    @require_initialization
    def handle_ready_confirm(self, message):
        """Handle ready confirmation from auctioneer."""
        auction_id = message["auction_id"]
        client_uuid = message["requester_uuid"]

        if auction_id not in self.auctions:
            logger.warning("Auction {} not found for ready confirm.", auction_id)
            return

        auction = self.auctions[auction_id]

        if auction["auctioneer_uuid"] != client_uuid:
            logger.warning("Client {} is not the auctioneer of auction {}.", client_uuid, auction_id)
            return

        logger.info("Auctioneer confirmed ready for auction {}. Starting auction.", auction_id)
        self.start_auction(auction_id)

    @require_initialization
    def start_auction(self, auction_id):
        """Start the auction and begin bidding."""
        auction = self.auctions[auction_id]
        auction["status"] = "active"
        auction["current_round"] = 1
        auction["bids"][1] = self.manager.dict()

        logger.info("Starting auction {} for item '{}'", auction_id, auction["item_name"])

        # Set up multicast for all participants
        for participant_uuid in list(auction["participants"]):
            if participant_uuid in self.clients:
                participant = self.clients[participant_uuid]
                copy_utils.add_item_to_dict(self.clients, participant_uuid, "multicast_port", auction["multicast_port"])
                copy_utils.add_item_to_dict(self.clients, participant_uuid, "multicast_ip", auction["multicast_ip"])

        # Notify all participants that auction is starting via unicast
        auction_start_msg = request_response_handler.auction_start(
            self.server, auction_id, auction["item_name"],
            auction["min_bid_price"], auction["min_rounds"],
            list(auction["participants"]),
            auction["multicast_ip"], auction["multicast_port"]
        )

        # Get all participant details
        participants_list = list(auction["participants"])
        logger.info("AUCTION_START - Participants: {}", participants_list)

        recipients = []
        for participant_uuid in participants_list:
            if participant_uuid in self.clients:
                recipients.append(self.clients[participant_uuid])
                logger.info("Will send AUCTION_START to {} at {}:{}",
                           participant_uuid,
                           self.clients[participant_uuid]["ip_address"],
                           self.clients[participant_uuid]["port"])
            else:
                logger.warning("Participant {} NOT found in clients for AUCTION_START!", participant_uuid)

        # Send to all without blocking
        logger.info("Sending AUCTION_START to {} recipients", len(recipients))
        self.server.udp.send_to_all(auction_start_msg, recipients)

        # Small delay to ensure AUCTION_START is processed before ROUND_START
        time.sleep(0.5)

        # Start first round
        self.start_round(auction_id)

    @require_initialization
    def start_round(self, auction_id):
        """Start a new bidding round."""
        auction = self.auctions[auction_id]
        current_round = auction["current_round"]

        logger.info("Starting round {} for auction {}", current_round, auction_id)

        # Initialize bids dict for this round if not exists
        if current_round not in auction["bids"]:
            auction["bids"][current_round] = self.manager.dict()

        round_start_msg = request_response_handler.round_start(
            self.server, auction_id, current_round,
            auction["min_bid_price"]
        )

        # Get all participant details
        participants_list = list(auction["participants"])
        logger.info("Participants in auction: {}", participants_list)
        logger.info("Clients known to server: {}", list(self.clients.keys()))

        recipients = []
        for participant_uuid in participants_list:
            if participant_uuid in self.clients:
                recipients.append(self.clients[participant_uuid])
                logger.info("Will send ROUND_START to participant {} at {}:{}",
                           participant_uuid,
                           self.clients[participant_uuid]["ip_address"],
                           self.clients[participant_uuid]["port"])
            else:
                logger.warning("Participant {} NOT found in clients!", participant_uuid)

        # Send to all without blocking
        logger.info("Sending ROUND_START to {} recipients", len(recipients))
        self.server.udp.send_to_all(round_start_msg, recipients)

    @require_initialization
    def receive_bid(self, message):
        """Process a bid submission from a client."""
        client_uuid = message["requester_uuid"]
        auction_id = message["auction_id"]
        bid_amount = message["bid_amount"]
        round_num = message["round"]

        if auction_id not in self.auctions:
            logger.warning("Auction {} not found for bid.", auction_id)
            return

        auction = self.auctions[auction_id]

        if auction["status"] != "active":
            logger.warning("Auction {} is not active. Ignoring bid.", auction_id)
            return

        if round_num != auction["current_round"]:
            logger.warning("Bid for wrong round. Expected {}, got {}.", auction["current_round"], round_num)
            return

        if client_uuid not in list(auction["participants"]):
            logger.warning("Client {} is not a participant in auction {}.", client_uuid, auction_id)
            return

        if bid_amount < auction["min_bid_price"]:
            logger.warning("Bid amount {} is below minimum {}. Rejecting.", bid_amount, auction["min_bid_price"])
            # Still accept the bid but it will be recorded as the minimum
            bid_amount = auction["min_bid_price"]

        # Record the bid
        auction["bids"][round_num][client_uuid] = bid_amount
        logger.info("Recorded bid of {} from {} for auction {} round {}",
                   bid_amount, client_uuid, auction_id, round_num)

        # Trigger state replication to backups (bid is critical state)
        self._trigger_replication()

        # Broadcast the bid to all participants via unicast
        bid_msg = request_response_handler.bid_broadcast(
            self.server, auction_id, round_num, client_uuid, bid_amount
        )
        recipients = [self.clients[p] for p in list(auction["participants"]) if p in self.clients]
        self.server.udp.send_to_all(bid_msg, recipients)

        # Check if all bids are in for this round
        self.check_round_complete(auction_id)

    @require_initialization
    def check_round_complete(self, auction_id):
        """Check if all participants have submitted bids for current round."""
        auction = self.auctions[auction_id]
        current_round = auction["current_round"]
        participants = list(auction["participants"])
        round_bids = dict(auction["bids"].get(current_round, {}))

        if len(round_bids) == len(participants):
            logger.info("All bids received for auction {} round {}", auction_id, current_round)

            # Send round complete to all participants via unicast
            round_complete_msg = request_response_handler.round_complete(
                self.server, auction_id, current_round, round_bids
            )
            recipients = [self.clients[p] for p in participants if p in self.clients]
            self.server.udp.send_to_all(round_complete_msg, recipients)

            # Check if we've completed minimum rounds
            if current_round >= auction["min_rounds"]:
                self.complete_auction(auction_id)
            else:
                # Start next round
                auction["current_round"] = current_round + 1
                auction["bids"][auction["current_round"]] = self.manager.dict()
                self.start_round(auction_id)

    @require_initialization
    def complete_auction(self, auction_id):
        """Complete the auction and determine winner."""
        auction = self.auctions[auction_id]
        auction["status"] = "completed"

        winner, winning_amount = self.calculate_winner(auction)
        logger.info("Auction {} completed. Winner: {} with total bid: {}",
                   auction_id, winner, winning_amount)

        # Trigger state replication to backups (auction completion is critical)
        self._trigger_replication()

        # Build results for all participants
        cumulative_bids = self._get_cumulative_bids(auction)

        # Notify each participant
        for participant_uuid in list(auction["participants"]):
            if participant_uuid in self.clients:
                participant = self.clients[participant_uuid]
                if participant_uuid == winner:
                    self.server.udp.unicast(
                        request_response_handler.auction_winner(
                            self.server, auction_id, auction["item_name"],
                            winning_amount, cumulative_bids
                        ),
                        participant["ip_address"], participant["port"]
                    )
                else:
                    self.server.udp.unicast(
                        request_response_handler.auction_loser(
                            self.server, auction_id, auction["item_name"],
                            winner, winning_amount, cumulative_bids
                        ),
                        participant["ip_address"], participant["port"]
                    )

    def calculate_winner(self, auction):
        """Calculate winner based on highest cumulative bid."""
        cumulative = self._get_cumulative_bids(auction)
        if not cumulative:
            return None, 0
        winner = max(cumulative, key=cumulative.get)
        return winner, cumulative[winner]

    def _get_cumulative_bids(self, auction):
        """Calculate cumulative bids for all participants."""
        cumulative = {}
        bids_dict = dict(auction["bids"])
        for round_num, round_bids in bids_dict.items():
            for client_uuid, amount in dict(round_bids).items():
                cumulative[client_uuid] = cumulative.get(client_uuid, 0) + amount
        return cumulative

    @require_initialization
    def broadcast_to_auction(self, auction_id, message):
        """Broadcast a message to all auction participants via multicast."""
        auction = self.auctions[auction_id]
        multicast_ip = auction["multicast_ip"]
        multicast_port = auction["multicast_port"]

        logger.info("Broadcasting {} to auction {} at {}:{}", message.get("type"), auction_id, multicast_ip, multicast_port)
        self.server.udp.multicast(message, multicast_ip, multicast_port)

    @require_initialization
    def send_actual_leader_info_to_client(self, message):
        """Send leader info to client when this server is not the leader."""
        logger.debug("Server {} is not the leader, sending leader info to client", self.server.uuid)
        if self.server.leader and self.server.leader in self.server.discovered_servers:
            leader_details = self.server.discovered_servers[self.server.leader]
            client = self.server.messages_manager.discovery_handler.get_server_details(
                message, message["type"]
            )
            self.server.udp.unicast(
                request_response_handler.leader_info_response(self.server, leader_details),
                client["ip_address"],
                client["port"]
            )
            logger.info("Sent leader info ({}:{}) to client {}",
                       leader_details["ip_address"],
                       leader_details["port"],
                       message["requester_uuid"])
        else:
            logger.error("Leader details not available. Cannot inform client.")

    @require_initialization
    def resume_active_auctions(self):
        """Resume any active auctions after becoming the new leader."""
        for auction_id, auction in dict(self.auctions).items():
            if auction.get("status") == "active":
                logger.info("Resuming active auction {} for item '{}'", auction_id, auction.get("item_name"))

                multicast_ip = auction.get("multicast_ip")
                multicast_port = auction.get("multicast_port")

                # Notify all participants that auction is resuming
                for participant_uuid in list(auction.get("participants", [])):
                    if participant_uuid in self.clients:
                        participant = self.clients[participant_uuid]
                        # Send auction start again to re-establish connection (includes multicast info)
                        self.server.udp.unicast(
                            request_response_handler.auction_start(
                                self.server, auction_id, auction["item_name"],
                                auction["min_bid_price"], auction["min_rounds"],
                                list(auction["participants"]),
                                multicast_ip, multicast_port
                            ),
                            participant["ip_address"], participant["port"]
                        )

                # Resume the current round
                current_round = auction.get("current_round", 1)
                logger.info("Resuming auction {} at round {}", auction_id, current_round)
                self.start_round(auction_id)

    @require_initialization
    def print_auction_sessions(self):
        """Log active auction sessions."""
        if not self.auctions:
            logger.info("No active auction sessions.")
        else:
            logger.info("Current Auction Sessions:")
            for auction_id, auction in dict(self.auctions).items():
                logger.info("  Auction ID: {} | Item: {} | Status: {} | Participants: {} | Round: {}",
                           auction_id, auction["item_name"], auction["status"],
                           len(list(auction["participants"])), auction["current_round"])

    @require_initialization
    def cancel_auction(self, auction_id, reason="Auction cancelled"):
        """Cancel an auction and notify all participants."""
        if auction_id not in self.auctions:
            return

        auction = self.auctions[auction_id]
        item_name = auction.get("item_name", "Unknown")
        participants = list(auction.get("participants", []))

        auction["status"] = "cancelled"

        logger.info("Cancelling auction {} for '{}'. Reason: {}", auction_id, item_name, reason)

        # Notify all participants
        for participant_uuid in participants:
            if participant_uuid in self.clients:
                participant = self.clients[participant_uuid]
                self.server.udp.unicast(
                    request_response_handler.auction_cancel(self.server, auction_id, reason),
                    participant["ip_address"], participant["port"]
                )
                logger.debug("Notified participant {} about auction cancellation", participant_uuid)

        # Remove the cancelled auction from active auctions
        del self.auctions[auction_id]
        logger.info("Auction {} removed from active auctions", auction_id)

    def reassign_server(self, failed_server):
        """Notify other servers about a failed server."""
        logger.info("Server {} failed, initiating reassignment", failed_server)

        # Check if the failed server had any auctions
        for auction_id, auction in dict(self.auctions).items():
            # If this server is the new leader, it needs to take over
            if self.server.is_leader:
                logger.info("Taking over auction {} from failed server", auction_id)

        # Notify other servers about the failure
        for server_uuid, server_details in dict(self.server.discovered_servers).items():
            if server_uuid != failed_server:
                self.server.udp.unicast(
                    request_response_handler.reassignment(failed_server, self.server),
                    server_details["ip_address"],
                    server_details["port"]
                )

    def start_reassignment(self, message):
        """Handle reassignment after server failure."""
        failed_server = message["failed_uuid"] if "failed_uuid" in message else message["requester_uuid"]
        logger.info("Starting reassignment process for failed server {}", failed_server)

        replication_manager = self.server.messages_manager.replication_manager
        existing_clients = dict(self.clients)

        # Restore from replicated state if available
        if replication_manager.has_replicated_state():
            logger.info("Restoring state from replication for reassignment")
            replication_manager.restore_from_replicated_state()

        # Notify clients that were connected to the failed server
        for client, client_details in self.clients.items():
            if client not in existing_clients:
                self.server.udp.unicast(
                    request_response_handler.auction_reassignment(self.server),
                    client_details["ip_address"], client_details["port"]
                )

    def _trigger_replication(self):
        """Trigger immediate state replication to backup servers."""
        if self.server.is_leader:
            try:
                replication_manager = self.server.messages_manager.replication_manager
                replication_manager.trigger_replication()
            except Exception as e:
                logger.warning("Failed to trigger replication: {}", e)
