//
// Created by Sohankumar Rajeeshkumar on 24.10.25.
//

#include "Discovery.h"

#include <ostream>
#include <utility>
#include <spdlog/spdlog.h>

Agora::Discovery::Discovery(std::string pIpAddress, const int pPort, std::string broadcastAddress)
    : vIpAddress(std::move(pIpAddress)), vPort(pPort), sBroadcastAddress(std::move(broadcastAddress)) {
}

void Agora::Discovery::Broadcast() const{
    spdlog::info("Broadcast started");

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Failed to create socket for broadcasting");
        return;
    }

    constexpr int broadcastEnable = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcastEnable, sizeof(broadcastEnable));

    sockaddr_in broadcastAddress {};
    broadcastAddress.sin_family = AF_INET;
    broadcastAddress.sin_addr.s_addr = inet_addr(sBroadcastAddress.c_str());
    broadcastAddress.sin_port = htons(vPort);

    std::string message = vIpAddress + " " + std::to_string(vPort);

    while (true) {
        spdlog::info("Sending message: {}", message);
        sendto(sock, message.c_str(), message.size(), 0,
               reinterpret_cast<sockaddr *>(&broadcastAddress), sizeof(broadcastAddress));

        std::this_thread::sleep_for(std::chrono::seconds(5));
    }
}

void Agora::Discovery::Listen() const {
    spdlog::info("Listen started");
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Failed to create socket for listening");
        return;
    }

    constexpr int reusePortEnable = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEPORT, &reusePortEnable, sizeof(reusePortEnable));

    sockaddr_in receiver_addr {};
    receiver_addr.sin_family = AF_INET;
    receiver_addr.sin_addr.s_addr = INADDR_ANY;
    receiver_addr.sin_port = htons(vPort);

    int res = bind(sock, reinterpret_cast<struct sockaddr *>(&receiver_addr), sizeof(receiver_addr));

    if (res < 0) {
        spdlog::error("Failed to bind socket for broadcast listening");
    }

    char buffer[1024];

    sockaddr_in senderAddr{};
    socklen_t senderLen = sizeof(senderAddr);

    while (true) {
        int len = recvfrom(sock, buffer, 1024 - 1, 0,
                           reinterpret_cast<sockaddr *>(&senderAddr), &senderLen);
        if (len > 0) {
            buffer[len] = '\0';
            std::string message(buffer, len);
            //if (message != vIpAddress) { // ignore own broadcast
             //   spdlog::info("Node at {} with message {}", message, message);
            //}

            spdlog::info("Node at {} with message {}", message, message);
        }
    }
}


