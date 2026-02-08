import time

import constants
from constants import SERVER
from util import uuid_util


# Discovery Messages

def discovery_request(component):
    return {
        "type": constants.DISCOVERY_REQUEST,
        "requester_type": component.type,
        "requester_uuid": component.uuid,
        "timestamp": time.time(),
        "requester_hostname": component.unicast.host_name,
        "requester_ip_address": component.unicast.ip_address,
        "requester_port": component.unicast.port,
    }


def discovery_response(discovery_request, component):
    return {
        "type": constants.DISCOVERY_RESPONSE,
        "respondent_type": SERVER,
        "respondent_uuid": component.uuid,
        "respondent_hostname": component.unicast.host_name,
        "respondent_ip_address": component.unicast.ip_address,
        "respondent_port": component.unicast.port,
        "timestamp": time.time(),
        "response_to": discovery_request.get("requester_uuid")
    }


# Election Messages

def leader_election_request(server, election_uuid):
    return {
        "type": constants.LEADER_ELECTION_REQUEST,
        "election_uuid": election_uuid,
        "requester_type": server.type,
        "requester_uuid": server.uuid,
        "timestamp": time.time()
    }


def leader_election_response(server, message):
    return {
        "type": constants.LEADER_ELECTION_RESPONSE,
        "election_uuid": message["election_uuid"],
        "respondent_type": server.type,
        "respondent_uuid": server.uuid,
        "timestamp": time.time(),
        "response_to": message["requester_uuid"],
    }


def leader_ack_response(message, component, requester_uuid):
    return {
        "type": constants.LEADER_ACK_RESPONSE,
        "respondent_type": component.type,
        "respondent_uuid": component.uuid,
        "election_uuid": message["election_uuid"],
        "accepted": False,
        "timestamp": time.time(),
        "response_to": requester_uuid
    }


def leader_election_coordination_request(election_uuid, server):
    return {
        "type": constants.LEADER_ELECTION_COORDINATION_REQUEST,
        "requester_uuid": server.uuid,
        "election_uuid": election_uuid,
        "requester_type": server.type,
        "timestamp": time.time()
    }


# Heartbeat Messages

def heart_beat(component):
    return {
        "type": constants.HEART_BEAT,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "heart_beat_uuid": uuid_util.get_uuid(),
        "timestamp": time.time()
    }


def heart_beat_ack(component, heartbeat):
    return {
        "type": constants.HEART_BEAT_ACK,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "heart_beat_uuid": heartbeat["heart_beat_uuid"]
    }


def leader_info_response(component, leader_details):
    return {
        "type": constants.LEADER_DETAILS,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "leader_details": leader_details,
        "timestamp": time.time()
    }


def state_replicate(component, state_data):
    """Create a state replication message from leader to backups."""
    return {
        "type": constants.STATE_REPLICATE,
        "leader_uuid": component.uuid,
        "leader_type": component.type,
        "state": state_data,
        "timestamp": time.time()
    }


def request_state_replication(component):
    """Request state replication from a peer server."""
    return {
        "type": constants.STATE_REPLICATION_REQUEST,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "requester_ip_address": component.unicast.ip_address,
        "requester_port": component.unicast.port,
        "timestamp": time.time()
    }


def reassignment(failed_server, component):
    return {
        "type": constants.REASSIGNMENT,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "failed_uuid": failed_server,
        "timestamp": time.time()
    }


def auction_reassignment(component):
    return {
        "type": constants.REASSIGNMENT,
        "requester_type": component.type,
        "requester_uuid": component.uuid,
        "timestamp": time.time(),
        "details": {
            "uuid": component.uuid,
            "hostname": component.unicast.host_name,
            "ip_address": component.unicast.ip_address,
            "port": component.unicast.port,
            "type": component.type
        }
    }


# Auction Creation & Joining Messages

def auction_create_request(component, item_name, min_bid_price, min_rounds, min_bidders):
    return {
        "type": constants.AUCTION_CREATE_REQUEST,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "requester_hostname": component.unicast.host_name,
        "requester_ip_address": component.unicast.ip_address,
        "requester_port": component.unicast.port,
        "timestamp": time.time(),
        "item_name": item_name,
        "min_bid_price": min_bid_price,
        "min_rounds": min_rounds,
        "min_bidders": min_bidders
    }


def auction_create_ack(component, auction_id, item_name, min_bid_price, min_rounds,
                       min_bidders):
    return {
        "type": constants.AUCTION_CREATE_ACK,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "item_name": item_name,
        "min_bid_price": min_bid_price,
        "min_rounds": min_rounds,
        "min_bidders": min_bidders
    }


def auction_create_deny(component, reason):
    return {
        "type": constants.AUCTION_CREATE_DENY,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "reason": reason
    }


def auction_list_request(component):
    return {
        "type": constants.AUCTION_LIST_REQUEST,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "requester_hostname": component.unicast.host_name,
        "requester_ip_address": component.unicast.ip_address,
        "requester_port": component.unicast.port,
        "timestamp": time.time()
    }


def auction_list_response(component, auctions):
    return {
        "type": constants.AUCTION_LIST_RESPONSE,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auctions": auctions
    }


def auction_join_request(component, auction_id):
    return {
        "type": constants.AUCTION_JOIN_REQUEST,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "requester_hostname": component.unicast.host_name,
        "requester_ip_address": component.unicast.ip_address,
        "requester_port": component.unicast.port,
        "timestamp": time.time(),
        "auction_id": auction_id
    }


def auction_join_ack(component, auction_id, item_name, min_bid_price, min_rounds):
    return {
        "type": constants.AUCTION_JOIN_ACK,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "item_name": item_name,
        "min_bid_price": min_bid_price,
        "min_rounds": min_rounds
    }


def auction_join_deny(component, reason):
    return {
        "type": constants.AUCTION_JOIN_DENY,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "reason": reason
    }


# Auction Lifecycle Messages

def auction_ready_check(component, auction_id, num_bidders):
    return {
        "type": constants.AUCTION_READY_CHECK,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "num_bidders": num_bidders
    }


def auction_ready_confirm(component, auction_id):
    return {
        "type": constants.AUCTION_READY_CONFIRM,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id
    }


def auction_start(component, auction_id, item_name, min_bid_price, min_rounds, participants):
    return {
        "type": constants.AUCTION_START,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "item_name": item_name,
        "min_bid_price": min_bid_price,
        "min_rounds": min_rounds,
        "participants": participants
    }


def auction_cancel(component, auction_id, reason):
    return {
        "type": constants.AUCTION_CANCEL,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "reason": reason
    }


# Bidding Messages

def round_start(component, auction_id, round_num, min_bid_price):
    return {
        "type": constants.ROUND_START,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "round": round_num,
        "min_bid_price": min_bid_price
    }


def bid_submit(component, auction_id, round_num, bid_amount):
    return {
        "type": constants.BID_SUBMIT,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "round": round_num,
        "bid_amount": bid_amount
    }


def bid_submit_retransmit(component, auction_id, round_num, bid_amount):
    return {
        "type": constants.BID_SUBMIT_RETRANSMIT,
        "requester_uuid": component.uuid,
        "requester_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "round": round_num,
        "bid_amount": bid_amount
    }


def bid_broadcast(component, auction_id, round_num, client_uuid, bid_amount):
    return {
        "type": constants.BID_BROADCAST,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "round": round_num,
        "client_uuid": client_uuid,
        "bid_amount": bid_amount
    }


def round_complete(component, auction_id, round_num, bids):
    return {
        "type": constants.ROUND_COMPLETE,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "round": round_num,
        "bids": bids
    }


# Auction Completion Messages

def auction_winner(component, auction_id, item_name, winning_amount, cumulative_bids):
    return {
        "type": constants.AUCTION_WINNER,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "item_name": item_name,
        "winning_amount": winning_amount,
        "cumulative_bids": cumulative_bids
    }


def auction_loser(component, auction_id, item_name, winner, winning_amount, cumulative_bids):
    return {
        "type": constants.AUCTION_LOSER,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "item_name": item_name,
        "winner": winner,
        "winning_amount": winning_amount,
        "cumulative_bids": cumulative_bids
    }


def auction_result(component, auction_id, item_name, winner, winning_amount, all_bids):
    return {
        "type": constants.AUCTION_RESULT,
        "respondent_uuid": component.uuid,
        "respondent_type": component.type,
        "timestamp": time.time(),
        "auction_id": auction_id,
        "item_name": item_name,
        "winner": winner,
        "winning_amount": winning_amount,
        "all_bids": all_bids
    }
