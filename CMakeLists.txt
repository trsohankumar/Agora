cmake_minimum_required(VERSION 4.0)
project(DS1_Project)

set(CMAKE_CXX_STANDARD 23)

add_executable(server main.cpp
        Discovery/Discovery.cpp
        Discovery/Discovery.h)
