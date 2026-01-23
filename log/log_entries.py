from dataclasses import dataclass
from message.message import Message


@dataclass
class LogEntries:
    term: int
    command: Message

    def to_dict(self):
        return {
            "term": self.term,
            "command": self.command.to_json()
        }

    @staticmethod
    def from_dict(data):
        return LogEntries(term=data["term"], command=Message.from_json(data["command"]))