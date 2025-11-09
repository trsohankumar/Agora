#include "Configuration.h"

YAML::Node Configuration::config;

Configuration::Configuration(std::string file){
    config = YAML::LoadFile(file);
};


std::string Configuration::getValue(std::string propertyName){
    return config[propertyName].as<std::string>();
}