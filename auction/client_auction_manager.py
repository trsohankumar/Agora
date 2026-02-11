import time

from loguru import logger

from util import request_response_handler


class ClientAuctionManager:

    def __init__(self, client):
        self.client = client
        self.server = None
        self.auction_id = None
        self.is_auctioneer = False
        self.item_name = None
        self.min_bid_price = 0
        self.min_rounds = 0
        self.current_round = 0
        self.my_bids = {}
        self.all_bids = {}  # round -> {client_uuid: amount}
        self.participants = []
        self.is_finished = False
        self.won = None
        self.is_active = False
        self.is_waiting_for_start = False
        self.is_bidding = False
        self.available_auctions = []
        self.last_bid_time = None
        self.ready_to_confirm = False

    def create_auction(self, item_name, min_bid_price, min_rounds, min_bidders):
        """Send auction creation request to server."""
        if not self.server:
            logger.error("No server connection. Cannot create auction.")
            return False

        logger.info("Creating auction for item '{}' with min_bid={}, min_rounds={}, min_bidders={}",
                   item_name, min_bid_price, min_rounds, min_bidders)

        self.client.unicast.unicast(
            request_response_handler.auction_create_request(
                self.client, item_name, min_bid_price, min_rounds, min_bidders
            ),
            self.server["ip_address"], self.server["port"]
        )
        return True

    def handle_create_ack(self, message):
        """Handle auction creation acknowledgment."""
        self.auction_id = message["auction_id"]
        self.item_name = message["item_name"]
        self.min_bid_price = message["min_bid_price"]
        self.min_rounds = message["min_rounds"]
        self.is_auctioneer = True
        self.is_waiting_for_start = True

        logger.info("Auction created successfully! ID: {}", self.auction_id)
        print(f"\n Auction created for '{self.item_name}'")
        print(f"Auction ID: {self.auction_id}")
        print(f"Minimum bid: ${self.min_bid_price}")
        print(f"Minimum rounds: {self.min_rounds}")
        print(f"Waiting for bidders to join...")

    def handle_create_deny(self, message):
        """Handle auction creation denial."""
        reason = message.get("reason", "Unknown reason")
        logger.warning("Auction creation denied: {}", reason)
        print(f"\n Auction creation denied: {reason}")

    def list_available_auctions(self):
        """Request list of available auctions from server."""
        if not self.server:
            logger.error("No server connection. Cannot list auctions.")
            return False

        self.client.unicast.unicast(
            request_response_handler.auction_list_request(self.client),
            self.server["ip_address"], self.server["port"]
        )
        return True

    def handle_list_response(self, message):
        """Handle auction list response from server."""
        self.available_auctions = message.get("auctions", [])
        logger.info("Received {} available auctions", len(self.available_auctions))

    def join_auction(self, auction_id):
        """Send auction join request to server."""
        if not self.server:
            logger.error("No server connection. Cannot join auction.")
            return False

        logger.info("Requesting to join auction {}", auction_id)
        self.client.unicast.unicast(
            request_response_handler.auction_join_request(self.client, auction_id),
            self.server["ip_address"], self.server["port"]
        )
        return True

    def handle_join_ack(self, message):
        """Handle auction join acknowledgment."""
        self.auction_id = message["auction_id"]
        self.item_name = message["item_name"]
        self.min_bid_price = message["min_bid_price"]
        self.min_rounds = message["min_rounds"]
        self.is_auctioneer = False
        self.is_waiting_for_start = True

        logger.info("Successfully joined auction {}", self.auction_id)
        print(f"\n✓ Joined auction for '{self.item_name}'")
        print(f"Auction ID: {self.auction_id}")
        print(f"Minimum bid: ${self.min_bid_price}")
        print(f"Minimum rounds: {self.min_rounds}")
        print(f"Waiting for auction to start...")

    def handle_join_deny(self, message):
        """Handle auction join denial."""
        reason = message.get("reason", "Unknown reason")
        logger.warning("Auction join denied: {}", reason)
        print(f"\n Could not join auction: {reason}")

    def handle_ready_check(self, message):
        """Handle ready check from server (auctioneer only)."""
        if not self.is_auctioneer:
            return

        num_bidders = message.get("num_bidders", 0)
        logger.info("Ready check received. {} bidders joined.", num_bidders)
        print(f"\n! {num_bidders} bidders have joined!")
        print("Ready to start the auction?")
        self.ready_to_confirm = True

    def confirm_start(self):
        """Confirm auction start (auctioneer only)."""
        if not self.is_auctioneer or not self.auction_id:
            logger.error("Cannot confirm start - not auctioneer or no auction")
            return False

        logger.info("Confirming auction start for {}", self.auction_id)
        self.client.unicast.unicast(
            request_response_handler.auction_ready_confirm(self.client, self.auction_id),
            self.server["ip_address"], self.server["port"]
        )
        self.ready_to_confirm = False
        return True

    def handle_auction_start(self, message):
        """Handle auction start notification."""
        logger.info("Received AUCTION_START for {}", message.get("auction_id"))
        self.auction_id = message["auction_id"]
        self.item_name = message["item_name"]
        self.min_bid_price = message["min_bid_price"]
        self.min_rounds = message["min_rounds"]
        self.participants = message.get("participants", [])
        self.is_active = True
        self.is_waiting_for_start = False

        logger.info("Auction {} started with {} participants",
                   self.auction_id, len(self.participants))
        print(f"\n{'='*50}")
        print(f"AUCTION STARTED!")
        print(f"Item: {self.item_name}")
        print(f"Minimum bid: ${self.min_bid_price}")
        print(f"Rounds: {self.min_rounds}")
        bidder_count = len([p for p in self.participants if p != self.client.uuid]) if self.is_auctioneer else len(self.participants) - 1
        print(f"Bidders: {bidder_count}")
        print(f"{'='*50}")

    def handle_round_start(self, message):
        """Handle round start notification."""
        logger.info("Received ROUND_START for round {}", message.get("round"))
        self.current_round = message["round"]
        self.min_bid_price = message.get("min_bid_price", self.min_bid_price)

        if self.current_round not in self.all_bids:
            self.all_bids[self.current_round] = {}

        logger.info("Round {} started", self.current_round)
        print(f"\n--- Round {self.current_round} ---")
        print(f"Minimum bid: ${self.min_bid_price}")

        if self.is_auctioneer:
            print("Waiting for bids...")
        else:
            self.is_bidding = True
            print("Enter your bid:")

    def submit_bid(self, bid_amount):
        """Submit a bid for the current round."""
        if not self.is_active or not self.is_bidding:
            logger.warning("Cannot bid - auction not active or not bidding phase")
            return False

        if bid_amount < self.min_bid_price:
            print(f"Bid must be at least ${self.min_bid_price}")
            return False

        logger.info("Submitting bid of ${} for round {}", bid_amount, self.current_round)
        self.my_bids[self.current_round] = bid_amount
        self.last_bid_time = time.time()
        self.is_bidding = False

        self.client.unicast.unicast(
            request_response_handler.bid_submit(
                self.client, self.auction_id, self.current_round, bid_amount
            ),
            self.server["ip_address"], self.server["port"]
        )

        print(f"Bid of ${bid_amount} submitted")
        return True

    def handle_bid_broadcast(self, message):
        """Handle bid broadcast from server."""
        round_num = message["round"]
        client_uuid = message["client_uuid"]
        bid_amount = message["bid_amount"]

        if round_num not in self.all_bids:
            self.all_bids[round_num] = {}
        self.all_bids[round_num][client_uuid] = bid_amount

        # Show bid from other participants
        if client_uuid != self.client.uuid:
            short_uuid = client_uuid[:8]
            print(f"Bidder {short_uuid}... bid ${bid_amount}")

    def handle_round_complete(self, message):
        """Handle round complete notification."""
        round_num = message["round"]
        bids = message.get("bids", {})
        self.all_bids[round_num] = bids

        logger.info("Round {} complete. Bids: {}", round_num, bids)
        print(f"\n  Round {round_num} complete!")
        print("Bids this round:")
        for client_uuid, amount in bids.items():
            marker = " (you)" if client_uuid == self.client.uuid else ""
            short_uuid = client_uuid[:8]
            print(f"{short_uuid}...: ${amount}{marker}")

    def handle_auction_winner(self, message):
        """Handle winning notification."""
        self.is_finished = True
        self.is_active = False
        self.won = True

        item_name = message.get("item_name", self.item_name)
        winning_amount = message.get("winning_amount", 0)
        cumulative_bids = message.get("cumulative_bids", {})

        logger.info("WON auction for '{}' with total bid ${}", item_name, winning_amount)
        print(f"\n{'='*50}")
        print(f"🎉 CONGRATULATIONS! YOU WON! 🎉")
        print(f"Item: {item_name}")
        print(f"Your total bid: ${winning_amount}")
        print(f"\n  Final standings:")
        for client_uuid, total in sorted(cumulative_bids.items(), key=lambda x: x[1], reverse=True):
            marker = " (you)" if client_uuid == self.client.uuid else ""
            short_uuid = client_uuid[:8]
            print(f"{short_uuid}...: ${total}{marker}")
        print(f"{'='*50}")

    def handle_auction_loser(self, message):
        """Handle losing notification."""
        self.is_finished = True
        self.is_active = False
        self.won = False

        item_name = message.get("item_name", self.item_name)
        winner = message.get("winner", "Unknown")
        winning_amount = message.get("winning_amount", 0)
        cumulative_bids = message.get("cumulative_bids", {})

        logger.info("Lost auction for '{}'. Winner: {} with ${}", item_name, winner, winning_amount)
        print(f"\n{'='*50}")
        if self.is_auctioneer:
            print(f"  AUCTION COMPLETE")
        else:
            print(f"  Auction ended - You did not win")
        print(f"Item: {item_name}")
        print(f"Winner: {winner[:8]}... with total bid ${winning_amount}")
        print(f"\n  Final standings:")
        for client_uuid, total in sorted(cumulative_bids.items(), key=lambda x: x[1], reverse=True):
            marker = " (you)" if client_uuid == self.client.uuid else ""
            short_uuid = client_uuid[:8]
            print(f"{short_uuid}...: ${total}{marker}")
        print(f"{'='*50}")

    def handle_auction_cancel(self, message):
        """Handle auction cancellation."""
        reason = message.get("reason", "Unknown reason")
        item_name = self.item_name or "Unknown item"

        # Reset all auction state flags
        self.is_finished = True
        self.is_active = False
        self.is_waiting_for_start = False
        self.is_bidding = False
        self.ready_to_confirm = False

        logger.info("Auction {} for '{}' cancelled: {}", self.auction_id, item_name, reason)
        print(f"\n{'='*50}")
        print(f"AUCTION CANCELLED")
        print(f"Item: {item_name}")
        print(f"Reason: {reason}")
        print(f"{'='*50}")
        print("Press Enter to return to menu...")

    def retransmit_last_bid(self):
        """Retransmit the last bid if no response received."""
        if self.current_round in self.my_bids:
            bid_amount = self.my_bids[self.current_round]
            logger.info("Retransmitting bid of ${} for round {}", bid_amount, self.current_round)
            self.client.unicast.unicast(
                request_response_handler.bid_submit_retransmit(
                    self.client, self.auction_id, self.current_round, bid_amount
                ),
                self.server["ip_address"], self.server["port"]
            )

    def handle_leader_failure(self):
        """Handle leader server failure."""
        logger.warning("Leader server failed!")
        print("\n! Server connection lost. Attempting to reconnect...")

        # Keep auction state but mark as disconnected
        self.server = None

        # If we were in an active auction, we need to wait for reconnection
        if self.is_active or self.is_waiting_for_start:
            print("Your auction session will resume when a new leader is found.")
            # Don't reset the auction state - we want to resume

    def set_server(self, server_details):
        """Set the server connection details."""
        self.server = server_details
        self.client.server = server_details
        logger.info("Connected to server: {}:{}", server_details["ip_address"], server_details["port"])

    def get_my_total_bid(self):
        """Calculate total bid amount across all rounds."""
        return sum(self.my_bids.values())

    def reset(self):
        """Reset auction state for a new auction."""
        self.auction_id = None
        self.is_auctioneer = False
        self.item_name = None
        self.min_bid_price = 0
        self.min_rounds = 0
        self.current_round = 0
        self.my_bids = {}
        self.all_bids = {}
        self.participants = []
        self.is_finished = False
        self.won = None
        self.is_active = False
        self.is_waiting_for_start = False
        self.is_bidding = False
        self.ready_to_confirm = False
