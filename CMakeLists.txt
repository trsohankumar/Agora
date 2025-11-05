cmake_minimum_required(VERSION 4.0)
project(agora)

set(CMAKE_CXX_STANDARD 23)

include(FetchContent)

if(NOT CMAKE_PREFIX_PATH)
    set(CMAKE_PREFIX_PATH "/opt/homebrew" CACHE PATH "Search path for packages")
endif()

FetchContent_Declare(
        yaml-cpp
        GIT_REPOSITORY https://github.com/jbeder/yaml-cpp.git
        GIT_TAG 0.8.0
)
FetchContent_MakeAvailable(yaml-cpp)


find_package(nlohmann_json CONFIG REQUIRED)
find_package(spdlog CONFIG REQUIRED)

add_executable(server main.cpp
        Utility/Configuration.cpp
        Utility/Configuration.h
        Discovery/Discovery.cpp
        Discovery/Discovery.h
        Server/Server.cpp
        Server/Server.h
        Net/Message.h)

target_include_directories(server PRIVATE ${CMAKE_SOURCE_DIR})

target_link_libraries(server PRIVATE
        nlohmann_json::nlohmann_json
        spdlog::spdlog_header_only
        fmt::fmt-header-only
        yaml-cpp::yaml-cpp
        ${CMAKE_SOURCE_DIR}
)