#pragma once
#include <unordered_map>
#include <string>
#include <fstream>
#include "yaml-cpp/yaml.h"


class Configuration{
    static YAML::Node config;
public:
    Configuration(std::string file);

    std::string getValue(std::string propertyName);
};
