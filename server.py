from broadcast.broadcast import Broadcast
from message.message_handler import MessageHandler

from loguru import logger
import uuid
import threading

if __name__ == "__main__":
    broadcast = Broadcast()

    server_id = uuid.uuid4()
    logger.info(f"{server_id} has started")
    message = {
        "id": str(server_id)
    }
    message_queue = MessageHandler()
    message_queue.start_message_handler()
    threading.Thread(target=broadcast.listen_broadcast,args=(message_queue,), daemon=True).start()
    broadcast.send_broadcast(message)
    while True:
        pass