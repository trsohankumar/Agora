from dataclasses import dataclass, field
from typing import Optional
from node_list import Node
from message.message_types import MessageType


@dataclass
class Message:
    """
    Message class to replace the use of dictionary
    """

    sender: Optional[Node] = None
    receiver: Optional[Node] = None
    message_type: Optional[MessageType] = None
    data: Optional[dict] = field(default_factory=dict)

    def to_json(self) -> dict:
        """
        This method converts the message to json format
        """
        return {
            "type": self.message_type,
            "sender": self.sender.dict() if self.sender else None,
            "receiver": self.receiver.dict() if self.receiver else None,
            "data": self.data,
        }

    @classmethod
    def from_json(cls, message):
        """
        Creates a Message object from a JSON dictionary.
        """
        sender_data = message.get("sender")
        receiver_data = message.get("receiver")
        return cls(
            sender=Node.from_json(sender_data) if sender_data else None,
            receiver=Node.from_json(receiver_data) if receiver_data else None,
            message_type=message.get("type"),
            data=message.get("data"),
        )

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
