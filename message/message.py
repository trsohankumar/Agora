from dataclasses import dataclass, field
from typing import Optional
from node_list import Node
from message.message_types import MessageType


@dataclass
class Message:
    """
    Message class to replace the use of dictionary
    """

    sender: Node
    message_type: Optional[MessageType]
    data: Optional[dict] = field(default_factory=dict)

    def to_json(self) -> dict:
        """
        This method covnerts the message to json format
        """
        return {
            "type": self.message_type,
            "sender": self.sender.dict(),
            "data": self.data,
        }

    @classmethod
    def from_json(cls, message):
        return cls(
            sender=Node.from_json(message.get("sender")),
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
