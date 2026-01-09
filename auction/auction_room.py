import uuid
from node_list import NodeList
from enum import Enum

class AuctionRoomStatus(Enum):
    AWAITING_PEEERS = 0
    IN_AUCTION = 1
    DONE = 2

class AuctionRoom:
    def __init__(self, auctioneer, rounds, item, min_bid, min_bidders):
        self._id = str(uuid.uuid4())
        self.auctioneer = None
        self.bidders = NodeList()
        self.status = AuctionRoomStatus.AWAITING_PEEERS
        self.rounds = rounds
        self.round_timeout = 10
        self.item = item
        self.min_bid = min_bid
        self.max_bid = 0
        self.max_bidder = None
        self.min_number_of_bidders = min_bidders

    def add_participant(self, participant):
        self.bidders.add_node(participant)
        
    def to_json(self):
        return {
            'id': str(self._id),
            'auctioneer': self.auctioneer,
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