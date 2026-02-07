import socket
import struct

from loguru import logger


def get_ip_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('1.1.1.1', 1))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception as e:
        logger.error("Cannot resolve ip address: {}", e)


def get_broadcast_address():
    try:
        local_ip = get_ip_address()

        subnet_mask = '255.255.255.0'

        ip_binary = struct.unpack('!L', socket.inet_aton(local_ip))[0]
        mask_binary = struct.unpack('!L', socket.inet_aton(subnet_mask))[0]

        broadcast_binary = ip_binary | ~mask_binary
        broadcast_address = socket.inet_ntoa(struct.pack('!L', broadcast_binary & 0xFFFFFFFF))
        return broadcast_address
    except Exception as e:
        logger.error("Cannot resolve broadcast address: {}", e)
