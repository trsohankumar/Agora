//
// Created by Sohankumar Rajeeshkumar on 01.11.25.
//

#include "Server.h"

Agora::Server::Server(Configuration config)
    : vServerDetails() {

    spdlog::info("Server created with uuid: {}", uuids::to_string(vServerDetails.getNodeIdentifier()));

	vBroadcastAddress = vServerDetails.getNodeIpAddress().substr(0, vServerDetails.getNodeIpAddress().find_last_of('.')+1) + "255";
	spdlog::info("Broadcast address: {}", vBroadcastAddress);
    
    uint16_t broadcastPort = static_cast<uint16_t>(std::stoi(config.getValue("broadcastPort")));
    vDiscovery = std::make_unique<Agora::Discovery>(vServerDetails.getNodeIdentifier(), vServerDetails.getNodeIpAddress(), vServerDetails.getNodePort(), vBroadcastAddress, broadcastPort);

    // Start Broadcast
    StartBroadCast();

    // list to BroadCast
    ListenBroadCast();
}

void Agora::Server::StartBroadCast() {
    // setup thread for broadcasting
    std::thread(&Agora::Discovery::Broadcast, vDiscovery.get(),std::ref(vDiscoveredPeers), std::ref(vDiscoveredPeersMutex)).detach();
}

void Agora::Server::ListenBroadCast() {
   std::thread(&Agora::Discovery::Listen, vDiscovery.get(), std::ref(vDiscoveredPeers), std::ref(vDiscoveredPeersMutex)).detach();
}

void Agora::Server::Listen() {

    spdlog::info("Server with ip: {} Listening on Port: {}", vServerDetails.getNodeIpAddress(), vServerDetails.getNodePort());
    while (true) {
    }
}
