//
// Created by Sohankumar Rajeeshkumar on 24.10.25.
//
#pragma once

#include <string>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <thread>
#include <uuid.h>
#include <spdlog/spdlog.h>
#include <chrono>
#include <nlohmann/json.hpp>

#include "../Node/Node.h"

namespace Agora{
class Discovery {
public:
            Discovery(uuids::uuid pEntityId, std::string pIpAddress, const uint16_t pPort, std::string pBroadcastAddress, const uint16_t pBroadcastPort);
    void    Broadcast(std::vector<Agora::Node>& pDiscoveredNodes, std::mutex& pDiscoveredNodesMutex) const;
    void    Listen(std::vector<Agora::Node>& pDiscoveredNodes, std::mutex& pDiscoveredNodesMutex ) const;
private:
    Agora::Node                 vNodeInfo;
    std::string                 vBroadcastAddress;
    uint16_t                    vBroadcastPort;
};
};