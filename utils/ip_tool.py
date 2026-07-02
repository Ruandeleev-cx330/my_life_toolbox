"""
本机 IP 查询工具
用法：
    from utils.ip_tool import get_internal_ip, get_external_ip
"""

import socket

import requests


def get_internal_ip() -> str:
    """获取本机内网 IP（UDP 连接法，避免返回 127.0.0.1）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def get_external_ip(timeout: float = 3.0) -> str:
    """
    获取本机公网 IP。
    依次尝试多个服务（兼容国内网络环境），全部失败时返回"获取失败"。
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
            if ip:
                return ip
        except Exception:
            continue
    return "获取失败"


# ── 自测块 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"内网 IP : {get_internal_ip()}")
    print(f"公网 IP : {get_external_ip()}")
