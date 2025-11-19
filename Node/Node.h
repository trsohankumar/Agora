#pragma once

#include <string>
#include <arpa/inet.h>
#include <spdlog/spdlog.h>
#include <uuid.h>

#include "../Utility/UuidGeneration.h"

namespace Agora
{
class Node
{

public:
                Node();
                Node(uuids::uuid pNodeIdentifier,std::string pIpAddress, uint16_t pPort);
    uuids::uuid getNodeIdentifier()                                                         const;
    std::string getNodeIpAddress()                                                          const;
    uint16_t    getNodePort()                                                               const;

private:
    uuids::uuid vNodeIdentifier;
    std::string vIpAddress;
    uint16_t    vPort;
};
}
