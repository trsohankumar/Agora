// Net/Message.h
#pragma once
#include <string>
#include <cstdint>
#include <nlohmann/json.hpp>

namespace Agora {

struct NodeInfo {
    std::string   nodeId;       // unique id for this server instance
    std::string   ip;           // your advertised IP
    int           port{0};      // your service port (if any)
    std::string   status;       // e.g., "online"
    std::uint64_t timestampMs{0}; // epoch ms
};

inline void to_json(nlohmann::json& j, const NodeInfo& n) {
    j = nlohmann::json{
        {"nodeId", n.nodeId},
        {"ip", n.ip},
        {"port", n.port},
        {"status", n.status},
        {"timestampMs", n.timestampMs}
    };
}

inline void from_json(const nlohmann::json& j, NodeInfo& n) {
    j.at("nodeId").get_to(n.nodeId);
    j.at("ip").get_to(n.ip);
    j.at("port").get_to(n.port);
    j.at("status").get_to(n.status);
    j.at("timestampMs").get_to(n.timestampMs);
}

} // namespace Agora