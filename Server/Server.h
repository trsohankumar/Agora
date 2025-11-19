//
// Created by Sohankumar Rajeeshkumar on 01.11.25.
//

#pragma once
#include <string>
#include <arpa/inet.h>
#include <spdlog/spdlog.h>
#include <uuid.h>
#include "../Discovery/Discovery.h"
#include "../Utility/Configuration.h"
#include "../Node/Node.h"

namespace Agora {
class Server {

public:
         Server(Configuration config);
    void Listen();
private:

    void StartBroadCast();
    void ListenBroadCast();

    Agora::Node                         vServerDetails;
	std::string                         vBroadcastAddress;
    std::unique_ptr<Agora::Discovery>   vDiscovery;
    std::vector<Agora::Node>            vDiscoveredPeers;
    std::mutex                          vDiscoveredPeersMutex;
};
};