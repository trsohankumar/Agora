from dataclasses import dataclass
from typing import Optional
from message.message_types import ClientMessageType, ServerMessageType

@dataclass
class Message:
    """
        Message class to replace the use of dictionary
    """
    message_type:str 
    sender_details:Optional[dict] = None
    data:dict


    def to_json(self):
        return {
            "type": self.message_type,
            "sender": self.sender_details,
            "data": self.data
        }