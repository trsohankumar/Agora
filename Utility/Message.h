
#pragma once

#include <uuid.h>
#include <nlohmann/json.hpp>

namespace Agora
{
    namespace Message
    {
        struct Discovery
        {
            uuids::uuid  uEntityId;
            std::string  uIpAddress;
            uint16_t     uPort;

            Discovery() = default;
            Discovery(uuids::uuid pEntityId, std::string pIpAddress, uint16_t pPort);

            nlohmann::json toJson() const;
            void fromJson(const nlohmann::json& pJsonDiscoveryMessage);
        };
    }
}