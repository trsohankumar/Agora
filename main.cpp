#include <iostream>
#include "spdlog/spdlog.h"
#include "Discovery/Discovery.h"
#include "Server/Server.h"

int main() {

    std::unique_ptr<Agora::Server> server = std::make_unique<Agora::Server>();

    server->Listen();
    return 0;
}
