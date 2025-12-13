//
// Created by Srindhi Krishna on 29.11.25.
//

#pragma once
#include <chrono>
#include <arpa/inet.h>
#include <spdlog/spdlog.h>

namespace Agora{
    class HeartBeat{
    public:
        HeartBeat();

        bool receiveHeartBeat(std::chrono::milliseconds timeout);
        void sendHeartBeat();
    
    private:
        // A listener that awaits HeartBeat from leader
        // random time out for follower
        // Receive HeartBeat
        

        // Send HeartBeat
        
    };
};
