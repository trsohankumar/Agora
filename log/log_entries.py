import threading
from dataclasses import dataclass

@dataclass
class LogEntries:
    term = 0
    command = None