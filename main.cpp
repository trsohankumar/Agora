#include <iostream>
#include "spdlog/spdlog.h"
#include "Discovery/Discovery.h"
#include "Server/Server.h"
#include "Utility/Configuration.h"

int main() {
    static Configuration config = Configuration("../properties.yaml");
    std::unique_ptr<Agora::Server> server = std::make_unique<Agora::Server>(config);

    server->Listen();
    return 0;
}
