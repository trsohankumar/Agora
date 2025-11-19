#include "Node.h"

Agora::Node::Node ()
{
    
    std::string publicRoutableIp = "8.8.8.8";

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        spdlog::error("Error creating socket to retrieve Ip address");
        return;
    }

    sockaddr_in send_addr {};
    send_addr.sin_family = AF_INET;
    send_addr.sin_port = 1234; 

    inet_pton(AF_INET, publicRoutableIp.c_str(), &send_addr.sin_addr);

    if (connect(sock, reinterpret_cast<sockaddr *>(&send_addr), sizeof(send_addr) ) < 0) {
        spdlog::error("Error connecting to 8.8.8.8 {} (errno: {})", strerror(errno), errno);
        close(sock);
        return;
    }

    sockaddr_in nodeAddrSock {};
    socklen_t nodeAddrSockLen = sizeof(nodeAddrSock);
    if (getsockname(sock, reinterpret_cast<sockaddr *>(&nodeAddrSock), &nodeAddrSockLen) < 0) {
        spdlog::error("Error getting local ip address socket");
        close(sock);
        return;
    }

    // now get local ip and random port on which server can run
    char ip_buf[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &nodeAddrSock.sin_addr, ip_buf, sizeof(ip_buf));

    vIpAddress = ip_buf;
    vPort = ntohs(nodeAddrSock.sin_port);
    vNodeIdentifier = generateRandomUuid();

    if (vIpAddress.empty() || vPort == 0) {
        spdlog::warn("Retrieved invalid IP or port");
    }

    close(sock);
}

Agora::Node::Node (uuids::uuid pNodeIdentifier,std::string pIpAddress, uint16_t pPort )
    : vNodeIdentifier(pNodeIdentifier), vIpAddress(pIpAddress), vPort(pPort) {

}

uuids::uuid Agora::Node::getNodeIdentifier() const
{
    return vNodeIdentifier;
}                         

std::string Agora::Node::getNodeIpAddress() const                                                         
{
    return vIpAddress;
}

uint16_t    Agora::Node::getNodePort() const                                                        
{
    return vPort;
}