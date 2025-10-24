#include <iostream>
#include "Discovery/Discovery.h"

int main(int argc, char *argv[]) {

    if (argc != 3) {
        std::println("Usage: ./server <ip-address> <port>");
    }

    std::string ip_address = argv[1];
    std::string port = argv[2];

    std::println("Server Listening on: ip-address {} : Port  {} ", ip_address , port);

    Discovery discovery{ip_address, std::stoi(port)};

    // Start listener in a separate thread
    std::thread listenThread(&Discovery::Listen, &discovery);
    listenThread.detach();

    // Start broadcasting
    discovery.Broadcast();
    return 0;
}