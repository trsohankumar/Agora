import threading
from dataclasses import dataclass

@dataclass
class Node:
    """
        class Node to replace the node_info dictionary
    """
    _id: str
    ip: str
    port: str


class NodeList:    
    def __init__(self):
        self.nodes = {}
        self.lock = threading.Lock()
    
    def add_node(self, node_id, node_info):
        with self.lock:
            if node_id not in self.nodes:
                self.nodes[node_id] = node_info
                return True
            else:
                self.nodes[node_id].update(node_info)
                return False
    
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
