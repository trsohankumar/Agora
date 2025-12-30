from typing import Any
import uuid
import threading
import time
from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from utils.common import get_ip_port
from message.message_handler import MessageHandler
from enum import Enum
from loguru import logger
from message.message_types import ClientMessageType

class ClientState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1

class Client:
    def __init__(self):
        self.client_id = uuid.uuid4()
        self.client_ip, self.client_port = get_ip_port()
        logger.info(
            f"starting client {self.client_id} @ {self.client_ip} {self.client_port}"
        )

        self.message_handler = MessageHandler()
        self.broadcast = Broadcast(self.client_ip)
        self.unicast = Unicast(unicast_ip= self.client_ip, unicast_port=self.client_port)
        self.client_state = ClientState.DISCONNECTED
        self.leader_server = None
        self.is_client_in_action = False
        self.register_callbacks()

        self.state_lock = threading.Lock()

        self.heartbeat_interval = 0.05
        self.heartbeat_timeout = 2.0
        self.last_heartbeat_time = time.time()

        self.req_heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
        self.req_heartbeat_thread.start()
        self.available_auctions = list()
        self.auction_join_state = None
        self.is_client_in_auction = False
        self.options = [
            "Start auction"
            "Join existing auction"
        ]

    def register_callbacks(self):
        self.message_handler.register_handler(ClientMessageType.RES_DISC.value, self.discover_leader)
        self.message_handler.register_handler(ClientMessageType.RES_HEART_BEAT.value, self.recv_heartbeats_resp)
        self.message_handler.register_handler(ClientMessageType.RES_RETRIEVE_AUCTION_LIST.value, self.retrieve_auctions_from_leader)
        self.message_handler.register_handler(ClientMessageType.RES_JOIN_AUCTION.value, self.handle_auction_join_res)

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

    def start_client(self):
        self.message_handler.start_message_handler()
        self.unicast.start_unicast_listen(self.message_handler)
        while True:
            with self.state_lock:
                time_since_heartbeat = time.time() - self.last_heartbeat_time
                if self.client_state == ClientState.CONNECTED and time_since_heartbeat > self.heartbeat_timeout:
                    print(f"here {time_since_heartbeat}, {self.heartbeat_timeout}")
                    self.client_state = ClientState.DISCONNECTED
                    self.is_client_in_auction = False
                    self.leader_server = None
                current_state = self.client_state
            if current_state == ClientState.DISCONNECTED:
                self.search_for_leader()
            elif current_state == ClientState.CONNECTED:
                with self.state_lock:
                    if not self.is_client_in_auction:
                        threading.Thread(target=self.client_menu, daemon=True).start()
                        self.is_client_in_auction = True
                # Provide menu to choose between existing auctions or create a new auction
                # The exisitng auction list must be the list of auctions that are still accepting clients
                # 
    
    def join_auction(self):
        # List auction rooms still acception clients
        self.retreive_auctions_from_leader()
        # client selects the auction room
        with self.state_lock:
            if self.available_auctions is None:
                print("No new auctions are available to join. Try again later")
                return
                
        self.display_and_select_auction()
        # Sends requests to server
        self.send_auction_join_req()
        # Response - successful or failed to join
        # If successful, client is shown the round status and current highest bids once the auction starts
        while True:
            with self.state_lock:
                join_status = self.auction_join_status
            if join_status is None:
                time.sleep(1)
            else:
                if join_status == True:
                    self.run_auction()
                else: 
                    print("Unable to join auction. Try Again Later!!")
                with self.state_lock:
                    self.is_client_in_auction = False
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
            msg = {
                "type": ClientMessageType.REQ_RETRIEVE_AUCTION_LIST.value,
                "id": self.client_id,
                "ip": self.client_ip,
                "port": self.client_port
            }

        self.unicast.send_message(msg, leader_server.get("ip"), leader_server.get("ip"))
        print("Wating for responses....")
        time.sleep(5)

    def handle_auction_list_resp(self, msg):
        with self.state_lock:
            self.available_auctions = msg.get("available_auctions")
        
    def display_and_select_auction(self):
        with self.state_lock:
            auction_list = self.available_auctions

        print("The list of Available auctions are:")
        for index, auc in enumerate(auction_list, start=1):
            print(f"{index}. {auc.get("item")}")
        x = int("Enter your choice:")

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

    def create_new_auction(self):
        pass

    def client_menu(self):
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

            match inp:
                case 1: self.join_auction()
                case 2: self.create_new_auction()
                case 3: pass
        except:
            print("Wrong choice selected. Try again!")


    def send_heartbeat(self):
        while True:
            with self.state_lock:
                if self.client_state == ClientState.CONNECTED:
                    msg = {
                        "type": ClientMessageType.REQ_HEART_BEAT.value,
                        "id": str(self.client_id),
                        "ip": self.client_ip,
                        "port": self.client_port
                    }
                    self.unicast.send_message(msg, ip=self.leader_server.get("ip"), port=self.leader_server.get("port"))
            time.sleep(self.heartbeat_interval)
                
    def recv_heartbeats_resp(self, message):
        with self.state_lock:
            if self.leader_server.get("id") != message.get('id'):
                self.leader_server = {
                    "id": message.get('id'),
                    "ip": message.get('ip'),
                    "port": message.get('port')
                } 
            self.last_heartbeat_time = time.time()


def main():
    # 1. broadcasts itself to the network
    # 2. awaits response from leader
    # 3. starts heartbeat to leader
    # 4. no response from leader -> broadcast
    client = Client()
    client.start_client()


if __name__ == "__main__":
    main()