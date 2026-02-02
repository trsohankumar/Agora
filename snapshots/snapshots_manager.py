import glob
import json
import os
import tempfile
import threading
import time

from loguru import logger

import constants
from util import request_response_handler, uuid_util


class SnapshotsManager:

    def __init__(self, component):
        self.component = component
        self.folder_created = False
        self.folder_path = None
        self.recording = False
        self.snapshot = None
        self.remote_snapshot = False

    def get_a_cut(self):
        pass

    def initiate_snapshot(self):
        if hasattr(self.component, 'is_leader') and self.component.is_leader:
            threading.Timer(constants.SNAPSHOT_INTERVAL, self.initiate_snapshot).start()
            logger.info("{} - {} Initiating Snapshot", self.component.type, self.component.uuid)
            self.record()
            self.send_marker([self.component.uuid])

    def record(self):
        self.recording = True
        self.snapshot = self.take_a_snapshot()
        logger.debug("{} - {} - Recorded Snapshot", self.component.type, self.component.uuid)

    def send_marker(self, marked_participants):
        discovered_servers = dict(self.component.discovered_servers)
        discovered_clients = dict(self.component.discovered_clients) if hasattr(self.component,
                                                                                'discovered_clients') else None

        if discovered_servers:
            for _, server in discovered_servers.items():
                self.send_marker_to(server, marked_participants)

        if discovered_clients:
            for _, client in discovered_clients.items():
                self.send_marker_to(client, marked_participants)

    def send_marker_to(self, target, marked_participants):
        if target["uuid"] not in marked_participants:
            logger.debug("{} - {} - Sending marker to {}", self.component.type, self.component.uuid, target["uuid"])
            self.component.udp.unicast(
                request_response_handler.snapshot_marker(self.component, marked_participants),
                target["ip_address"],
                target["port"]
            )

    def handle_marker(self, message):
        logger.debug("{} - {} got a marker {}", self.component.type, self.component.uuid, message)
        if not self.recording:
            logger.debug("{} - {} not recording", self.component.type, self.component.uuid)
            self.record()
            existing_marked_participants = list(message["from"])
            existing_marked_participants.append(self.component.uuid)
            self.send_marker(existing_marked_participants)
        else:
            logger.debug("{} - {} already recording", self.component.type, self.component.uuid)
            self.recording = False

    def take_a_snapshot(self):
        if not self.folder_created:
            self.create_folder()
        snapshot = self.capture_server_state() if self.component.type == constants.SERVER else self.capture_client_state()
        self.create_snapshot_file(snapshot)
        return snapshot

    def create_snapshot_file(self, snapshot_payload):
        snapshot_file_path = os.path.join(self.folder_path, str(int(time.time())) + ".json")
        try:
            with open(snapshot_file_path, 'w') as snapshot_file:
                snapshot_file.write(json.dumps(snapshot_payload))
            logger.debug("File {} created", snapshot_file_path)
        except Exception as e:
            logger.error("Exception while creating file: {}", e)

    def capture_client_state(self):
        auction_manager = self.component.messages_manager.auction_manager
        return {
            "snapshot_id": uuid_util.get_uuid(),
            "timestamp": time.time(),
            "client_uuid": self.component.uuid,
            "type": self.component.type,
            "discovered_servers": dict(self.component.discovered_servers),
            "queues": {
                "client": list(self.component.queues["client"])
            },
            "auction": {
                "auction_id": auction_manager.auction_id,
                "is_auctioneer": auction_manager.is_auctioneer,
                "item_name": auction_manager.item_name,
                "min_bid_price": auction_manager.min_bid_price,
                "current_round": auction_manager.current_round,
                "my_bids": dict(auction_manager.my_bids),
                "participants": list(auction_manager.participants),
                "is_active": auction_manager.is_active,
                "is_finished": auction_manager.is_finished,
                "server": auction_manager.server
            }
        }

    def capture_server_state(self):
        auction_manager = self.component.messages_manager.auction_manager

        # Convert auctions to serializable format
        auctions_data = {}
        for auction_id, auction in dict(auction_manager.auctions).items():
            bids_data = {}
            for round_num, round_bids in dict(auction.get("bids", {})).items():
                bids_data[str(round_num)] = dict(round_bids)

            auctions_data[auction_id] = {
                "auction_id": auction.get("auction_id"),
                "item_name": auction.get("item_name"),
                "min_bid_price": auction.get("min_bid_price"),
                "min_rounds": auction.get("min_rounds"),
                "min_bidders": auction.get("min_bidders"),
                "auctioneer_uuid": auction.get("auctioneer_uuid"),
                "participants": list(auction.get("participants", [])),
                "current_round": auction.get("current_round"),
                "bids": bids_data,
                "status": auction.get("status"),
                "multicast_ip": auction.get("multicast_ip"),
                "multicast_port": auction.get("multicast_port")
            }

        return {
            "snapshot_id": uuid_util.get_uuid(),
            "timestamp": time.time(),
            "server_uuid": self.component.uuid,
            "type": self.component.type,
            "discovered_servers": dict(self.component.discovered_servers),
            "discovered_clients": dict(self.component.discovered_clients),
            "is_leader": self.component.is_leader,
            "leader": self.component.leader,
            "queues": {
                "client": list(self.component.queues["client"]),
                "discovery": list(self.component.queues["discovery"]),
                "heartbeat": list(self.component.queues["heartbeat"]),
                "election": list(self.component.queues["election"])
            },
            "auctions": {
                "running_auctions": auctions_data,
                "clients": dict(auction_manager.clients),
                "assignments": dict(auction_manager.assignments)
            }
        }

    def create_folder(self):
        temp_dir = tempfile.gettempdir()
        self.folder_path = os.path.join(temp_dir, self.component.uuid)
        try:
            os.makedirs(self.folder_path, exist_ok=True)
            logger.info("Snapshots Folder {} created", self.folder_path)
        except Exception as e:
            logger.error("Exception while creating folder {}: {}", self.folder_path, e)

    def get_latest_snapshot(self, uuid):
        files = glob.glob(os.path.join(os.path.join(tempfile.gettempdir(), str(uuid)), "*.json"))
        if not files:
            return None
        latest_file = max(files, key=os.path.getctime)
        with open(latest_file, "r", encoding="utf-8") as file:
            return json.load(file)

    def is_snapshot_local(self, uuid):
        return self.get_latest_snapshot(uuid) is not None

    def restore_from_snapshot_json(self, snapshot_json):
        logger.info("Restoring from json")

        for server, server_details in snapshot_json.get("discovered_servers", {}).items():
            if server not in self.component.discovered_servers and server != self.component.uuid:
                self.component.discovered_servers[server] = server_details

        for client, client_details in snapshot_json.get("discovered_clients", {}).items():
            if client not in self.component.discovered_clients:
                self.component.discovered_clients[client] = client_details

        auctions_data = snapshot_json.get("auctions", {})
        auction_manager = self.component.messages_manager.auction_manager
        mp_manager = auction_manager.manager

        # Restore running auctions
        for auction_id, auction_data in auctions_data.get("running_auctions", {}).items():
            if auction_id not in auction_manager.auctions:
                # Recreate the auction with multiprocessing-compatible structures
                auction = mp_manager.dict({
                    "auction_id": auction_data.get("auction_id"),
                    "item_name": auction_data.get("item_name"),
                    "min_bid_price": auction_data.get("min_bid_price"),
                    "min_rounds": auction_data.get("min_rounds"),
                    "min_bidders": auction_data.get("min_bidders"),
                    "auctioneer_uuid": auction_data.get("auctioneer_uuid"),
                    "participants": mp_manager.list(auction_data.get("participants", [])),
                    "current_round": auction_data.get("current_round"),
                    "status": auction_data.get("status"),
                    "multicast_ip": auction_data.get("multicast_ip"),
                    "multicast_port": auction_data.get("multicast_port")
                })

                # Restore bids
                bids = mp_manager.dict()
                for round_num, round_bids in auction_data.get("bids", {}).items():
                    bids[int(round_num)] = mp_manager.dict(round_bids)
                auction["bids"] = bids

                auction_manager.auctions[auction_id] = auction

        # Restore clients
        for client, client_details in auctions_data.get("clients", {}).items():
            if client not in auction_manager.clients:
                auction_manager.clients[client] = client_details

        # Restore assignments
        for server_id, auction_ids in auctions_data.get("assignments", {}).items():
            if server_id not in auction_manager.assignments:
                auction_manager.assignments[server_id] = auction_ids

    def restore_latest_snapshot(self, uuid, remote):
        try:
            logger.info("Starting snapshot restoration for {}", uuid)
            if remote:
                logger.info("Initializing snapshot restoration from remote")
                self.remote_snapshot = True
                self.ask_snapshot(uuid)

                # Wait for remote snapshot with timeout
                timeout = 30  # seconds
                start_time = time.time()
                while self.remote_snapshot and (time.time() - start_time) < timeout:
                    time.sleep(0.5)

                if self.remote_snapshot:
                    logger.warning("Timeout waiting for remote snapshot after {}s", timeout)
                    self.remote_snapshot = False
                else:
                    logger.info("Remote snapshot restoration completed")
            else:
                logger.info("Restoring snapshot from local")
                latest_snapshot = self.get_latest_snapshot(uuid)
                if latest_snapshot:
                    self.restore_from_snapshot_json(latest_snapshot)
                else:
                    logger.warning("No local snapshot found for {}", uuid)
        except Exception as e:
            logger.warning("Exception while restoring snapshot from {}: {}".format(uuid, e))

    def restore_latest_remote_snapshot(self, message):
        """Restore state from a snapshot received from another server."""
        snapshot_data = message.get("snapshot")
        if snapshot_data:
            logger.info("Received remote snapshot, restoring...")
            self.restore_from_snapshot_json(snapshot_data)
            self.remote_snapshot = False
        else:
            logger.warning("Received empty snapshot response")

    def ask_snapshot(self, uuid):
        self.component.broadcast.broadcast(request_response_handler.send_snapshot(self.component, uuid))

    def send_snapshot(self, component_uuid):
        """Send snapshot of specified component to the requesting leader."""
        latest_snapshot = self.get_latest_snapshot(component_uuid)
        if latest_snapshot:
            # We have a snapshot for the requested component, send it to the leader
            leader = self.component.discovered_servers.get(self.component.leader)
            if leader:
                logger.info("Sending snapshot for {} to leader {}", component_uuid, self.component.leader)
                self.component.udp.unicast(
                    request_response_handler.send_snapshot_response(self.component, latest_snapshot),
                    leader["ip_address"], leader["port"]
                )
            else:
                logger.warning("Cannot send snapshot - leader not found in discovered servers")
        else:
            logger.debug("No local snapshot available for {}", component_uuid)
