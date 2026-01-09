from typing import Any
import uuid
import threading
import time
from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from utils.common import get_ip_port
from message.message_handler import MessageHandler
from ui.ui import Ui
from enum import Enum
from loguru import logger
from message.message_types import ClientMessageType, ClientUiMessageType
import queue
from message.message import Message

class ClientState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1

class Client:
    def __init__(self):
        self.client_id = str(uuid.uuid4())
        self.client_ip, self.client_port = get_ip_port()
        self.client_state = ClientState.DISCONNECTED
        self.state_lock = threading.Lock()
        self.leader_server = None

        self.broadcast = Broadcast(self.client_ip)
        self.message_handler = MessageHandler()
        self.register_callbacks()
        self.message_handler.start_message_handler()
        self.unicast = Unicast(unicast_ip= self.client_ip, unicast_port=self.client_port)
        self.unicast.start_unicast_listen(self.message_handler)

        # Heartbeats
        self.heartbeat_interval = 0.1
        self.heartbeat_timeout = 2.0
        self.last_heartbeat_time = time.time()
        self.req_heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
        self.req_heartbeat_thread.start()

        # UI Section
        self.available_auctions = []
        self.auction_join_status = None
        self.ui = Ui(client_msg_queue=self.message_handler)
        self.ui_thread = threading.Thread(target=self.ui.start_ui_loop, daemon=True)
        self.ui_thread.start()


        logger.info(f"starting client {self.client_id} @ {self.client_ip} {self.client_port}")

    def _ui_loop(self):
        while not self.ui_should_exit:
            with self.state_lock:
                current_state = self.client_state

            if current_state == ClientState.DISCONNECTED:
                time.sleep(0.5)
                continue

            try:
                self._show_menu_and_handle_choice()
            except Exception as e:
                logger.error(f"Error in UI loop: {e}")
                time.sleep(1)

    def register_callbacks(self):
        self.message_handler.register_handler(ClientMessageType.RES_DISC.value, self.discover_leader)
        self.message_handler.register_handler(ClientMessageType.SERVER_HEART_BEAT.value, self.recv_server_heartbeat)
        self.message_handler.register_handler(ClientMessageType.RES_RETRIEVE_AUCTION_LIST.value, self.handle_auction_list_resp)
        self.message_handler.register_handler(ClientMessageType.RES_JOIN_AUCTION.value, self.handle_auction_join_res)
        self.message_handler.register_handler(ClientMessageType.RES_START_AUCTION.value, self.handle_start_auction_res)

    def discover_leader(self, message):
        with self.state_lock:
            logger.info("leader found at %s %s", message["ip"], message["port"])
            self.leader_server = {
                "id": message["id"],
                "ip": message["ip"],
                "port": message["port"]
            }

            self.client_state = ClientState.CONNECTED

    def search_for_leader(self):
            with self.state_lock:
                logger.info("searching for leader")
                client_message = {
                    "type": ClientMessageType.REQ_DISC.value,
                    "id": str(self.client_id),
                    "ip": self.client_ip,
                    "port": self.client_port
                }
            self.broadcast.send_broadcast(client_message)
            time.sleep(1)

    async def start_client(self):

        while True:
            with self.state_lock:
                current_state = self.client_state
                time_since_heartbeat = time.time() - self.last_heartbeat_time

                if current_state == ClientState.CONNECTED and time_since_heartbeat > self.heartbeat_timeout:
                    logger.warning(f"Leader heartbeat timeout: {time_since_heartbeat:.2f}s > {self.heartbeat_timeout}s")
                    self.client_state = ClientState.DISCONNECTED
                    self.leader_server = None
                    current_state = ClientState.DISCONNECTED

            if current_state == ClientState.DISCONNECTED:
                self.ui.ui_message_handler.add_message(Message(ClientUiMessageType.SHOW_DISCONNECTED.value, data="Setting up connection to server....."))
                await self.search_for_leader()

            time.sleep(0.1)
                
    def handle_start_auction_res(self, msg):
        self.ui_msg_queue.put(msg.get("msg"))

    def join_auction(self):
        # List auction rooms still accepting clients
        self.retrieve_auctions_from_leader()
        # client selects the auction room
        with self.state_lock:
            if not self.available_auctions:
                print("No new auctions are available to join. Try again later")
                return
                
        self.display_and_select_auction()
        # Response - successful or failed to join
        # If successful, client is shown the round status and current highest bids once the auction starts
        while True:
            with self.state_lock:
                join_status = self.auction_join_status
            if join_status is None:
                time.sleep(1)
            else:
                if join_status == True:
                    # TODO: Implement run_auction() method
                    logger.info("Auction joined successfully")
                else:
                    print("Unable to join auction. Try Again Later!!")
                break
        # client is allowed to send one bid every round (round can help us order the requests)
        # Once the auction concludes client is displayed with winning or losing status
        # Return to main menu upon finishing the auction or failing to join
    def handle_auction_join_res(self, msg):
        with self.state_lock:
            self.auction_join_status= msg.get("status")
    
    def retrieve_auctions_from_leader(self):
        with self.state_lock:
            leader_server = self.leader_server
            if leader_server is None:
                logger.warning("No leader server available")
                return
            msg = {
                "type": ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port
            }
            leader_ip = leader_server.get("ip")
            leader_port = leader_server.get("port")

        # Send message outside the lock
        self.unicast.send_message(msg, leader_ip, leader_port)
        print("Waiting for responses....")
        time.sleep(5)

    def handle_auction_list_resp(self, msg):
        with self.state_lock:
            self.available_auctions = msg.get("available_auctions")
        
    def display_and_select_auction(self):
        with self.state_lock:
            auction_list = self.available_auctions

        print("The list of Available auctions are:")
        for index, auc in enumerate(auction_list, start=1):
            print(f"{index}. {auc.get('item')}")
        x = int(input("Enter your choice:"))

        with self.state_lock:
            msg = {
                "type": ClientMessageType.REQ_JOIN_AUCTION.value,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port,
                "auction": self.available_auctions[x-1]
            }
            leader_server = self.leader_server
            self.auction = self.available_auctions[x-1]

        self.unicast.send_message(msg, leader_server.get("ip"), leader_server.get("port"))

    def _show_menu_and_handle_choice(self):
        print("="*40)
        print("Welcome to Agora")
        print("="*40)
        print("Choose one of the following options")
        print("1. Join Auction")
        print("2. Start Auction")
        print("3. Exit")
        print("="*40)
        try:
            inp = input("Enter your choice:")
            inp = int(inp)

            with self.state_lock:
                        if self.client_state == ClientState.DISCONNECTED:
                            print("Lost connection to leader. Reconnecting...")
                            return
            match inp:
                case 1: self.join_auction()
                case 2: self.create_new_auction()
                case 3: 
                    print("Exiting..")
                    self.ui_should_exit = True
                    return

        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
        except Exception as e:
            logger.error(f"Unexpected error in menu: {e}")
            print("An error occurred. Please try again.")


    def send_heartbeat(self):
        """Send periodic heartbeats to server (no response expected)"""
        while True:
            time.sleep(self.heartbeat_interval)
            with self.state_lock:
                if self.client_state == ClientState.CONNECTED and self.leader_server is not None:
                    msg = {
                        "type": ClientMessageType.CLIENT_HEART_BEAT.value,
                        "id": self.client_id,
                        "ip": self.client_ip,
                        "port": self.client_port
                    }
                    leader_ip = self.leader_server.get("ip")
                    leader_port = self.leader_server.get("port")
                else:
                    continue

            # Send message outside the lock (no response expected)
            self.unicast.send_message(msg, ip=leader_ip, port=leader_port)

    def recv_server_heartbeat(self, message):
        """Receive heartbeat from server (no response needed)"""
        with self.state_lock:
            # Update last heartbeat time to detect server failures
            self.last_heartbeat_time = time.time()

            # Update leader info if it changed
            if self.leader_server is None or self.leader_server.get("id") != message.get('id'):
                self.leader_server = {
                    "id": message.get('id'),
                    "ip": message.get('ip'),
                    "port": message.get('port')
                }
                logger.info(f"Updated leader info from heartbeat: {message.get('id')}")

    def create_new_auction(self):
        item = input("Enter name of item you want to sell:")
        min_bid_amt = int(input("Enter minimum bid amount:"))
        min_bidders =  int(input("Enter the minimum number of bidders (must be greater than 2):"))
        no_of_rounds = int(input("Enter the number of rounds:"))

        with self.state_lock:
            msg =  {
                "type": ClientMessageType.REQ_START_AUCTION.value,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port,
                "item": item,
                "min_bid": min_bid_amt,
                "min_bidders": min_bidders,
                "rounds": no_of_rounds
            }
            leader_ip = self.leader_server.get("ip")
            leader_port = self.leader_server.get("port")

        # Send message outside the lock
        self.unicast.send_message(msg, leader_ip, leader_port)

        while True:
            try:
                ui_msg = self.ui_msg_queue.get(timeout=1.0)
                print(ui_msg)
            except queue.Empty:
                continue
    


def main():
    # 1. broadcasts itself to the network
    # 2. awaits response from leader
    # 3. starts heartbeat to leader
    # 4. no response from leader -> broadcast
    client = Client()
    client.start_client()


if __name__ == "__main__":
    main()