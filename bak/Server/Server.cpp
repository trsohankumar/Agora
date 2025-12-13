//
// Created by Sohankumar Rajeeshkumar on 01.11.25.
//

#include "Server.h"

Agora::Server::Server(Configuration config)
    : vServerDetails() , vHeartBeatTimeOut(10000), vHeartBeat(){

    spdlog::info("Server created with uuid: {}", uuids::to_string(vServerDetails.getNodeIdentifier()));

	vBroadcastAddress = vServerDetails.getNodeIpAddress().substr(0, vServerDetails.getNodeIpAddress().find_last_of('.')+1) + "255";
	spdlog::info("Broadcast address: {}", vBroadcastAddress);
    
    uint16_t broadcastPort = static_cast<uint16_t>(std::stoi(config.getValue("broadcastPort")));
    vDiscovery = std::make_unique<Agora::Discovery>(vServerDetails.getNodeIdentifier(), vServerDetails.getNodeIpAddress(), vServerDetails.getNodePort(), vBroadcastAddress, broadcastPort);

    // Start Broadcast
    StartBroadCast();

    // list to BroadCast
    ListenBroadCast();
    
    spdlog::info("Switching to follower state");
    // Server has joined the network and switches itself to follower mode where it awaits HeartBeat
    behavior = Agora::BEHAVIOR::FOLLOWER;

    Listen();
}

void Agora::Server::StartBroadCast() {
    // setup thread for broadcasting
    std::thread(&Agora::Discovery::Broadcast, vDiscovery.get(),std::ref(vDiscoveredPeers), std::ref(vDiscoveredPeersMutex)).detach();
}

void Agora::Server::ListenBroadCast() {
   std::thread(&Agora::Discovery::Listen, vDiscovery.get(), std::ref(vDiscoveredPeers), std::ref(vDiscoveredPeersMutex)).detach();
}

void Agora::Server::startFollowerState() {
    // Wait for HeartBeat
    while (true) {
    	bool isLeaderAvailable = vHeartBeat.receiveHeartBeat(vHeartBeatTimeOut);
		// If timedout change state to Candiddate
		if(!isLeaderAvailable) {
   			spdlog::info("Failed to receive HeartBeat from server");
    		behavior = Agora::BEHAVIOR::CANDIDATE;
    		return;
 		}
		// Else Add entry to log
		spdlog::info("Heartbeat: {}");


    }

}


void startElection(){

}

void Agora::Server::Listen() {

    while(true) {
        switch (behavior) {
        case Agora::BEHAVIOR::FOLLOWER:
           // Follower based code
        spdlog::info("Server in Follower State");
        startFollowerState();
        break;
        case Agora::BEHAVIOR::CANDIDATE:
        spdlog::info("Server in Candidate State");
        startElection();
        break;
        // Initiate election process
        case Agora::BEHAVIOR::LEADER:
	    spdlog::info("Server in Leader State");
        break;
        }
    }

}
