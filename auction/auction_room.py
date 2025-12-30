import uuid
from node_list import NodeList
from enum import Enum

class AuctionRoomStatus(Enum):
    AWAITING_PEEERS = 0
    IN_AUCTION = 1
    DONE = 2

class AuctionRoom:
    def __init__(self, auctioneer):
        self._id = uuid.uuid4()
        self.auctioneer = None
        self.participants = NodeList()
        self.status = AuctionRoomStatus.AWAITING_PEEERS
        self.rounds = 0
        self.round_timeout = 10
        self.item = None
        self.min_bid = 0 
        self.max_bid = 0
        self.max_bidder = None

    def add_participant(self, participant):
        self.participants.add_node(participant)
        
    def to_json(self):
        return {
            'id': str(self._id),
            'auctioneer': self.auctioneer,
            'participants': self.participants,
            'status': self.status.value if self.status else None,
            'rounds': self.rounds,
            'round_timeout': self.round_timeout,
            'item': self.item,
            'min_bid': self.min_bid,
            'max_bid': self.max_bid,
            'max_bidder': self.max_bidder
        }