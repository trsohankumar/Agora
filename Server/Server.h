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
#include "HeartBeat/HeartBeat.h"

namespace Agora {
enum BEHAVIOR{
    FOLLOWER,
    CANDIDATE,
    LEADER,
};

class Server {

public:
         Server(Configuration config);
    void Listen();
private:

    void StartBroadCast();
    void ListenBroadCast();
    void startReceiveHeartbeat();
    void startFollowerState();

    Agora::Node                         vServerDetails;
    Agora::HeartBeat                     vHeartBeat;

	std::string                         vBroadcastAddress;
    std::unique_ptr<Agora::Discovery>   vDiscovery;
    std::vector<Agora::Node>            vDiscoveredPeers;
    std::mutex                          vDiscoveredPeersMutex;
    //std::vector<Agora::Logreplica>      vLogReplica;
    // Properties of server that help with
    Agora::BEHAVIOR                      behavior;
    std::chrono::milliseconds     vHeartBeatTimeOut;
    int                           TERM;
};
};