#include "Message.h"


Agora::Message::Discovery::Discovery(uuids::uuid pEntityId, std::string pIpAddress, uint16_t pPort)
    : uEntityId(pEntityId), uIpAddress(pIpAddress), uPort(pPort) {
}

nlohmann::json Agora::Message::Discovery::toJson() const
{
    nlohmann::json discoveryMessage = nlohmann::json{
        {"uuid", uuids::to_string(uEntityId)},
        {"ip", uIpAddress},
        {"port", uPort},
    };

    return discoveryMessage;
}

void Agora::Message::Discovery::fromJson(const nlohmann::json& pJsonDiscoveryMessage) {
    std::string tempEntityId;
    pJsonDiscoveryMessage.at("uuid").get_to(tempEntityId);
    uEntityId = uuids::uuid::from_string(tempEntityId).value();

    pJsonDiscoveryMessage.at("ip").get_to(uIpAddress);
    pJsonDiscoveryMessage.at("port").get_to(uPort);
}