import threading
from dataclasses import dataclass, asdict
from utils.common import get_ip_port
from typing import Dict


@dataclass
class Node:
    """
    class Node to replace the node_info dictionary
    """

    _id: str
    ip: str
    port: str

    def dict(self):
        return {k: str(v) for k, v in asdict(self).items()}

class NodeList:
    """
        This class is responsible to maintain a list of nodes
    """
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.lock = threading.Lock()

    def add_node(self, node_id:str, node_info:Node):
        """
            method adds a node to the node list
        """
        with self.lock:
            if node_id not in self.nodes:
                self.nodes[node_id] = node_info
            else:
                self.nodes[node_id].update(node_info)

    def get_node(self, node_id):
        with self.lock:
            return self.nodes.get(node_id)

    def get_all_node(self):
        with self.lock:
            return self.nodes.copy()

    def remove_node(self, node_id):
        with self.lock:
            return self.nodes.pop(node_id, None)

    def get_len(self):
        with self.lock:
            return len(self.nodes)
