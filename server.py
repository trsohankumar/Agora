from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from message.message_handler import MessageHandler
from node_list import NodeList

from loguru import logger
import uuid
import threading
import socket
import time
import random
from enum import Enum
import random

class ServerState(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"

def get_ip_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(("8.8.8.8", 80))
    return {
        "ip" : sock.getsockname()[0],
        "port" : sock.getsockname()[1]
    }

class Server:
    def __init__(self):
        self.server_id = uuid.uuid4()
        res = get_ip_port()
        self.state = ServerState.FOLLOWER

        self.server_ip = res["ip"]
        self.server_port = res["port"]
        self.peer_list = NodeList()
        logger.info(f"Server starting with id: {self.server_id}, ip: {self.server_ip}, port: {self.server_port}")
        # setup message resolver for the server
        self.message_queue = MessageHandler(self)
        self.discovery_complete = False

        # setup unicast communication for the server
        self.unicast = Unicast(unicast_ip= self.server_ip, unicast_port=self.server_port)

        # setup broadcast communication for the server
        self.broadcast = Broadcast(self.server_ip)

        self.current_term = 0
        self.voted_for = None
        self.log = []

        self.commit_index = 0
        self.last_applied = 0

        self.next_index = {}
        self.match_index = {}

        self.election_timeout = self._get_random_election_timeout()
        self.last_heartbeat_time = time.time()
        self.votes_received = set()
        self.state_lock = threading.Lock()
    
    def _get_random_election_timeout(self):
        return random.uniform(0.15, 0.30)


    def start_server(self):
        self.message_queue.start_message_handler()
        self.unicast.start_unicast_listen(self.message_queue)
        self.broadcast.start_broadcast_listen(self.message_queue)
        broadcast_message = {
            "type": "DISC",
            "id": str(self.server_id),
            "ip": self.server_ip,
            "port": self.server_port
        }
        for _ in range(5):
            self.broadcast.send_broadcast(broadcast_message)
            time.sleep(1)

        self.discovery_complete = True
        logger.info(f"Discovery complete: No of peers found{len(self.peer_list.get_all_node())}")

        self.last_heartbeat_time = time.time()

        self.run_server_loop()


    def run_server_loop(self):
        while True:
            with self.state_lock:
                current_state = self.state
                timeout_since_heartbeat = time.time() - self.last_heartbeat_time
            if current_state == ServerState.FOLLOWER:
                if self.discovery_complete and timeout_since_heartbeat > self.election_timeout:
                    logger.info("Election timeout occurred")
                    self.transisiton_to_candidate()
            elif current_state == ServerState.CANDIDATE:
                if timeout_since_heartbeat > self.election_timeout:
                    logger.info("Candidate timeout occurred. Starting new election")
                    self.transisiton_to_candidate()
            elif current_state == ServerState.LEADER:
                pass

    def transisiton_to_candidate(self):
        with self.state_lock:
            self.current_term += 1
            self.state = ServerState.CANDIDATE
            self.voted_for = str(self.server_id)
            self.votes_received =  {str(self.server_id)}
            self.election_timeout = self._get_random_election_timeout()
            self.last_heartbeat_time = time.time()

        self.send_request_vote()
        self.check_election_won()

    def send_request_vote(self):
        peers = self.peer_list.get_all_node()
        for peer_id, peer_info in peers.items():
            vote_request = {
                "type": "VOTE_REQ",
                "term": self.current_term,
                "id": str(self.server_id),
                "ip": self.server_ip,
                "port": self.server_port,
                "last_log_index": len(self.log) - 1,
                "last_log_term": self.log[-1]["term"] if self.log else 0
            }
            self.unicast.send_message(vote_request, peer_info["ip"], peer_info["port"])

    def check_election_won(self):
        with self.state_lock:
            if self.state != ServerState.CANDIDATE:
                return
            
            total_nodes = len(self.peer_list.get_all_node()) + 1
            if len(self.votes_received) > (total_nodes / 2):
                logger.info(f"Server: {self.server_id} has won the election for term: {self.current_term}")
                self.state = ServerState.LEADER
                peers = self.peer_list.get_all_node()
                for peer_id in peers.keys():
                    self.next_index[peer_id] = len(self.log)
                    self.match_index[peer_id] = - 1

    def handle_request_vote(self, msg):
        with self.state_lock:
            grant_vote = False

            if msg["term"] > self.current_term:
                self.current_term = msg["term"]
                self.state = ServerState.FOLLOWER
                self.voted_for = None

            if msg["term"] == self.current_term:
                if self.voted_for is None or self.voted_for == msg["id"]:
                    server_last_log_term = self.log[-1]["term"] if self.log else 0
                    server_last_log_index = len(self.log) - 1 

                    vote_possible = (
                        msg["last_log_term"] > server_last_log_term or
                        (msg["last_log_term"] == server_last_log_term and msg["last_log_index"] >= server_last_log_index)
                    )

                    if vote_possible:
                        grant_vote = True
                        self.voted_for = msg["id"]
                        self.last_heartbeat_time = time.time()
            current_term = self.current_term
        vote_response = {
            "type" : "VOTE_RESP",
            "id": str(self.server_id),
            "term" : current_term,
            "vote_granted": grant_vote,
            "voter_id": str(self.server_id)
        }

        self.unicast.send_message(vote_response, msg["ip"], msg["port"])
        logger.info(f"Vote {'GRANTED' if grant_vote else 'DENIED'} for {msg['id']} for term: {self.current_term}")

    def handle_vote_resp(self, msg):
        with self.state_lock:
            if self.state != ServerState.CANDIDATE or msg["term"] != self.current_term:
                return
            
            if msg["vote_granted"]:
                self.votes_received.add(msg["voter_id"])
                logger.info(f"Received vote from {msg['voter_id']}. Total: {len(self.votes_received)}")

        self.check_election_won()


if __name__ == "__main__":

    server = Server()
    server.start_server()