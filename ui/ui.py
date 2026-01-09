from message.message_handler import MessageHandler
from message.message_types import ClientUiMessageType

class Ui:
    def __init__(self, client_msg_queue):
        self.client_messgae_queue = client_msg_queue
        self.ui_message_handler = MessageHandler()
        self._register_callbacks()
        self.ui_message_handler.start_message_handler()
        self.ui_should_exit = False

    def _register_callbacks(self):
        self.ui_message_handler.register_handler(ClientUiMessageType.SHOW_DISCONNECTED.value, self.handle_show_disconnected)

    def handle_show_disconnected(self, msg):
        print(f"Waiting to connect to leade {msg}")
        

    def start_ui_loop(self):
        while not self.ui_should_exit:
            try:
