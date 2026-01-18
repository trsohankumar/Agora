from dataclasses import dataclass
from typing import Optional
from node_list import Node
from message.message_types import MessageType


@dataclass
class Message:
    """
        Message class to replace the use of dictionary
    """
    sender:Node
    message_type:Optional[MessageType]
    data:Optional[dict] = {}

    def to_json(self) -> dict:
        """
            This method covnerts the message to json format
        """
        return {
            "type": self.message_type,
            "sender": self.sender,
            "data": self.data
        }
    
    def set_type(self, message_type: MessageType) -> None:
        """
            This method sets the type of the message
        """
        self.message_type = message_type

    def set_data(self, data: Optional[dict]) -> None:
        """
            This method sets the payload of the message
        """
        self.data = data