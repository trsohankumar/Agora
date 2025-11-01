//
// Created by Sohankumar Rajeeshkumar on 24.10.25.
//

#ifndef DS1_PROJECT_DISCOVERY_H
#define DS1_PROJECT_DISCOVERY_H
#include <string>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <thread>

namespace Agora{
class Discovery {
public:
            Discovery(std::string pIpAddress, const int pPort);
    void    Broadcast() const;
    void    Listen() const;
private:
    std::string         vIpAddress;
    uint16_t            vPort;
    static std::string  sBroadcastAddress;
    static int          sBroadcastPort;
};
};


#endif //DS1_PROJECT_DISCOVERY_H