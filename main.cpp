#include <iostream>
#include "spdlog/spdlog.h"
#include "Discovery/Discovery.h"

int main(int argc, char *argv[]) {

    if (argc != 3) {
        spdlog::info("Usage: ./server <ip-address> <port>");
        return 1;
    }

    std::string ip_address = argv[1];
    std::string port = argv[2];

    spdlog::info("Server Listening on: ip-address {} : Port  {} ", ip_address , port);

    Agora::Discovery discovery{ip_address, std::stoi(port)};

    // Start listener in a separate thread
    std::thread listenThread(&Agora::Discovery::Listen, &discovery);
    listenThread.detach();

    // Start broadcasting
    discovery.Broadcast();
    return 0;
}