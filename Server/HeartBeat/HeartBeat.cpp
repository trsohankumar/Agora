//
// Created by Srindhi Krishna on 29.11.25.
//
#include "HeartBeat.h"


Agora::HeartBeat::HeartBeat(){
}


bool Agora::HeartBeat::receiveHeartBeat(std::chrono::milliseconds timeout){
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Failed to create socket for listening: {}", std::strerror(errno));
        return false;
    }

    constexpr int reusePortEnable = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEPORT, &reusePortEnable, sizeof(reusePortEnable));
    struct timeval tv;
    tv.tv_sec = std::chrono::duration_cast<std::chrono::seconds>(timeout).count();
    tv.tv_usec = std::chrono::duration_cast<std::chrono::microseconds>(
    timeout - std::chrono::duration_cast<std::chrono::seconds>(timeout)).count();
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    uint16_t port = 5001;
    sockaddr_in address;
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(port);

    if (bind(sock, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        spdlog::error("bind() failed on port {}: {}", port, std::strerror(errno));
        close(sock);
        return false;
    }

    spdlog::info("Listening for UDP on port {}", port);

    std::string buf(8192, '\0');

    sockaddr_in senderAddr{};
    socklen_t senderLen = sizeof(senderAddr);

    while (true) {
        const ssize_t payloadSize = ::recvfrom(sock, buf.data(), buf.size() - 1, 0,
            reinterpret_cast<sockaddr*>(&senderAddr), &senderLen);

        if (payloadSize < 0) {
            if(errno == EAGAIN || errno == EWOULDBLOCK) return false;
            if (errno == EINTR) continue;
            spdlog::warn("recvfrom() failed: {}", std::strerror(errno));
            continue;
        }

        buf[payloadSize] = '\0';
    }

    close(sock);
    return false;
}
