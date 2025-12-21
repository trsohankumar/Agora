from enum import Enum

class MessageType(Enum):
    AppendEntry = 0
    RequestVote = 1
    ResponseVote = 2
    Response = 3
    BroadCast = 4
    BroadCastResponse = 5

class Message:
    def __init__(self, term, data, message_type):
        self.term = term
        self.data = data
        self.message_type = message_type