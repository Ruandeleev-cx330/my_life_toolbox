"""
本机 IP 查询工具 —— 支持 IPv4 + IPv6
用法：
    from utils.ip_tool import (
        get_internal_ipv4, get_external_ipv4,
        get_internal_ipv6, get_external_ipv6,
    )
"""

import socket

import requests


# ══════════════════════════════════════════════════════════════════
# IPv4
# ══════════════════════════════════════════════════════════════════

def get_internal_ipv4() -> str:
    """获取本机内网 IPv4 地址（UDP 连接法，避免返回 127.0.0.1）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def get_external_ipv4(timeout: float = 3.0) -> str:
    """
    获取本机公网 IPv4 地址。
    依次尝试多个服务（兼容国内网络环境）。
    """
    services = [
        ("https://api.ipify.org", lambda r: r.text.strip()),
        ("https://httpbin.org/ip", lambda r: r.json()["origin"].split(",")[0].strip()),
        ("https://ipapi.co/ip/", lambda r: r.text.strip()),
        ("https://ifconfig.me/ip", lambda r: r.text.strip()),
    ]
    for url, parser in services:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            ip = parser(resp)
            if ip and "." in ip:  # 确保是 IPv4 格式
                return ip
        except Exception:
            continue
    return "获取失败"


# ══════════════════════════════════════════════════════════════════
# IPv6
# ══════════════════════════════════════════════════════════════════

def get_internal_ipv6() -> str:
    """
    获取本机内网 IPv6 地址。
    通过连接 Google DNS IPv6 地址来获取本机首选 IPv6。
    """
    if not socket.has_ipv6:
        return "IPv6 不可用"

    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    try:
        # Google Public DNS IPv6
        s.connect(("2001:4860:4860::8888", 53))
        addr = s.getsockname()[0]
        # 去掉 %scope_id 后缀（Windows 上可能附带）
        if "%" in addr:
            addr = addr.split("%")[0]
        return addr
    except OSError:
        # 降级：尝试遍历网卡获取非链路本地地址
        return _find_ipv6_address()
    finally:
        s.close()


def _find_ipv6_address() -> str:
    """遍历本机网卡，返回第一个全局单播 IPv6 地址"""
    try:
        from socket import getaddrinfo, AF_INET6, SOCK_STREAM
        hostname = socket.gethostname()
        for info in getaddrinfo(hostname, None, AF_INET6, SOCK_STREAM):
            addr = info[4][0]
            if "%" in addr:
                addr = addr.split("%")[0]
            # 排除环回地址
            if addr != "::1" and not addr.startswith("fe80:"):
                return addr
    except Exception:
        pass
    return "::1"


def get_external_ipv6(timeout: float = 3.0) -> str:
    """
    获取本机公网 IPv6 地址。
    依次尝试多个 IPv6 专用服务。
    """
    if not socket.has_ipv6:
        return "IPv6 不可用"

    services = [
        ("https://api6.ipify.org", lambda r: r.text.strip()),
        ("https://ipv6.icanhazip.com", lambda r: r.text.strip()),
        ("https://ifconfig.co", lambda r: r.text.strip()),
        ("https://ipv6.ip.sb", lambda r: r.text.strip()),
    ]
    for url, parser in services:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            ip = parser(resp)
            if ip and ":" in ip:  # 确保是 IPv6 格式
                return ip
        except Exception:
            continue
    return "获取失败"


# ══════════════════════════════════════════════════════════════════
# 兼容旧 API
# ══════════════════════════════════════════════════════════════════

def get_internal_ip() -> str:
    """兼容旧接口，返回 IPv4 内网地址"""
    return get_internal_ipv4()


def get_external_ip(timeout: float = 3.0) -> str:
    """兼容旧接口，返回 IPv4 公网地址"""
    return get_external_ipv4(timeout=timeout)


# ══════════════════════════════════════════════════════════════════
# 自测块
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"内网 IPv4 : {get_internal_ipv4()}")
    print(f"公网 IPv4 : {get_external_ipv4()}")
    print(f"内网 IPv6 : {get_internal_ipv6()}")
    print(f"公网 IPv6 : {get_external_ipv6()}")
