from enum import Enum

class ClientMessageType(Enum):
    REQ_DISC = 1
    RES_DISC = 2
    REQ_START_AUCTION = 3
    RES_START_AUCTION = 4
    REQ_JOIN_AUCTION = 5
    RES_JOIN_AUCTION = 6
    CLIENT_HEART_BEAT = 7       # Client -> Server heartbeat (unidirectional)
    SERVER_HEART_BEAT = 8       # Server -> Client heartbeat (unidirectional)
    REQ_MAKE_BID = 9
    RES_MAKE_BID = 10
    REQ_REMOVE_CLIENT = 11
    REQ_RETRIEVE_AUCTION_LIST = 12
    RES_RETRIEVE_AUCTION_LIST = 13  # Fixed: was 12, should be 13

class ClientUiMessageType(Enum):
    SHOW_DISCONNECTED = 1000
    SHOW_CONNECTED = 1001

class ServerMessageType(Enum):
    REQ_DISC = 100
    RES_DISC = 101
    REQ_VOTE = 102
    RES_VOTE = 103
    REQ_APPEND_ENTRIES = 104
    RES_APPEND_ENTRIES = 105