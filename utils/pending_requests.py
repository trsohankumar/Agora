from dataclasses import dataclass, field
import threading

@dataclass
class PendingRequest:
    event: threading.Event = field(default_factory=threading.Event)
    response: Any = None
    disconnected: bool = False