cmake_minimum_required(VERSION 4.0)
project(agora)

set(CMAKE_CXX_STANDARD 23)

if(NOT CMAKE_PREFIX_PATH)
    set(CMAKE_PREFIX_PATH "/opt/homebrew" CACHE PATH "Search path for packages")
endif()

find_package(nlohmann_json CONFIG REQUIRED)
find_package(spdlog CONFIG REQUIRED)

add_executable(server main.cpp
        Discovery/Discovery.cpp
        Discovery/Discovery.h
        Server/Server.cpp
        Server/Server.h)

target_link_libraries(server PRIVATE
        nlohmann_json::nlohmann_json
        spdlog::spdlog_header_only
        fmt::fmt-header-only
)