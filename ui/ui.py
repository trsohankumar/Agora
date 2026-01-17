import time
from loguru import logger
from utils.common import DisconnectedError, RequestTimeoutError


class Ui:
    def __init__(self, client):
        self.client = client
        self.running = True
        self.waiting_for_auction = False

    def start(self):
        while self.running:
            if not self.client.is_connected():
                print("Connecting to server....")
                time.sleep(1)
                continue

            self._show_menu()

    def _show_menu(self):
        print("=" * 40)
        print("Welcome to Agora")
        print("=" * 40)
        print("Choose one of the following options")
        print("1. Join Auction")
        print("2. Start Auction")
        print("3. Exit")
        print("=" * 40)
        try:
            inp = input("Enter your choice:").strip()
            match inp:
                case "1":
                    self._join_auction_flow()
                case "2":
                    self._create_new_auction_flow()
                case "3":
                    print("Exiting..")
                    self.running = False
                case _:
                    print("Invalid choice")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
        except Exception as e:
            logger.error(f"Unexpected error in menu: {e}")
            print("An error occurred. Please try again.")

    def _join_auction_flow(self):
        print("Fetching available auctions....")
        try:
            auctions = self.client.get_auctions_list()
        except DisconnectedError:
            print("Lost connection to server.")
            return
        except RequestTimeoutError:
            print("Request timed out. Try again")
            return

        if not auctions:
            print("No auctions available.")
            return

        print("\nAvailable auctions:")
        print(auctions)
        for i, auction in enumerate(auctions, 1):
            print(f"  {i}. {auction.get('item')}")
        try:
            choice = int(input("\nSelect acution:")) - 1
            if not (0 <= choice < len(auctions)):
                return
        except ValueError:
            print("Invalid input.")
            return

        print("Joining auction. Please Wait....")

        try:
            resp = self.client.join_auction(auctions[choice].get("id"))
            print(resp)
        except RequestTimeoutError:
            print("Request timed out. Try again")
            return

        if resp.get("status") is not True:
            print("Unable to join the room try again later")

        while not self.client.auction_room_enabled():
            time.sleep(5)

        while True:
            msg = self.client.await_make_bid()

            while True:
                print("=" * 40)
                bid = int(input(f"Please bid for round {msg.get("round")} for {msg.get("item")} (Min bid: {msg.get("current_highest") + 1}) Enter 0 (no bid)"))
                print("=" * 40)

                if bid > msg.get("current_highest") or bid == 0:
                    break

                print("Invalid bid entered. Try again")

            self.client.make_bid(msg.get("auction_id"), bid)

            msg = self.client.await_round_result()

            print(
                f"The highest bid for round {msg.get("round")} is {msg.get("highest_bid")}"
            )

            if msg.get("is_final_round"):
                print(f"The winner of the auction is {msg.get("highest_bidder")}")
                break

    def _create_new_auction_flow(self):
        try:
            item = input("Item name: ").strip()
            min_bid = int(input("Minimum bid: "))
            min_bidders = int(input("Minimum bidders (>2): "))
            rounds = int(input("Number of rounds: "))
        except ValueError:
            print("Invalid input.")
            return

        print("\nCreating auction...")

        try:
            result = self.client.create_new_auction(item, min_bid, min_bidders, rounds)
            print(f"Result: {result}")
            auction_id = result.get("auction_id")
        except DisconnectedError:
            print("Lost connection to server.")
            return

        # if server succeded in creating an auction
        print("Waiting for bidders to join...")

        while not self.client.auction_room_enabled():
            time.sleep(5)
        # run a while loop until enough peers are available. ( Sleep in the loop)

        # once enough peers are available allow the client to either wait more or start the auction immediately
        print("")
        print("=" * 40)
        _ = input("Bidders have joined the room, please press any key to start the auction:")
        print("=" * 40)

        try:
            result = self.client.start_auction(auction_id)
            print(result.get("msg"))
        except DisconnectedError:
            print("Lost connection to server.")
            return

        while True:
            msg = self.client.await_round_result()

            print(f"The highest bid for round {msg.get("round")} is {msg.get("current_highest")}")

            if msg.get("is_final_round"):
                print(f"The winner of the auction is {msg.get("highest_bidder")}")
                break
