"""
天气获取工具 —— 调用 wttr.in 获取当前天气。
用法：
    from utils.weather import fetch_weather
    weather_str = fetch_weather()
"""

import requests


def fetch_weather(city: str = "Beijing", timeout: float = 3.0) -> str:
    """
    从 wttr.in 获取当前天气摘要。

    Args:
        city: 城市名（英文），默认 Beijing
        timeout: 请求超时秒数，默认 3 秒

    Returns:
        天气字符串，如 "☀️ +25°C"；超时或异常时返回 "天气获取中"
    """
    url = f"https://wttr.in/{city}?format=%C+%t"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text.strip()
    except Exception:
        return "天气获取中"


# ── 自测块 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    result = fetch_weather()
    print(f"当前天气: {result}")
