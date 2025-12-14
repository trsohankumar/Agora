from broadcast.broadcast import Broadcast
from loguru import logger
import uuid

if __name__ == "__main__":
    broadcast = Broadcast()

    server_id = uuid.uuid4()
    logger.info(f"{server_id} has started")
    message = {
        "id": str(server_id)
    }
    broadcast.send_broadcast(message)
    broadcast.listen_broadcast()