import threading
import time

from loguru import logger

import constants
from util import request_response_handler


class StateReplicationManager:
    """
    Manages Primary-Backup state replication.

    The leader replicates its full state to all backup servers:
    - On key events (client join, auction changes)
    - Periodically (every REPLICATION_INTERVAL seconds)

    Backups store the replicated state in memory and use it
    when they become the new leader.
    """

    def __init__(self, server):
        self.server = server
        self.replicated_state = None  # State received from leader
        self.last_replication_time = None
        self.replication_timer = None

    def start_periodic_replication(self):
        """Start periodic state replication (leader only)."""
        if not self.server.is_leader:
            return

        self.replicate_state_to_backups()

        # Schedule next replication
        self.replication_timer = threading.Timer(
            constants.REPLICATION_INTERVAL,
            self.start_periodic_replication
        )
        self.replication_timer.daemon = True
        self.replication_timer.start()

    def stop_periodic_replication(self):
        """Stop periodic replication (when no longer leader)."""
        if self.replication_timer:
            self.replication_timer.cancel()
            self.replication_timer = None

    def replicate_state_to_backups(self):
        """Package current state and send to all backup servers."""
        if not self.server.is_leader:
            logger.debug("Not leader, skipping replication")
            return

        # Capture full state
        state_data = self.capture_full_state()

        # Send to all discovered servers (backups)
        backup_count = 0
        for server_uuid, server_details in dict(self.server.discovered_servers).items():
            if server_uuid != self.server.uuid:  # Don't send to self
                try:
                    self.server.udp.unicast(
                        request_response_handler.state_replicate(self.server, state_data),
                        server_details["ip_address"],
                        server_details["port"],
                        wait=False  # Non-blocking
                    )
                    backup_count += 1
                except Exception as e:
                    logger.warning("Failed to replicate state to {}: {}", server_uuid, e)

        if backup_count > 0:
            logger.debug("Replicated state to {} backup server(s)", backup_count)

        self.last_replication_time = time.time()

    def capture_full_state(self):
        """Capture complete server state for replication."""
        auction_manager = self.server.messages_manager.auction_manager

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
                "multicast_port": auction.get("multicast_port"),
                "ready_check_time": auction.get("ready_check_time")
            }

        return {
            "state_id": f"{self.server.uuid}_{int(time.time())}",
            "timestamp": time.time(),
            "leader_uuid": self.server.uuid,

            # Server discovery state
            "discovered_servers": dict(self.server.discovered_servers),
            "discovered_clients": dict(self.server.discovered_clients),

            # Auction state
            "auctions": {
                "running_auctions": auctions_data,
                "clients": dict(auction_manager.clients),
                "assignments": dict(auction_manager.assignments)
            }
        }

    def receive_replicated_state(self, message):
        """Receive and store replicated state from leader."""
        if self.server.is_leader:
            logger.debug("Ignoring replicated state - I am the leader")
            return

        leader_uuid = message.get("leader_uuid")
        state_data = message.get("state")

        if not state_data:
            logger.warning("Received empty state replication from {}", leader_uuid)
            return

        # Verify it's from the current leader
        if leader_uuid != self.server.leader:
            logger.warning("Received state from {} but current leader is {}",
                         leader_uuid, self.server.leader)
            return

        self.replicated_state = state_data
        logger.info("Received replicated state from leader {} (timestamp: {})",
                   leader_uuid, state_data.get("timestamp"))

    def restore_from_replicated_state(self):
        """Restore server state from replicated data (called when becoming leader)."""
        if not self.replicated_state:
            logger.warning("No replicated state available to restore")
            return False

        logger.info("Restoring state from replication (state_id: {})",
                   self.replicated_state.get("state_id"))

        try:
            # Restore discovered servers
            for server_uuid, server_details in self.replicated_state.get("discovered_servers", {}).items():
                if server_uuid not in self.server.discovered_servers and server_uuid != self.server.uuid:
                    self.server.discovered_servers[server_uuid] = server_details

            # Restore discovered clients
            for client_uuid, client_details in self.replicated_state.get("discovered_clients", {}).items():
                if client_uuid not in self.server.discovered_clients:
                    self.server.discovered_clients[client_uuid] = client_details

            # Restore auctions
            auctions_data = self.replicated_state.get("auctions", {})
            auction_manager = self.server.messages_manager.auction_manager

            # Ensure auction manager is initialized
            if auction_manager.manager is None:
                auction_manager.initialize()

            mp_manager = auction_manager.manager

            # Restore running auctions
            for auction_id, auction_data in auctions_data.get("running_auctions", {}).items():
                if auction_id not in auction_manager.auctions:
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
                        "multicast_port": auction_data.get("multicast_port"),
                        "ready_check_time": auction_data.get("ready_check_time")
                    })

                    # Restore bids
                    bids = mp_manager.dict()
                    for round_num, round_bids in auction_data.get("bids", {}).items():
                        bids[int(round_num)] = mp_manager.dict(round_bids)
                    auction["bids"] = bids

                    auction_manager.auctions[auction_id] = auction
                    logger.info("Restored auction {} for '{}'", auction_id, auction_data.get("item_name"))

            # Restore auction clients
            for client_uuid, client_details in auctions_data.get("clients", {}).items():
                if client_uuid not in auction_manager.clients:
                    auction_manager.clients[client_uuid] = client_details

            # Restore assignments
            for server_id, auction_ids in auctions_data.get("assignments", {}).items():
                if server_id not in auction_manager.assignments:
                    auction_manager.assignments[server_id] = auction_ids

            logger.info("State restoration complete. Auctions: {}, Clients: {}, Servers: {}",
                       len(auction_manager.auctions),
                       len(self.server.discovered_clients),
                       len(self.server.discovered_servers))

            return True

        except Exception as e:
            logger.error("Error restoring from replicated state: {}", e)
            import traceback
            traceback.print_exc()
            return False

    def has_replicated_state(self):
        """Check if we have replicated state available."""
        return self.replicated_state is not None

    def trigger_replication(self):
        """Trigger immediate state replication (called after important events)."""
        if self.server.is_leader:
            self.replicate_state_to_backups()
