"""
系统原生通知工具
用法：
    from utils.notifier import send_notification
    send_notification("标题", "消息内容")

策略（降级链）：
  1. plyer.notification（Windows/macOS/Linux 原生通知）
  2. ctypes MessageBox（Windows 弹窗）
  3. print 到控制台（最后兜底）
"""


def send_notification(title: str, message: str, timeout: int = 10):
    """
    发送系统原生通知。

    Args:
        title:   通知标题
        message: 通知正文
        timeout: 通知显示秒数（仅 plyer 路径生效）
    """
    # ── 策略 1：plyer（跨平台原生通知）────────────────
    try:
        from plyer import notification

        notification.notify(title=title, message=message, timeout=timeout)
        return
    except Exception:
        pass

    # ── 策略 2：Windows MessageBox ───────────────────
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            title,
            0x40,  # MB_ICONINFORMATION
        )
        return
    except Exception:
        pass

    # ── 策略 3：控制台输出 ──────────────────────────
    print(f"\n{'='*50}")
    print(f"[NOTIFY] [{title}]")
    print(f"   {message}")
    print(f"{'='*50}\n")


# ── 自测块 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    send_notification("My Life Toolbox", "这是一条测试通知 ✅")
    print("通知已发送(请检查桌面右下角或弹窗)")
