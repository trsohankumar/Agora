import uuid
import threading

from enum import Enum
from typing import Dict
from dataclasses import dataclass, field

from node_list import NodeList
from node_list import Node

class AuctionRoomStatus(Enum):
    AWAITING_PEEERS = 0
    IN_AUCTION = 1
    DONE = 2

@dataclass
class RoundState:
    round_num: int
    expected_bidders: set[str]
    bids: Dict[str, int] = field(default_factory=dict)
    all_received: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_bid(self, client_id: str, amount: int) -> bool:
        with self.lock:
            if client_id not in self.expected_bidders:
                return False
            
            self.bids[client_id] = amount
            
            if set(self.bids.keys()) == self.expected_bidders:
                self.all_received.set()
                return True
        return False

    def wait_for_all(self) -> bool:
        return self.all_received.wait()


class AuctionRoom:
    def __init__(self, auctioneer:Node, rounds:int, item:str, min_bid:int, min_bidders:int):
        self._id = str(uuid.uuid5(uuid.NAMESPACE_DNS, item))
        self.auctioneer = auctioneer
        self.bidders = NodeList()
        self.status = AuctionRoomStatus.AWAITING_PEEERS
        self.rounds = rounds
        self.round_timeout = 10
        self.item = item
        self.min_bid = min_bid
        self.max_bid = 0
        self.max_bidder = None
        self.min_number_of_bidders = min_bidders
        
    def add_participant(self, participant_id, participant):
        self.bidders.add_node(participant_id, participant)

    def to_json(self):
        return {
            'id': str(self._id),
            'auctioneer': self.auctioneer.dict(),
            'bidders': self.bidders.get_all_node(),
            'status': self.status.value if self.status else None,
            'rounds': self.rounds,
            'round_timeout': self.round_timeout,
            'item': self.item,
            'min_bid': self.min_bid,
            'max_bid': self.max_bid,
            'max_bidder': self.max_bidder
        }
    
    def get_id(self):
        return self._id
    
    def get_bidder_count(self):
        return self.bidders.get_len()
    
    def get_min_number_bidders(self):
        return self.min_number_of_bidders
    
    def get_auctioneer(self):
        return self.auctioneer
    
    def get_max_bidder(self):
        return self.max_bid
    
    def get_max_bid_amt(self):
        return self.max_bid

    def get_rounds(self):
        return self.rounds