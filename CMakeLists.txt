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
        GIT_TAG master
)
FetchContent_MakeAvailable(yaml-cpp)

FetchContent_Declare(json URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz)
FetchContent_MakeAvailable(json)

FetchContent_Declare(
        spdlog
        GIT_REPOSITORY https://github.com/gabime/spdlog
        GIT_TAG v1.16.0
)
FetchContent_MakeAvailable(spdlog)

FetchContent_Declare(
    stduuid
    GIT_REPOSITORY https://github.com/mariusbancila/stduuid.git
    GIT_TAG        v1.2.3
)
FetchContent_MakeAvailable(stduuid)


add_executable(server main.cpp
        Utility/Configuration.cpp
        Utility/Configuration.h
        Utility/Message.h
        Utility/Message.cpp
        Utility/UuidGeneration.h
        Utility/UuidGeneration.cpp
        Discovery/Discovery.cpp
        Discovery/Discovery.h
        Server/Server.cpp
        Server/Server.h)

target_include_directories(server PRIVATE 
        ${CMAKE_SOURCE_DIR}
)

target_link_libraries(server PRIVATE
        nlohmann_json::nlohmann_json
        spdlog::spdlog_header_only
        yaml-cpp::yaml-cpp
        stduuid
)