//
// Created by Sohankumar Rajeeshkumar on 01.11.25.
//

#ifndef AGORA_SERVER_H
#define AGORA_SERVER_H
#include <string>
#include <arpa/inet.h>
#include <spdlog/spdlog.h>

#include "../Discovery/Discovery.h"

namespace Agora {
class Server {

public:
         Server();
    void Listen();
private:

    void StartBroadCast();
    void ListenBroadCast();

    std::string vIpAddress;
    uint16_t    vPort;
    std::string vServerIdentifier;
    std::unique_ptr<Agora::Discovery> vDiscovery;
};
};


#endif //AGORA_SERVER_H