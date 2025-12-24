import threading
from dataclasses import dataclass

@dataclass
class LogEntries:
    term: int
    command: dict