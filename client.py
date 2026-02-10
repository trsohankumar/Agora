import sys
import threading
import time

from loguru import logger
from pyfiglet import figlet_format
from termcolor import cprint

import constants
from auction.client_auction_manager import ClientAuctionManager
from broadcast.broadcast import Broadcast
from constants import CLIENT
from discovery.discovery_handler import DiscoveryHandler
from heartbeat.hearbeat import Heartbeat
from messages.client_messages_manager import ClientMessagesManager
from unicast.unicast import Unicast
from util import request_response_handler, uuid_util

logger.remove()
logger.add(sys.stderr, level=40)


class Client:
    def __init__(self):
        self.uuid = uuid_util.get_uuid()
        self.type = CLIENT
        self.discovered_servers = {}
        self.messages_manager = ClientMessagesManager()
        self.broadcast = Broadcast(self.messages_manager)
        self.unicast = Unicast(self.messages_manager)
        self.discovery_handler = DiscoveryHandler(self)
        self.heartbeat_manager = Heartbeat(self, constants.HEART_BEAT_INTERVAL)
        self.auction_manager = ClientAuctionManager(self)
        self._register_message_handlers()
        self.round_tracker = 0
        self.leader = None
        self.server = None

    def _register_message_handlers(self):
        mm = self.messages_manager
        # Discovery
        mm.register(
            constants.DISCOVERY_RESPONSE,
            self.discovery_handler.process_discovery_response,
        )
        # Heartbeat
        mm.register(
            constants.HEART_BEAT_ACK, self.heartbeat_manager.process_heartbeat_ack
        )
        # Auction creation and joining
        mm.register(
            constants.AUCTION_CREATE_ACK, self.auction_manager.handle_create_ack
        )
        mm.register(
            constants.AUCTION_CREATE_DENY, self.auction_manager.handle_create_deny
        )
        mm.register(
            constants.AUCTION_LIST_RESPONSE, self.auction_manager.handle_list_response
        )
        mm.register(constants.AUCTION_JOIN_ACK, self.auction_manager.handle_join_ack)
        mm.register(constants.AUCTION_JOIN_DENY, self.auction_manager.handle_join_deny)
        # Auction lifecycle
        mm.register(
            constants.AUCTION_READY_CHECK, self.auction_manager.handle_ready_check
        )
        mm.register(constants.AUCTION_START, self.auction_manager.handle_auction_start)
        mm.register(
            constants.AUCTION_CANCEL, self.auction_manager.handle_auction_cancel
        )
        # Bidding
        mm.register(constants.ROUND_START, self.auction_manager.handle_round_start)
        mm.register(constants.BID_BROADCAST, self.auction_manager.handle_bid_broadcast)
        mm.register(
            constants.ROUND_COMPLETE, self.auction_manager.handle_round_complete
        )
        # Auction completion
        mm.register(
            constants.AUCTION_WINNER, self.auction_manager.handle_auction_winner
        )
        mm.register(constants.AUCTION_LOSER, self.auction_manager.handle_auction_loser)
        # Leader updates
        mm.register(constants.LEADER_DETAILS, self.handle_leader_update)

    def start_clients(self):
        logger.info("Starting client {}", self.uuid)
        self.start_chores()

    def start_chores(self):
        threading.Thread(target=self.broadcast.listen, daemon=True).start()
        threading.Thread(target=self.unicast.listen, daemon=True).start()
        self.messages_manager.start()
        self.initiate_discovery()
        discovery_start = time.time()
        self.heartbeat_manager.send_heartbeat()
        self.period_debug_info()

        # Display auction banner
        cprint(
            figlet_format("AGORA", font="dos_rebel"),
            "green",
            "on_black",
            attrs=["bold"],
        )
        print("Finding a server...")
        print(f"You are: {self.uuid}")
        print(f"Listening on: {self.unicast.ip_address}:{self.unicast.port}")
        print("(Make sure the server is running first)")

        # Wait for leader discovery - retry every 10 seconds initially
        retry_interval = 10
        while self.leader is None:
            if time.time() - discovery_start > retry_interval:
                discovery_start = time.time()
                print("Retrying discovery...")
                self.initiate_discovery()
            time.sleep(1)

        # Set server in auction manager
        leader_server = self.discovered_servers[self.leader]
        self.auction_manager.set_server(leader_server)

        print(f"\nConnected to server!")

        # Main auction loop
        self.run_auction_menu()

    def run_auction_menu(self):
        """Main auction menu loop."""
        while True:
            try:
                logger.debug(
                    "Menu loop: is_finished={}, ready_to_confirm={}, is_bidding={}, is_active={}, is_waiting={}",
                    self.auction_manager.is_finished,
                    self.auction_manager.ready_to_confirm,
                    self.auction_manager.is_bidding,
                    self.auction_manager.is_active,
                    self.auction_manager.is_waiting_for_start,
                )

                if self.auction_manager.is_finished:
                    print("\nAuction ended. Returning to main menu...")
                    self.auction_manager.reset()

                if self.auction_manager.ready_to_confirm:
                    self.handle_auctioneer_confirm()
                elif self.auction_manager.is_bidding:
                    self.handle_bidding()
                elif (
                    self.auction_manager.is_active
                    and not self.auction_manager.is_bidding
                ):
                    # Auction is active but waiting for round to start
                    logger.debug(
                        "Waiting for round to start (is_active=True, is_bidding=False)"
                    )
                    time.sleep(0.5)
                elif self.auction_manager.is_waiting_for_start:
                    print(".", end="", flush=True)
                    time.sleep(1)
                else:
                    self.show_main_menu()

            except EOFError:
                print("\nGoodbye!")
                break
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break

    def show_main_menu(self):
        """Display and handle main menu."""
        print("\n" + "=" * 50)
        print("  AUCTION SYSTEM - MAIN MENU")
        print("=" * 50)
        print("  1. Create Auction")
        print("  2. List Auctions")
        print("  3. Join Auction")
        print("  4. Exit")
        print("=" * 50)

        try:
            choice = input("Enter choice (1-4): ").strip()

            if choice == "1":
                self.handle_create_auction()
            elif choice == "2":
                self.handle_list_auctions()
            elif choice == "3":
                self.handle_join_auction()
            elif choice == "4":
                print("Goodbye!")
                raise KeyboardInterrupt
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Invalid input.")

    def handle_create_auction(self):
        """Handle auction creation flow."""
        print("\n--- Create New Auction ---")
        try:
            item_name = input("Item name: ").strip()
            if not item_name:
                print("Item name cannot be empty.")
                return

            min_bid_str = input("Minimum bid price ($): ").strip()
            min_bid_price = float(min_bid_str)
            if min_bid_price <= 0:
                print("Minimum bid must be positive.")
                return

            min_rounds_str = input("Minimum rounds (default 3): ").strip()
            min_rounds = int(min_rounds_str) if min_rounds_str else 3
            if min_rounds < 1:
                print("Minimum rounds must be at least 1.")
                return

            min_bidders_str = input("Minimum bidders (default 2): ").strip()
            min_bidders = int(min_bidders_str) if min_bidders_str else 2
            if min_bidders < 2:
                print("Minimum bidders must be at least 2.")
                return

            print(f"\nCreating auction for '{item_name}'...")
            self.auction_manager.create_auction(
                item_name, min_bid_price, min_rounds, min_bidders
            )

            # Wait for response
            time.sleep(2)

        except ValueError:
            print("Invalid input. Please enter valid numbers.")

    def handle_list_auctions(self):
        """Handle listing available auctions."""
        print("\n--- Available Auctions ---")
        self.auction_manager.list_available_auctions()

        # Wait for response
        time.sleep(2)

        auctions = self.auction_manager.available_auctions
        if not auctions:
            print("No auctions available.")
            return

        print(f"\n{'ID':<8} {'Item':<20} {'Min Bid':<10} {'Rounds':<8} {'Bidders':<10}")
        print("-" * 60)
        for i, auction in enumerate(auctions, 1):
            print(
                f"{i:<8} {auction['item_name'][:18]:<20} ${auction['min_bid_price']:<9.2f} "
                f"{auction['min_rounds']:<8} {auction['current_bidders']}/{auction['min_bidders']:<9}"
            )

    def handle_join_auction(self):
        """Handle joining an auction."""
        print("\n--- Join Auction ---")

        # First, list available auctions
        self.auction_manager.list_available_auctions()
        time.sleep(2)

        auctions = self.auction_manager.available_auctions
        if not auctions:
            print("No auctions available to join.")
            return

        print(f"\n{'#':<4} {'Item':<20} {'Min Bid':<10} {'Bidders':<10}")
        print("-" * 50)
        for i, auction in enumerate(auctions, 1):
            print(
                f"{i:<4} {auction['item_name'][:18]:<20} ${auction['min_bid_price']:<9.2f} "
                f"{auction['current_bidders']}/{auction['min_bidders']}"
            )

        try:
            choice_str = input(
                "\nEnter auction number to join (or 0 to cancel): "
            ).strip()
            choice = int(choice_str)

            if choice == 0:
                return

            if 1 <= choice <= len(auctions):
                auction = auctions[choice - 1]
                print(f"\nJoining auction for '{auction['item_name']}'...")
                self.auction_manager.join_auction(auction["auction_id"])
                time.sleep(2)
            else:
                print("Invalid choice.")
        except ValueError:
            print("Invalid input.")

    def handle_auctioneer_confirm(self):
        """Handle auctioneer confirmation to start."""
        try:
            confirm = input("Start auction now? (y/n): ").strip().lower()
            if confirm == "y":
                self.auction_manager.confirm_start()
                # Wait for auction to start and first round to begin
                print("Starting auction...")
                wait_count = 0
                while not self.auction_manager.is_bidding and wait_count < 20:
                    logger.info(
                        "Waiting for is_bidding... is_active={}, is_bidding={}, wait_count={}",
                        self.auction_manager.is_active,
                        self.auction_manager.is_bidding,
                        wait_count,
                    )
                    time.sleep(0.5)
                    wait_count += 1
                if self.auction_manager.is_bidding:
                    print("Auction started! You can now bid.")
                else:
                    logger.warning(
                        "Timeout waiting for auction to start. is_active={}, is_bidding={}",
                        self.auction_manager.is_active,
                        self.auction_manager.is_bidding,
                    )
                    print(
                        "Timeout waiting for auction to start. Please check server logs."
                    )
            else:
                print("Waiting for more bidders...")
                self.auction_manager.ready_to_confirm = False
        except (EOFError, KeyboardInterrupt):
            raise

    def handle_bidding(self):
        """Handle bidding input."""
        logger.info(
            "In handle_bidding: is_active={}, is_bidding={}, is_auctioneer={}",
            self.auction_manager.is_active,
            self.auction_manager.is_bidding,
            self.auction_manager.is_auctioneer,
        )
        try:
            bid_str = input(
                f"  Your bid (min ${self.auction_manager.min_bid_price}): $"
            ).strip()
            # Auction may have been cancelled while waiting for input
            if self.auction_manager.is_finished or not self.auction_manager.is_active:
                return
            bid_amount = float(bid_str)
            self.auction_manager.submit_bid(bid_amount)
        except ValueError:
            if self.auction_manager.is_finished:
                return
            print("  Invalid bid amount. Please enter a number.")
        except (EOFError, KeyboardInterrupt):
            raise

    def handle_leader_update(self, message):
        """Handle LEADER_DETAILS message — update leader and reconnect auction manager."""
        leader_server = message["leader_details"]
        self.leader = leader_server["uuid"]
        if self.leader not in self.discovered_servers:
            self.discovered_servers[leader_server["uuid"]] = leader_server
        self.auction_manager.set_server(leader_server)
        self.heartbeat_manager.election_triggered = False
        logger.info("Received new leader info: {}", leader_server["uuid"])

    def initiate_discovery(self):
        self.broadcast.broadcast(request_response_handler.discovery_request(self))

    def period_debug_info(self):
        try:
            self.round_tracker += 1
            threading.Timer(60, self.period_debug_info).start()
        except Exception as e:
            raise KeyboardInterrupt


if __name__ == "__main__":
    client = Client()
    client.start_clients()
