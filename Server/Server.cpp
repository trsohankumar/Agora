//
// Created by Sohankumar Rajeeshkumar on 01.11.25.
//

#include "Server.h"

#include <iostream>

Agora::Server::Server() {

    std::cout << "Server created" << std::endl;
    vIpAddress = "127.0.0.1";
    std::string publicRoutableIp = "8.8.8.8";

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Error creating socket");
        return;
    }

    sockaddr_in send_addr {};
    send_addr.sin_family = AF_INET;
    send_addr.sin_port = 1234; // the os can now assign any available port

    inet_pton(AF_INET, publicRoutableIp.c_str(), &send_addr.sin_addr);

    if (connect(sock, reinterpret_cast<sockaddr *>(&send_addr), sizeof(send_addr) ) < 0) {
        spdlog::error("Error connecting to 8.8.8.8");
        close(sock);
        return;
    }

    sockaddr_in serverAddrSock {};
    socklen_t serverAddrSockLen = sizeof(serverAddrSock);
    if (getsockname(sock, reinterpret_cast<sockaddr *>(&serverAddrSock), &serverAddrSockLen) < 0) {
        spdlog::error("Error getting local ip address socket");
        close(sock);
        return;
    }

    // now get local ip and random port on which server can run
    char ip_buf[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &serverAddrSock.sin_addr, ip_buf, sizeof(ip_buf));

    // retrieve port and Ip of the created socket
    vIpAddress = ip_buf;
    vPort = ntohs(serverAddrSock.sin_port);


    vDiscovery = std::make_unique<Agora::Discovery>(vIpAddress, vPort);

    // Start Broadcast
    StartBroadCast();

    // list to BroadCast
    ListenBroadCast();
}

void Agora::Server::StartBroadCast() {

    // setup thread for broadcasting
    std::thread(&Agora::Discovery::Broadcast, vDiscovery.get()).detach();
}

void Agora::Server::ListenBroadCast() {
   std::thread(&Agora::Discovery::Listen, vDiscovery.get()).detach();
}

void Agora::Server::Listen() {

    spdlog::info("Server with ip: {} Listening on Port: {}", vIpAddress, vPort);
    while (true) {
    }
}
