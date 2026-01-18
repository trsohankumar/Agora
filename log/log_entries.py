from dataclasses import dataclass

@dataclass
class LogEntries:
    term: int
    command: dict

    def to_dict(self):
        return {
            "term": self.term,
            "command": self.command
        }

    @staticmethod
    def from_dict(data):
        return LogEntries(term=data["term"], command=data["command"])