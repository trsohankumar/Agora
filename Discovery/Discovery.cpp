//
// Created by Sohankumar Rajeeshkumar on 24.10.25.
//

#include "Discovery.h"

#include <ostream>
#include <utility>

std::string Discovery::sBroadcastAddress = "192.168.1.255";
int Discovery::sBroadcastPort = 5000;

Discovery::Discovery(std::string pIpAddress, const int pPort)
    : vIpAddress(std::move(pIpAddress)), vPort(pPort){
}

void Discovery::Broadcast() const{

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        std::println("Error creating socket");
        return;
    }

    constexpr int broadcastEnable = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcastEnable, sizeof(broadcastEnable));

    sockaddr_in broadcaster_addr {};
    broadcaster_addr.sin_family = AF_INET;
    broadcaster_addr.sin_addr.s_addr = inet_addr(sBroadcastAddress.c_str());
    broadcaster_addr.sin_port = htons(sBroadcastPort);

    std::string message = "Hello from server" + vIpAddress;

    while (true) {
        sendto(sock, message.c_str(), message.size(), 0,
               (sockaddr*)&sBroadcastAddress, sizeof(sBroadcastAddress));

        std::this_thread::sleep_for(std::chrono::seconds(5));
    }
}

void Discovery::Listen() const {

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        std::println("Error creating Listener socket");
        return;
    }

    constexpr int reusePortEnable = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEPORT, &reusePortEnable, sizeof(reusePortEnable));

    sockaddr_in receiver_addr {};
    receiver_addr.sin_family = AF_INET;
    receiver_addr.sin_addr.s_addr = INADDR_ANY;
    receiver_addr.sin_port = htons(sBroadcastPort);

    int res = bind(sock, reinterpret_cast<struct sockaddr *>(&receiver_addr), sizeof(receiver_addr));

    if (res < 0) {
        std::println("Error binding socket on server with ip: {}", vIpAddress);
    }

    char buffer[1024];
    sockaddr_in senderAddr{};
    socklen_t senderLen = sizeof(senderAddr);

    while (true) {
        int len = recvfrom(sock, buffer, 1024 - 1, 0,
                           (sockaddr*)&senderAddr, &senderLen);
        if (len > 0) {
            buffer[len] = '\0';
            std::string senderIp = inet_ntoa(senderAddr.sin_addr);
            if (senderIp != vIpAddress) { // ignore own broadcast
                std::println("Node at {}", senderIp);
            }
        }
    }
}


