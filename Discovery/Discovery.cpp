//
// Created by Sohankumar Rajeeshkumar on 24.10.25.
//

#include "Discovery.h"

Agora::Discovery::Discovery(uuids::uuid pEntityId, std::string pIpAddress, const uint16_t pPort, std::string pBroadcastAddress, const uint16_t pBroadcastPort)
    :vDiscoveryMessage(std::move(pEntityId), std::move(pIpAddress), pPort), vBroadcastAddress(std::move(pBroadcastAddress)), vBroadcastPort(pBroadcastPort) {
}

void Agora::Discovery::Broadcast() const{
    spdlog::info("Broadcast started");

    int sock = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Failed to create socket for broadcasting: {}", std::strerror(errno));
        return;
    }

    constexpr int broadcastEnable = 1;
    if (::setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcastEnable, sizeof(broadcastEnable)) < 0) {
        spdlog::error("setsockopt(SO_BROADCAST) failed: {}", std::strerror(errno));
        ::close(sock);
        return;
    }

    sockaddr_in broadcastAddress{};
    broadcastAddress.sin_family      = AF_INET;
    broadcastAddress.sin_addr.s_addr = ::inet_addr(vBroadcastAddress.c_str()); 
    broadcastAddress.sin_port        = htons(vBroadcastPort);

    while (true) {
        
        nlohmann::json discoveryMessage = vDiscoveryMessage.toJson();
        const std::string payload = discoveryMessage.dump();

        spdlog::debug("Broadcasting {} bytes to {}:{}", payload.size(), vBroadcastAddress, vBroadcastPort);

        const ssize_t sent = ::sendto(sock, payload.data(), payload.size(), 0, reinterpret_cast<sockaddr*>(&broadcastAddress),
            sizeof(broadcastAddress));

        if (sent < 0) {
            spdlog::warn("Broadcast sendto failed: {}", std::strerror(errno));
        }

        std::this_thread::sleep_for(std::chrono::seconds(5));
    }

    ::close(sock);
}

void Agora::Discovery::Listen() const {
    spdlog::info("Listen started");

    int sock = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Failed to create socket for listening: {}", std::strerror(errno));
        return;
    }

    constexpr int reusePortEnable = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEPORT, &reusePortEnable, sizeof(reusePortEnable));

    sockaddr_in receiverAddr {};
    receiverAddr.sin_family = AF_INET;
    receiverAddr.sin_addr.s_addr = INADDR_ANY;
    receiverAddr.sin_port = htons(vBroadcastPort);

    if (::bind(sock, reinterpret_cast<sockaddr*>(&receiverAddr), sizeof(receiverAddr)) < 0) {
        spdlog::error("bind() failed on port {}: {}", vBroadcastPort, std::strerror(errno));
        ::close(sock);
        return;
    }

    spdlog::info("Listening for UDP on port {}", vBroadcastPort);

    std::string buf(8192, '\0');

    sockaddr_in senderAddr{};
    socklen_t senderLen = sizeof(senderAddr);

    while (true) {
        const ssize_t payloadSize = ::recvfrom(sock, buf.data(), buf.size() - 1, 0,
            reinterpret_cast<sockaddr*>(&senderAddr), &senderLen);

        if (payloadSize < 0) {
            if (errno == EINTR) continue;
            spdlog::warn("recvfrom() failed: {}", std::strerror(errno));
            continue;
        }

        buf[payloadSize] = '\0';

        try {
            nlohmann::json discoveredMessage = nlohmann::json::parse(buf.c_str(), buf.c_str() + payloadSize);
            Agora::Message::Discovery discoveredNode;
            discoveredNode.fromJson(discoveredMessage);

            if (discoveredNode.uEntityId == vDiscoveryMessage.uEntityId) continue;

            spdlog::info("Discovery: <Id: {}, Ip: {}, Port: {}> discovered <Id: {}, Ip: {}, Port: {}>",
                uuids::to_string(vDiscoveryMessage.uEntityId), vDiscoveryMessage.uIpAddress, vDiscoveryMessage.uPort,
                uuids::to_string(discoveredNode.uEntityId), discoveredNode.uIpAddress, discoveredNode.uPort);

        } catch (const std::exception& e) {
            spdlog::warn("Failed to parse incoming JSON: {}", e.what());
        }
    }

    ::close(sock); 
}

