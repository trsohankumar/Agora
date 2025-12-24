import uuid
import random
import time
import threading

from loguru import logger
from enum import Enum
from collections import defaultdict

from broadcast.broadcast import Broadcast
from unicast.unicast import Unicast
from message.message_handler import MessageHandler
from message.message_types import ServerMessageType, ClientMessageType
from node_list import NodeList
from log.log_entries import LogEntries
from utils.common import get_ip_port

class ServerState(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


class Server:
    def __init__(self):
        self.server_id = uuid.uuid4()
        self.state = ServerState.FOLLOWER
        self.server_ip, self.server_port = get_ip_port()
        self.peer_list = NodeList()
        self.client_list = NodeList()
        logger.info(f"Server starting with id: {self.server_id}, ip: {self.server_ip}, port: {self.server_port}")
        # setup message resolver for the server
        self.message_handler = MessageHandler(self)
        self.discovery_complete = False
        self.register_callbacks()
        # setup unicast communication for the server
        self.unicast = Unicast(unicast_ip= self.server_ip, unicast_port=self.server_port)

        # setup broadcast communication for the server
        self.broadcast = Broadcast(self.server_ip)

        self.term = 0
        self.voted_for = None
        self.log = []

        self.commit_index = 0
        self.last_applied = -1

        self.next_index = {}
        self.match_index = {}

        self.election_timeout = self._get_random_election_timeout()
        self.last_heartbeat_time = time.time()
        self.votes_received = set()
        self.state_lock = threading.Lock()
        self.heartbeat_interval = 0.05
    
    def _get_random_election_timeout(self):
        return random.uniform(0.15, 0.30)
    
    def handle_disc_resp(self, msg):
        
        if msg["id"] == str(self.server_id):
            return

        logger.info(f"Handling message: {msg}")
        if self.peer_list.get_node(msg["id"]) == None:
            self.peer_list.add_node(msg["id"], {"ip": msg["ip"], "port": msg["port"]})

    def handle_disc_req(self, msg):
        if msg["id"] == str(self.server_id):
            return
        logger.info(f"Handling message: {msg}")
        if self.peer_list.get_node(msg["id"]) == None:
            self.peer_list.add_node(msg["id"], {"ip": msg["ip"], "port": msg["port"]})
            return_messge = {
                "type": ServerMessageType.RES_DISC.value,
                "ip": self.server_ip,
                "port": self.server_port,
                "id": str(self.server_id)
            }
            self.unicast.send_message(return_messge, msg["ip"], msg["port"])

    def register_callbacks(self):
        self.message_handler.register_handler(ServerMessageType.REQ_DISC.value, self.handle_disc_req)
        self.message_handler.register_handler(ServerMessageType.RES_DISC.value, self.handle_disc_resp)
        self.message_handler.register_handler(ServerMessageType.REQ_VOTE.value, self.handle_request_vote)
        self.message_handler.register_handler(ServerMessageType.RES_VOTE.value, self.handle_vote_resp)
        self.message_handler.register_handler(
            ServerMessageType.REQ_APPEND_ENTRIES.value, self.handle_append_entries
        )
        self.message_handler.register_handler(ClientMessageType.REQ_DISC.value, self.connect_client)
        self.message_handler.register_handler(
            ServerMessageType.RES_APPEND_ENTRIES.value, self.handle_append_entries_resp
        )

    def connect_client(self, message):
        if message["id"] == str(self.server_id):
            return

        with self.state_lock:
            if self.state != ServerState.LEADER:
                return
            self.log.append(LogEntries(self.term, message))
 

    def start_server(self):
        self.message_handler.start_message_handler()
        self.unicast.start_unicast_listen(self.message_handler)
        self.broadcast.start_broadcast_listen(self.message_handler)
        broadcast_message = {
            "type": ServerMessageType.REQ_DISC.value,
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
                    self.transiton_to_candidate()
                time.sleep(self.heartbeat_interval)
            elif current_state == ServerState.CANDIDATE:
                if timeout_since_heartbeat > self.election_timeout:
                    logger.info("Candidate timeout occurred. Starting new election")
                    self.transiton_to_candidate()
                time.sleep(self.heartbeat_interval)
            elif current_state == ServerState.LEADER:
                self.send_heartbeat()
                time.sleep(self.heartbeat_interval)
            
            with self.state_lock:
                if self.commit_index > self.last_applied and self.last_applied + 1 < len(self.log):
                    # apply the logs to state machine
                    self.last_applied+=1
                    message =self.log[self.last_applied].command
                    match message.get("type"):
                        case ClientMessageType.REQ_DISC:
                            #
                            self.client_list.add_node(
                                message.get("id"),
                                {"ip": message.get("ip"), "port": message.get("port")}
                            )
                            if self.state == ServerState.LEADER:
                                self.unicast.send_message(
                                    {
                                        "type": ClientMessageType.RES_DISC.value,
                                        "id": str(self.server_id),
                                        "ip": self.server_ip,
                                        "port": self.server_port
                                    },
                                    message.get("ip"),
                                    message.get("port")
                                )
                        case _:
                            logger.info("default case")


    def transiton_to_candidate(self):
        with self.state_lock:
            self.term += 1
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
                "type": ServerMessageType.REQ_VOTE.value,
                "term": self.term,
                "id": str(self.server_id),
                "ip": self.server_ip,
                "port": self.server_port,
                "last_log_index": len(self.log) - 1,
                "last_log_term": self.log[-1].term if len(self.log) > 0 else 0
            }
            self.unicast.send_message(vote_request, peer_info["ip"], peer_info["port"])

    def check_election_won(self):
        with self.state_lock:
            if self.state != ServerState.CANDIDATE:
                return
            
            total_nodes = len(self.peer_list.get_all_node()) + 1
            if len(self.votes_received) > (total_nodes // 2):
                logger.info(f"Server: {self.server_id} has won the election for term: {self.term}")
                self.state = ServerState.LEADER
                peers = self.peer_list.get_all_node()
                for peer_id in peers.keys():
                    self.next_index[peer_id] = len(self.log)
                    self.match_index[peer_id] = - 1

    def handle_request_vote(self, msg):
        if msg["id"] == str(self.server_id):
            return
        with self.state_lock:
            grant_vote = False

            if msg["term"] > self.term:
                self.term = msg["term"]
                self.state = ServerState.FOLLOWER
                self.voted_for = None

            if msg["term"] == self.term:
                if self.voted_for is None or self.voted_for == msg["id"]:
                    server_last_log_term = self.log[-1].term if len(self.log) > 0 else 0
                    server_last_log_index = len(self.log) - 1 

                    vote_possible = (
                        msg["last_log_term"] > server_last_log_term or
                        (msg["last_log_term"] == server_last_log_term and msg["last_log_index"] >= server_last_log_index)
                    )

                    if vote_possible:
                        grant_vote = True
                        self.voted_for = msg["id"]
                        self.last_heartbeat_time = time.time()

            term = self.term
        vote_response = {
            "type" : ServerMessageType.RES_VOTE.value,
            "id": str(self.server_id),
            "term" : term,
            "vote_granted": grant_vote,
            "voter_id": str(self.server_id)
        }

        self.unicast.send_message(vote_response, msg["ip"], msg["port"])
        logger.info(f"Vote {'GRANTED' if grant_vote else 'DENIED'} for {msg['id']} for term: {self.term}")

    def handle_vote_resp(self, msg):
        if msg["id"] == str(self.server_id):
            return
        with self.state_lock:
            if self.state != ServerState.CANDIDATE or msg["term"] != self.term:
                return
            
            if msg["vote_granted"]:
                self.votes_received.add(msg["voter_id"])
                logger.info(f"Received vote from {msg['voter_id']}. Total: {len(self.votes_received)}")

        self.check_election_won()

    def send_heartbeat(self):
        logger.info("sending heartbeats")
        peers = self.peer_list.get_all_node()

        with self.state_lock:
            for peer_id, peer_info in peers.items():
                # edge case to be handled
                prev_log_idx = self.next_index[peer_id] - 1
                heartbeat_msg = {
                    "type": ServerMessageType.REQ_APPEND_ENTRIES.value,
                    "term": self.term,
                    "id": str(self.server_id),
                    "ip": self.server_ip,
                    "port": self.server_port,
                    "prev_log_index": prev_log_idx,
                    "prev_log_term": self.log[prev_log_idx].term if prev_log_idx >= 0 else 0,
                    "leader_commit": self.commit_index,
                    "entries": self.log[self.next_index.get(peer_id):]
                }
                self.unicast.send_message(heartbeat_msg, peer_info["ip"], peer_info["port"])

    def handle_append_entries(self, msg):
        if msg["id"] == str(self.server_id):
            return
        
        with self.state_lock:
                
            if msg["term"] > self.term:
                self.term = msg["term"]
                self.state = ServerState.FOLLOWER
                self.voted_for = None

            if msg["term"] < self.term:
                resp = False
            elif msg["prev_log_index"] >= len(self.log):
                resp = False
            elif msg["prev_log_index"] >= 0 and msg["prev_log_term"] != self.log[msg["prev_log_index"]].term:
                resp = False
            else:
                try:
                    del self.log[msg["prev_log_index"] + 1:]
                except IndexError:
                    pass
                self.log.extend(msg["entries"])

                if msg["leader_commit"] > self.commit_index:
                    self.commit_index = min(msg["leader_commit"], len(self.log) - 1)
                resp = True
            append_entries_response = {
                "type": ServerMessageType.RES_APPEND_ENTRIES.value,
                "term": self.term,
                "success": resp,
                "id": str(self.server_id)
            }
            self.election_timeout = self._get_random_election_timeout()
            self.last_heartbeat_time = time.time()
        self.unicast.send_message(append_entries_response, msg["ip"], msg["port"])


    def handle_append_entries_resp(self, msg):
        if msg["id"] == str(self.server_id):
            return

        with self.state_lock:
            if self.term < msg.get("term"):
                self.term = msg.get("term")
                self.state = ServerState.FOLLOWER
                return
            
            if msg.get("success") == False:
                self.next_index[msg.get("id")] -= 1

            if msg["success"] == True and msg["term"] == self.term: 
                self.match_index[msg.get("id")] = self.next_index[msg.get("id")]
                self.next_index[msg.get("id")] += 1

            index_count = defaultdict(int)
            for ind in self.match_index.values():
                index_count[ind] += 1
            index_count[len(self.log) - 1] += 1
            for key, val in index_count.items():
                if key > self.commit_index and val > (self.peer_list.get_len() + 1)//2 and self.log[key].term == self.term:
                    self.commit_index = key



if __name__ == "__main__":

    server = Server()
    server.start_server()