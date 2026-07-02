"""
My Life Toolbox —— 主入口（悬浮窗优先启动）

启动流程：
  1. 初始化数据库 + 导入页面模块（注册 @ui.page 路由）
  2. 启动定时任务（APScheduler）
  3. 启动 NiceGUI Web 服务器（后台线程，不自动打开浏览器）
  4. 启动系统托盘图标（后台线程）
  5. 显示桌面悬浮窗（tkinter 主循环，前台阻塞）
  6. 关闭悬浮窗 → 退出全部组件 → 进程结束

用法：python app.py
"""

import atexit
import threading
import webbrowser
from pathlib import Path

# ── 提前导入 nicegui（页面模块的 @ui.page 装饰器依赖它）──
from nicegui import ui

# ── 初始化数据库 ────────────────────────────────────────────────
from core.database import init_db

init_db()

# ── 导入页面模块 —— 在模块级执行以注册所有 @ui.page 路由 ──────
#     必须在 ui.run() 之前完成，因此在模块顶层导入
import modules.calendar_feed  # noqa: E402  /calendar
import modules.dashboard  # noqa: E402  /
import modules.diary  # noqa: E402  /diary
import modules.finance  # noqa: E402  /finance
import modules.gadgets  # noqa: E402  /gadgets
import modules.rnote_manager  # noqa: E402  /rnote
import modules.settings  # noqa: E402  /settings

from core.scheduler import start_scheduler, stop_scheduler  # noqa: E402

# ── 常量 ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
NICE_HOST = "127.0.0.1"
NICE_PORT = 18520
NICE_URL = f"http://{NICE_HOST}:{NICE_PORT}"

# 保存原始 webbrowser.open —— _run_nicegui_server 会 monkey-patch 它，
# 但悬浮窗的"打开面板"功能需要调用真正的浏览器打开函数。
_real_browser_open = webbrowser.open

# 同步原语：标记 NiceGUI 服务器是否已启动完成
_server_ready = threading.Event()


# ══════════════════════════════════════════════════════════════════
# NiceGUI 服务器（后台线程）
# ══════════════════════════════════════════════════════════════════

def _run_nicegui_server():
    """
    在后台线程中启动 NiceGUI Web 服务器。
    阻止 NiceGUI 自动打开浏览器（通过 monkey-patch webbrowser.open），
    让悬浮窗的「打开完整面板」按钮来控制浏览器打开时机。
    """
    # 保存原始函数，替换为空操作
    _real_open = webbrowser.open
    webbrowser.open = lambda *args, **kwargs: None

    try:
        _server_ready.set()
        ui.run(
            title="My Life Toolbox",
            host=NICE_HOST,
            port=NICE_PORT,
            native=False,   # 使用浏览器而非原生窗口
            show=False,     # 不打印启动横幅
            reload=False,   # 生产模式，禁用热重载
        )
    finally:
        webbrowser.open = _real_open  # 恢复（unreachable 但安全）


# ══════════════════════════════════════════════════════════════════
# 系统托盘（后台线程）
# ══════════════════════════════════════════════════════════════════

def _start_tray(floating_window):
    """
    在后台线程中创建系统托盘图标。
    提供：显示悬浮窗 / 打开 Web 面板 / 退出 菜单项。

    Args:
        floating_window: FloatingWindow 实例，用于 show/hide 操作
    """
    import pystray
    from PIL import Image

    # 托盘图标
    icon_path = BASE_DIR / "static" / "icon.ico"
    if icon_path.exists():
        image = Image.open(icon_path)
    else:
        image = Image.new("RGB", (64, 64), color="#3b82f6")

    def _do_show(icon, item):
        """恢复显示悬浮窗"""
        try:
            fw = floating_window
            if fw.root.winfo_exists():
                fw.root.deiconify()
                fw.root.lift()
                fw.root.attributes("-topmost", True)
                # 短暂置顶后恢复原状态
                fw.root.after(200, lambda: fw.root.attributes(
                    "-topmost", fw.config.get("always_on_top", True)
                ))
        except Exception:
            pass

    def _do_open_web(icon, item):
        """打开 Web 面板"""
        _server_ready.wait(timeout=5.0)
        _real_browser_open(NICE_URL)

    def _do_quit(icon, item):
        """退出整个程序"""
        icon.stop()
        stop_scheduler()
        try:
            floating_window.destroy()
        except Exception:
            pass

    menu = pystray.Menu(
        pystray.MenuItem("📌 显示悬浮窗", _do_show, default=True),
        pystray.MenuItem("🖥 打开 Web 面板", _do_open_web),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ 退出", _do_quit),
    )

    icon = pystray.Icon("my_life_toolbox", image, "My Life Toolbox", menu)
    icon.run()


# ══════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════

def main():
    """应用主入口：悬浮窗优先，Web 按需打开"""
    from widget.floating_window import FloatingWindow, load_config

    config = load_config()

    # ── 启动定时任务 ──────────────────────────────────────────
    start_scheduler()

    # ── 定义退出回调（在 FloatingWindow 实例化后可用）─────────
    app_ref = {"instance": None}  # 用 dict 解决闭包引用问题

    def _on_quit():
        """悬浮窗关闭 → 停止所有组件"""
        stop_scheduler()
        if app_ref["instance"]:
            try:
                app_ref["instance"].destroy()
            except Exception:
                pass

    def _on_open_web():
        """打开 Web 面板（等待服务器就绪后打开浏览器）"""
        _server_ready.wait(timeout=5.0)
        _real_browser_open(NICE_URL)

    # ── 创建悬浮窗（主线程，稍后进入其 mainloop）──────────────
    app = FloatingWindow(
        config=config,
        on_open_web=_on_open_web,
        on_quit=_on_quit,
    )
    app_ref["instance"] = app

    # ── 启动 NiceGUI 服务器（后台线程）────────────────────────
    nice_thread = threading.Thread(
        target=_run_nicegui_server,
        daemon=True,
        name="nicegui-server",
    )
    nice_thread.start()

    # ── 启动系统托盘（后台线程）───────────────────────────────
    tray_thread = threading.Thread(
        target=_start_tray,
        args=(app,),
        daemon=True,
        name="system-tray",
    )
    tray_thread.start()

    # ── 自动打开 Web（若配置启用）─────────────────────────────
    if config.get("auto_open_web", False):
        # 延迟 2 秒等服务器完全就绪
        timer = threading.Timer(2.0, _on_open_web)
        timer.daemon = True
        timer.start()

    # ── 进入 tkinter 主循环（阻塞）────────────────────────────
    app.run()

    # ── 清理（tkinter 主循环退出后执行）───────────────────────
    stop_scheduler()


if __name__ == "__main__":
    atexit.register(stop_scheduler)
    main()
