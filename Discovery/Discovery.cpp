//
// Created by Sohankumar Rajeeshkumar on 24.10.25.
//

#include "Discovery.h"

#include <chrono>
#include <cstring>
#include <string>
#include <thread>
#include <unistd.h>
#include <cerrno>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>

#include <nlohmann/json.hpp>
#include "Net/Message.h"

using nlohmann::json;
#include <ostream>
#include <utility>
#include <spdlog/spdlog.h>

std::string Agora::Discovery::sBroadcastAddress = "192.168.0.255";
int Agora::Discovery::sBroadcastPort = 5000;

Agora::Discovery::Discovery(std::string pIpAddress, const int pPort)
    : vIpAddress(std::move(pIpAddress)), vPort(pPort){
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
    broadcastAddress.sin_addr.s_addr = ::inet_addr(sBroadcastAddress.c_str()); 
    broadcastAddress.sin_port = htons(static_cast<uint16_t>(sBroadcastPort)); // changed to support macOS later lets see what to do with it i faced an error so changed it

    // Build the JSON object for broadcast
    Agora::NodeInfo info;
    info.nodeId = "agora-" + std::to_string(::getpid()); // simple unique id
    info.ip     = vIpAddress;                             // advertise what you already had
    info.port   = vPort;
    info.status = "online";

    while (true) {
        // for updating timestamp each time we send
        info.timestampMs = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count()
        );

        json j = info;
        const std::string payload = j.dump();

        spdlog::debug("Broadcasting {} bytes to {}:{}",
                      payload.size(), sBroadcastAddress, sBroadcastPort);

        const ssize_t sent = ::sendto(sock, payload.data(), payload.size(), 0,
                                      reinterpret_cast<sockaddr*>(&broadcastAddress),
                                      sizeof(broadcastAddress));
        if (sent < 0) {
            spdlog::warn("Broadcast sendto failed: {}", std::strerror(errno));
        }

        std::this_thread::sleep_for(std::chrono::seconds(5));
    }

    // (unreachable, but fine if you later add a stop condition)
    ::close(sock);
}

void Agora::Discovery::Listen() const {
    spdlog::info("Listen started");

    int sock = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Failed to create socket for listening: {}", std::strerror(errno));
        return;
    }
    // the 2 instance is chatgpt works fine most of it is but i didnt understand so it is what it is
    // Allow multiple listeners on the same UDP port
    int reuse = 1;
    if (::setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) < 0) {
        spdlog::warn("setsockopt(SO_REUSEADDR) failed: {}", std::strerror(errno));
    }
#ifdef SO_REUSEPORT
    if (::setsockopt(sock, SOL_SOCKET, SO_REUSEPORT, &reuse, sizeof(reuse)) < 0) {
        spdlog::warn("setsockopt(SO_REUSEPORT) failed: {}", std::strerror(errno));
    }
#endif

    sockaddr_in receiverAddr{};
    receiverAddr.sin_family      = AF_INET;
    receiverAddr.sin_addr.s_addr = htonl(INADDR_ANY);
    receiverAddr.sin_port        = htons(static_cast<uint16_t>(sBroadcastPort));

    if (::bind(sock, reinterpret_cast<sockaddr*>(&receiverAddr), sizeof(receiverAddr)) < 0) {
        spdlog::error("bind() failed on port {}: {}", sBroadcastPort, std::strerror(errno));
        ::close(sock);
        return;
    }

    spdlog::info("Listening for UDP on port {}", sBroadcastPort);

    std::string buf(8192, '\0');
    sockaddr_in senderAddr{};
    socklen_t senderLen = sizeof(senderAddr);

    while (true) {
        const ssize_t n = ::recvfrom(sock, buf.data(), buf.size() - 1, 0,
                                     reinterpret_cast<sockaddr*>(&senderAddr), &senderLen);
        if (n < 0) {
            if (errno == EINTR) continue;
            spdlog::warn("recvfrom() failed: {}", std::strerror(errno));
            continue;
        }
        buf[n] = '\0';

        try {
            nlohmann::json j = nlohmann::json::parse(buf.c_str(), buf.c_str() + n);
            Agora::NodeInfo other{};
            from_json(j, other);

            /
            const std::string selfId = "agora-" + std::to_string(::getpid());
            if (other.nodeId == selfId) continue;

            char srcIp[INET_ADDRSTRLEN]{};
            ::inet_ntop(AF_INET, &senderAddr.sin_addr, srcIp, sizeof(srcIp));

            spdlog::info("Discovery: from {}:{}  id={} ip={} port={} status={} t={}",
                         srcIp, ntohs(senderAddr.sin_port),
                         other.nodeId, other.ip, other.port, other.status, other.timestampMs);
        } catch (const std::exception& e) {
            spdlog::warn("Failed to parse incoming JSON: {}", e.what());
        }
    }

    ::close(sock); 
}

