import socket
import uuid

def get_ip_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(("8.8.8.8", 80))
    return (sock.getsockname()[0], sock.getsockname()[1])

def get_uuid():
    return str(uuid.uuid4())


def get_uuid_int(uuid1):
    return uuid.UUID(uuid1).int

class DisconnectedError(Exception):
    """Raised when connection is lost during a request."""
    pass

class RequestTimeoutError(Exception):
    """Raised when a request times out."""
    pass