from dataclasses import dataclass
from message_types import ClientMessageType, ServerMessageType

@dataclass
class Message:
    """
        Message class to replace the use of dictionary
    """
    message_type:str 
    data:dict


    def to_json(self):
        return {
            "type": self.message_type,
            "data": self.data
        }