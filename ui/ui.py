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
        print("="*40)
        print("Welcome to Agora")
        print("="*40)
        print("Choose one of the following options")
        print("1. Join Auction")
        print("2. Start Auction")
        print("3. Exit")
        print("="*40)
        try:
            inp = input("Enter your choice:").strip()
            match inp:
                case "1": self._join_auction_flow()
                case "2": self._create_new_auction_flow()
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
        
        if resp.get("status") == True:
            while True:
                print("Waiting for auction to start")
                time.sleep(5)

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
        except DisconnectedError:
            print("Lost connection to server.")
            return

        # if server succeded in creating an auction

        print("Waiting for bidders to join...")
        while True:
            time.sleep(5)
        # run a while loop until enough peers are available. ( Sleep in the loop)

        # once enough peers are available allow the client to either wait more or start the auction immediately
        