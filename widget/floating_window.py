"""
桌面悬浮窗 —— tkinter 原生无边框窗口
功能：天气 · 待办 · IP · 快捷记账 · 置顶切换 · 打开 Web 面板

架构：
  - 主线程 tkinter mainloop
  - 后台线程刷新数据（天气/IP/待办，每 30 秒）
  - 与 NiceGUI Web 共用同一 SQLite 数据库
"""

import ctypes
import json
import sys
import threading
from ctypes import wintypes
from datetime import date
from pathlib import Path
from tkinter import TclError, messagebox
from typing import Callable

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from core.database import SessionLocal, Todo, Transaction
from utils.ip_tool import (
    get_external_ipv4,
    get_external_ipv6,
    get_internal_ipv4,
    get_internal_ipv6,
)
from utils.weather import fetch_weather

# ── Win32 API 函数原型（一次性定义，避免每次调用时的类型转换错误）──
if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _user32.SetWindowLongW.restype = ctypes.c_long

# ── 路径常量 ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

# ── 配色方案（暗色主题）───────────────────────────────────────────
BG_DARK = "#2d2d2d"
BG_CARD = "#3a3a3a"
BG_HOVER = "#4a4a4a"
FG_PRIMARY = "#e0e0e0"
FG_SECONDARY = "#a0a0a0"
ACCENT_BLUE = "#3b82f6"
ACCENT_GREEN = "#22c55e"
ACCENT_RED = "#ef4444"
ACCENT_YELLOW = "#eab308"


# ═══════════════════════════════════════════════════════════════════
# 配置读写
# ═══════════════════════════════════════════════════════════════════

def load_config() -> dict:
    """从 config.json 读取配置，缺失时返回默认值"""
    defaults = {
        "always_on_top": True,
        "auto_open_web": False,
        "opacity": 0.88,
        "city": "Beijing",
    }
    try:
        if CONFIG_PATH.exists():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            defaults.update(raw)
    except (json.JSONDecodeError, OSError):
        pass
    return defaults


def save_config(config: dict):
    """保存配置到 config.json（原子写入：先写临时文件再替换）"""
    try:
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(CONFIG_PATH)
    except OSError:
        pass  # 静默失败，不影响悬浮窗运行


# ═══════════════════════════════════════════════════════════════════
# 悬浮窗主类
# ═══════════════════════════════════════════════════════════════════

class FloatingWindow:
    """
    桌面悬浮窗。

    Windows 平台通过 Win32 API 去除窗口边框（而非 overrideredirect），
    因为 overrideredirect 窗口无法使用 WS_EX_TOPMOST 置顶。

    Args:
        config: 配置字典（load_config() 返回值）
        on_open_web: 打开 Web 面板的回调
        on_quit: 退出整个程序的回调
    """

    # Win32 常量
    _GWL_STYLE = -16
    _GWL_EXSTYLE = -20
    _WS_CAPTION = 0x00C00000
    _WS_THICKFRAME = 0x00040000
    _WS_MINIMIZEBOX = 0x00020000
    _WS_MAXIMIZEBOX = 0x00010000
    _WS_SYSMENU = 0x00080000
    _WS_EX_TOOLWINDOW = 0x00000080
    _SWP_FRAMECHANGED = 0x0020
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _HWND_TOPMOST = wintypes.HWND(-1)
    _HWND_NOTOPMOST = wintypes.HWND(-2)

    def __init__(
        self,
        config: dict,
        on_open_web: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self.config = config
        self.on_open_web = on_open_web
        self.on_quit = on_quit

        # 展开状态
        self._todos_expanded = False
        self._ip_index = 0  # 0=内网, 1=外网
        self._todos_data: list[dict] = []
        self._weather_text = "天气获取中..."
        self._ipv4_local = "--"
        self._ipv6_local = "--"
        self._ipv4_public = "--"
        self._ipv6_public = "--"

        # ── 构建根窗口（不用 overrideredirect！）──────────────
        self.root = tk.Tk()
        self.root.title("My Life Toolbox")
        # 半透明（在去边框之前设，因为去边框后可能需要重新应用）
        self.root.attributes("-alpha", config.get("opacity", 0.88))
        self.root.configure(bg=BG_DARK)

        # 窗口初始位置（右下角，高度自适应内容）
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        ww, wh = 260, 280
        self.root.geometry(f"{ww}x{wh}+{sw - ww - 20}+{sh - wh - 80}")

        # ── 构建 UI ───────────────────────────────────────────
        self._build_ui()

        # ── 强制映射窗口，然后去除系统边框 ─────────────────────
        self.root.update()
        self._make_frameless()

        # ── 设置初始置顶（Win32 API，窗口已映射后生效）─────────
        self._win_set_topmost(config.get("always_on_top", True))
        self.root.update_idletasks()
        self._sync_pin_ui()

        # ── 拖拽支持 ──────────────────────────────────────────
        self._drag_x = 0
        self._drag_y = 0
        self._bind_drag()

        # ── 右键菜单 ──────────────────────────────────────────
        self._build_context_menu()

        # ── 关闭协议 ──────────────────────────────────────────
        self.root.protocol("WM_DELETE_WINDOW", self.on_quit)

        # ── 首次刷新 ──────────────────────────────────────────
        self._refresh_data()

        # ── 周期刷新（30 秒）──────────────────────────────────
        self._schedule_periodic_refresh()

    # ──────────────────────────────────────────────────────────────
    # Win32 去边框（替代 overrideredirect）
    # ──────────────────────────────────────────────────────────────

    def _make_frameless(self):
        """
        通过 Win32 API 移除窗口系统边框和标题栏，
        同时添加 WS_EX_TOOLWINDOW 隐藏任务栏图标。

        与 overrideredirect(True) 的关键区别：
          本方法保留 tkinter 对 -topmost 属性的管理能力。
        """
        if sys.platform != "win32":
            return  # 仅 Windows 需要此处理

        hwnd = self.root.winfo_id()

        REMOVE_STYLES = (
            self._WS_CAPTION
            | self._WS_THICKFRAME
            | self._WS_MINIMIZEBOX
            | self._WS_MAXIMIZEBOX
            | self._WS_SYSMENU
        )

        # 移除标题栏 + 边框样式
        style = _user32.GetWindowLongW(hwnd, self._GWL_STYLE)
        _user32.SetWindowLongW(hwnd, self._GWL_STYLE, style & ~REMOVE_STYLES)

        # 添加 TOOLWINDOW 样式——隐藏任务栏图标
        ex_style = _user32.GetWindowLongW(hwnd, self._GWL_EXSTYLE)
        _user32.SetWindowLongW(hwnd, self._GWL_EXSTYLE, ex_style | self._WS_EX_TOOLWINDOW)

        # 通知 Windows 窗口样式已变更
        _user32.SetWindowPos(
            hwnd, wintypes.HWND(0), 0, 0, 0, 0,
            self._SWP_FRAMECHANGED | self._SWP_NOMOVE
            | self._SWP_NOSIZE | self._SWP_NOZORDER,
        )

    # ──────────────────────────────────────────────────────────────
    # UI 构建
    # ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        """构建所有 UI 组件"""
        # 主容器
        main = tk.Frame(self.root, bg=BG_DARK, padx=10, pady=6)
        main.pack(fill="both", expand=True)

        # ── 标题栏（拖拽手柄）────────────────────────────────
        self._title_bar = tk.Frame(main, bg=BG_DARK)
        self._title_bar.pack(fill="x", pady=(0, 4))

        # 标题（可拖拽）
        self._title_label = tk.Label(
            self._title_bar,
            text="MLT",
            fg=FG_PRIMARY,
            bg=BG_DARK,
            font=("Segoe UI", 10, "bold"),
            cursor="fleur",
        )
        self._title_label.pack(side="left")

        # 右侧按钮容器
        btn_frame = tk.Frame(self._title_bar, bg=BG_DARK)
        btn_frame.pack(side="right")

        # 置顶图标 📌
        self._pin_btn = tk.Label(
            btn_frame,
            text="\N{PUSHPIN}" if self.config.get("always_on_top", True) else "\N{ROUND PUSHPIN}",
            fg=ACCENT_BLUE if self.config.get("always_on_top", True) else FG_SECONDARY,
            bg=BG_DARK,
            font=("Segoe UI", 11),
            cursor="hand2",
        )
        self._pin_btn.pack(side="right", padx=(4, 0))
        self._pin_btn.bind("<Button-1>", lambda e: self._toggle_pin())

        # 关闭按钮
        close_btn = tk.Label(
            btn_frame,
            text="✕",
            fg=FG_SECONDARY,
            bg=BG_DARK,
            font=("Segoe UI", 11),
            cursor="hand2",
        )
        close_btn.pack(side="right", padx=(4, 0))
        close_btn.bind("<Button-1>", lambda e: self.on_quit())

        # ── 分隔线 ────────────────────────────────────────────
        sep1 = tk.Frame(main, height=1, bg="#555")
        sep1.pack(fill="x", pady=(0, 6))

        # ── 天气卡片 ──────────────────────────────────────────
        self._weather_card = tk.Frame(main, bg=BG_CARD, padx=8, pady=6)
        self._weather_card.pack(fill="x", pady=(0, 6))
        tk.Label(
            self._weather_card,
            text="☀️",
            bg=BG_CARD,
            font=("Segoe UI", 18),
        ).pack(side="left", padx=(0, 6))
        self._weather_label = tk.Label(
            self._weather_card,
            text="天气获取中...",
            fg=FG_PRIMARY,
            bg=BG_CARD,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
        )
        self._weather_label.pack(side="left", fill="x", expand=True)

        # ── 待办卡片 ──────────────────────────────────────────
        self._todo_card = tk.Frame(main, bg=BG_CARD, padx=8, pady=6)
        self._todo_card.pack(fill="x", pady=(0, 6))

        # 头部（可点击展开/收起）
        self._todo_header = tk.Frame(self._todo_card, bg=BG_CARD, cursor="hand2")
        self._todo_header.pack(fill="x")
        self._todo_header.bind("<Button-1>", lambda e: self._toggle_todos())

        self._todo_icon = tk.Label(
            self._todo_header,
            text="📋",
            bg=BG_CARD,
            font=("Segoe UI", 12),
        )
        self._todo_icon.pack(side="left", padx=(0, 5))

        self._todo_count_label = tk.Label(
            self._todo_header,
            text="待办: --",
            fg=FG_PRIMARY,
            bg=BG_CARD,
            font=("Segoe UI", 10, "bold"),
        )
        self._todo_count_label.pack(side="left")

        self._todo_expand_icon = tk.Label(
            self._todo_header,
            text="▶",
            fg=FG_SECONDARY,
            bg=BG_CARD,
            font=("Segoe UI", 8),
        )
        self._todo_expand_icon.pack(side="right")

        # 展开列表容器（初始隐藏）
        self._todo_list_frame = tk.Frame(self._todo_card, bg=BG_CARD)

        # ── IP 卡片 ────────────────────────────────────────────
        self._ip_card = tk.Frame(main, bg=BG_CARD, padx=8, pady=6)
        self._ip_card.pack(fill="x", pady=(0, 6))

        def _on_ip_click(e):
            self._toggle_ip()

        self._ip_card.bind("<Button-1>", _on_ip_click)

        # 头部：图标 + 内外网标签 + 切换提示
        ip_header = tk.Frame(self._ip_card, bg=BG_CARD)
        ip_header.pack(fill="x")
        self._ip_icon = tk.Label(ip_header, text="\U0001F5A5", bg=BG_CARD, font=("Segoe UI", 11))
        self._ip_icon.pack(side="left", padx=(0, 4))
        self._ip_icon.bind("<Button-1>", _on_ip_click)
        self._ip_kind_label = tk.Label(ip_header, text="内网", fg=ACCENT_BLUE, bg=BG_CARD, font=("Segoe UI", 9, "bold"))
        self._ip_kind_label.pack(side="left")
        self._ip_kind_label.bind("<Button-1>", _on_ip_click)
        self._ip_switch_label = tk.Label(ip_header, text="\N{RIGHTWARDS ARROW} 外网", fg=FG_SECONDARY, bg=BG_CARD, font=("Segoe UI", 8))
        self._ip_switch_label.pack(side="right")
        self._ip_switch_label.bind("<Button-1>", _on_ip_click)

        # IPv4 行
        ipv4_frame = tk.Frame(self._ip_card, bg=BG_CARD)
        ipv4_frame.pack(fill="x", pady=(2, 0))
        self._ipv4_label = tk.Label(ipv4_frame, text="--", fg=FG_PRIMARY, bg=BG_CARD, font=("Consolas", 8), anchor="w", wraplength=195)
        self._ipv4_label.pack(side="left", fill="x", expand=True)
        self._ipv4_copy = tk.Label(ipv4_frame, text="cp", fg=FG_SECONDARY, bg=BG_CARD, font=("Segoe UI", 7), cursor="hand2")
        self._ipv4_copy.pack(side="right")
        self._ipv4_copy.bind("<Button-1>", lambda e: self._copy_ip(0))

        # IPv6 行
        ipv6_frame = tk.Frame(self._ip_card, bg=BG_CARD)
        ipv6_frame.pack(fill="x")
        self._ipv6_label = tk.Label(ipv6_frame, text="--", fg=FG_PRIMARY, bg=BG_CARD, font=("Consolas", 7), anchor="w", wraplength=195)
        self._ipv6_label.pack(side="left", fill="x", expand=True)
        self._ipv6_copy = tk.Label(ipv6_frame, text="cp", fg=FG_SECONDARY, bg=BG_CARD, font=("Segoe UI", 7), cursor="hand2")
        self._ipv6_copy.pack(side="right")
        self._ipv6_copy.bind("<Button-1>", lambda e: self._copy_ip(1))

        # ── 分隔线 ────────────────────────────────────────────
        sep2 = tk.Frame(main, height=1, bg="#555")
        sep2.pack(fill="x", pady=(2, 6))

        # ── 底部操作按钮 ──────────────────────────────────────
        bottom_frame = tk.Frame(main, bg=BG_DARK)
        bottom_frame.pack(fill="x")

        # 快捷记账
        self._add_btn = tk.Label(
            bottom_frame,
            text="+ 记账",
            fg=FG_PRIMARY,
            bg=ACCENT_BLUE,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=8,
            pady=3,
        )
        self._add_btn.pack(side="left")
        self._add_btn.bind("<Button-1>", lambda e: self._open_quick_add())
        self._add_btn.bind("<Enter>", lambda e: self._add_btn.configure(bg="#2563eb"))
        self._add_btn.bind("<Leave>", lambda e: self._add_btn.configure(bg=ACCENT_BLUE))

        # 新建待办
        self._todo_btn = tk.Label(
            bottom_frame,
            text="+ 待办",
            fg=FG_PRIMARY,
            bg=ACCENT_GREEN,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=8,
            pady=3,
        )
        self._todo_btn.pack(side="left", padx=(4, 0))
        self._todo_btn.bind("<Button-1>", lambda e: self._open_quick_todo())
        self._todo_btn.bind("<Enter>", lambda e: self._todo_btn.configure(bg="#16a34a"))
        self._todo_btn.bind("<Leave>", lambda e: self._todo_btn.configure(bg=ACCENT_GREEN))

        # 打开完整面板
        self._web_btn = tk.Label(
            bottom_frame,
            text="Web",
            fg=FG_PRIMARY,
            bg=BG_CARD,
            font=("Segoe UI", 10),
            cursor="hand2",
            padx=8,
            pady=3,
        )
        self._web_btn.pack(side="right")
        self._web_btn.bind("<Button-1>", lambda e: self.on_open_web())
        self._web_btn.bind("<Enter>", lambda e: self._web_btn.configure(bg=BG_HOVER))
        self._web_btn.bind("<Leave>", lambda e: self._web_btn.configure(bg=BG_CARD))

        # ── 版本标签 ──────────────────────────────────────────
        tk.Label(
            main,
            text="v1.0 · 30s refresh",
            fg="#555",
            bg=BG_DARK,
            font=("Segoe UI", 7),
        ).pack(pady=(6, 0))

        # 绑定双击打开 Web
        self.root.bind("<Double-Button-1>", lambda e: self.on_open_web())

    # ──────────────────────────────────────────────────────────────
    # 拖拽实现
    # ──────────────────────────────────────────────────────────────

    def _bind_drag(self):
        """绑定拖拽事件到标题栏"""
        self._title_bar.bind("<Button-1>", self._drag_start)
        self._title_bar.bind("<B1-Motion>", self._drag_move)
        self._title_label.bind("<Button-1>", self._drag_start)
        self._title_label.bind("<B1-Motion>", self._drag_move)

    def _drag_start(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _drag_move(self, event):
        self.root.geometry(
            f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}"
        )

    # ──────────────────────────────────────────────────────────────
    # 右键菜单
    # ──────────────────────────────────────────────────────────────

    def _build_context_menu(self):
        """构建右键弹出菜单"""
        from utils.autostart import is_autostart_enabled, set_autostart as _set_as

        self._menu = tk.Menu(self.root, tearoff=0, bg=BG_DARK, fg=FG_PRIMARY,
                             activebackground=ACCENT_BLUE, activeforeground="white")
        self._menu.add_command(label="打开完整面板", command=self.on_open_web)
        self._menu.add_separator()
        self._menu.add_command(label="切换置顶状态", command=self._toggle_pin)

        # 开机自启动
        self._autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        self._menu.add_checkbutton(
            label="开机自启动",
            command=lambda: _set_as(self._autostart_var.get()),
            variable=self._autostart_var,
        )

        self._menu.add_checkbutton(
            label="启动时自动打开 Web",
            command=lambda: self._toggle_auto_web(),
            variable=tk.BooleanVar(value=self.config.get("auto_open_web", False)),
        )
        self._menu.add_separator()
        self._menu.add_command(label="立即刷新", command=self._refresh_data)
        self._menu.add_command(label="退出", command=self.on_quit)

        # 将菜单绑定到所有组件
        def _show_menu(event):
            try:
                self._menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._menu.grab_release()
        self.root.bind("<Button-3>", _show_menu)

    # ──────────────────────────────────────────────────────────────
    # 数据刷新
    # ──────────────────────────────────────────────────────────────

    def _refresh_data(self):
        """刷新所有数据（在后台线程执行网络请求）"""
        # 本地数据（数据库）在主线程刷新
        self._refresh_todos()

        # 网络数据在后台线程刷新
        city = self.config.get("city", "Beijing")

        def _fetch_network():
            self._weather_text = fetch_weather(city=city)
            self._ipv4_local = get_internal_ipv4()
            self._ipv6_local = get_internal_ipv6()
            self._ipv4_public = get_external_ipv4()
            self._ipv6_public = get_external_ipv6()
            # 回到主线程更新 UI
            self.root.after(0, self._update_display)

        t = threading.Thread(target=_fetch_network, daemon=True)
        t.start()

    def _refresh_todos(self):
        """从数据库读取今日待办"""
        today = date.today()
        db = SessionLocal()
        try:
            todos = (
                db.query(Todo)
                .filter(
                    Todo.due_date == today,
                    Todo.is_completed == False,
                )
                .order_by(Todo.priority.asc())
                .all()
            )
            self._todos_data = [
                {
                    "id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "is_completed": t.is_completed,
                }
                for t in todos
            ]
        finally:
            db.close()

    def _update_display(self):
        """将缓存数据刷新到 UI 组件"""
        # 天气（含城市名）
        city = self.config.get("city", "Beijing")
        self._weather_label.configure(text=f"{city} {self._weather_text}")

        # 待办
        count = len(self._todos_data)
        if count == 0:
            self._todo_count_label.configure(text="待办: 0 项", fg=FG_SECONDARY)
        else:
            self._todo_count_label.configure(
                text=f"待办: {count} 项", fg=ACCENT_YELLOW
            )

        # 刷新展开的待办列表
        self._render_todo_list()

        # IP
        self._update_ip_display()

    def _update_ip_display(self):
        """IP 显示：内/外网两档，每档上下行分显 v4 + v6"""
        if self._ip_index == 0:
            self._ip_kind_label.configure(text="内网", fg=ACCENT_BLUE)
            self._ip_switch_label.configure(text="\N{RIGHTWARDS ARROW} 外网")
            self._ip_icon.configure(text="\U0001F5A5")
            v4 = self._ipv4_local or "--"
            v6 = self._ipv6_local or "--"
        else:
            self._ip_kind_label.configure(text="公网", fg=ACCENT_GREEN)
            self._ip_switch_label.configure(text="\N{LEFTWARDS ARROW} 内网")
            self._ip_icon.configure(text="\U0001F310")
            v4 = self._ipv4_public or "--"
            v6 = self._ipv6_public or "--"
        self._ipv4_label.configure(text=v4)
        self._ipv6_label.configure(text=v6)

    # ──────────────────────────────────────────────────────────────
    # 待办展开/收起
    # ──────────────────────────────────────────────────────────────

    def _toggle_todos(self):
        """展开/收起待办列表"""
        self._todos_expanded = not self._todos_expanded
        if self._todos_expanded:
            self._todo_expand_icon.configure(text="▼")
            self._render_todo_list()
            self._todo_list_frame.pack(fill="x", pady=(4, 0))
        else:
            self._todo_expand_icon.configure(text="▶")
            self._todo_list_frame.pack_forget()

    def _render_todo_list(self):
        """渲染待办列表内容"""
        for w in self._todo_list_frame.winfo_children():
            w.destroy()

        if not self._todos_expanded:
            return

        if not self._todos_data:
            tk.Label(
                self._todo_list_frame,
                text="  今天没有待办 🎉",
                fg=FG_SECONDARY,
                bg=BG_CARD,
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x")
            return

        for todo in self._todos_data:
            priority_icon = {1: "🔴", 2: "🟡", 3: "🟢"}.get(todo["priority"], "🟡")
            row = tk.Frame(self._todo_list_frame, bg=BG_CARD)
            row.pack(fill="x", pady=1)

            # 勾选按钮
            var = tk.BooleanVar(value=todo["is_completed"])
            cb = tk.Checkbutton(
                row,
                text=f"  {priority_icon} {todo['title']}",
                variable=var,
                fg=FG_PRIMARY,
                bg=BG_CARD,
                selectcolor=BG_CARD,
                activebackground=BG_CARD,
                activeforeground=FG_PRIMARY,
                font=("Segoe UI", 9),
                anchor="w",
                command=lambda tid=todo["id"], v=var: self._on_todo_check(tid, v),
            )
            cb.pack(side="left", fill="x")

    def _on_todo_check(self, todo_id: int, var: tk.BooleanVar):
        """勾选/取消待办"""
        db = SessionLocal()
        try:
            record = db.query(Todo).filter(Todo.id == todo_id).first()
            if record:
                record.is_completed = var.get()
                db.commit()
        finally:
            db.close()
        # 延迟刷新列表
        self.root.after(500, lambda: self._refresh_todos() or self._render_todo_list())

    # ──────────────────────────────────────────────────────────────
    # IP 切换与复制
    # ──────────────────────────────────────────────────────────────

    def _toggle_ip(self):
        """切换内外网显示"""
        self._ip_index = 1 - self._ip_index
        self._update_ip_display()

    def _copy_ip(self, line: int):
        """复制 IP 到剪贴板（line: 0=v4行, 1=v6行）"""
        if self._ip_index == 0:
            ip = self._ipv4_local if line == 0 else self._ipv6_local
            btn = self._ipv4_copy if line == 0 else self._ipv6_copy
        else:
            ip = self._ipv4_public if line == 0 else self._ipv6_public
            btn = self._ipv4_copy if line == 0 else self._ipv6_copy
        if ip and ip not in ("--", "获取失败", "IPv6 不可用", "::1"):
            self.root.clipboard_clear()
            self.root.clipboard_append(ip)
            btn.configure(text="ok")
            self.root.after(1500, lambda b=btn: b.configure(text="cp"))

    # ──────────────────────────────────────────────────────────────
    # 置顶切换
    # ──────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────
    # Win32 置顶（绕过 tkinter，直接操作窗口）
    # ──────────────────────────────────────────────────────────

    def _win_set_topmost(self, enable: bool):
        """使用 Win32 SetWindowPos 直接设置/取消窗口置顶。"""
        if sys.platform != "win32":
            self.root.attributes("-topmost", enable)
            self.root.lift()
            return

        hwnd = self.root.winfo_id()
        flag = self._HWND_TOPMOST if enable else self._HWND_NOTOPMOST
        _user32.SetWindowPos(
            hwnd, flag, 0, 0, 0, 0,
            self._SWP_NOMOVE | self._SWP_NOSIZE | self._SWP_NOACTIVATE,
        )
        # 同步 tkinter 内部状态
        self.root.attributes("-topmost", enable)

    def _sync_pin_ui(self):
        """根据 tkinter 实际 topmost 状态同步图标和配置

        图标约定（用户确认）：
          - 置顶中 → \N{PUSHPIN}（针扎下去）
          - 未置顶 → \N{ROUND PUSHPIN}（针收起来）
        """
        actual = bool(self.root.attributes("-topmost"))
        self.config["always_on_top"] = actual
        if actual:
            self._pin_btn.configure(text="\N{PUSHPIN}", fg=ACCENT_BLUE)
        else:
            self._pin_btn.configure(text="\N{ROUND PUSHPIN}", fg=FG_SECONDARY)

    def _toggle_pin(self):
        """切换窗口置顶状态"""
        # 读取当前状态，翻转
        is_topmost = bool(self.root.attributes("-topmost"))
        target = not is_topmost

        # 通过 Win32 API 设置置顶（比 tkinter 更可靠）
        self._win_set_topmost(target)

        # 同步图标
        self._sync_pin_ui()
        save_config(self.config)

        # 置顶时提升窗口层级
        if target:
            self.root.lift()

    # ──────────────────────────────────────────────────────────────
    # 自动打开 Web 开关
    # ──────────────────────────────────────────────────────────────

    def _toggle_auto_web(self):
        """切换开机自动打开 Web 选项"""
        self.config["auto_open_web"] = not self.config.get("auto_open_web", False)
        save_config(self.config)

    # ──────────────────────────────────────────────────────────────
    # 快捷记账
    # ──────────────────────────────────────────────────────────────

    def _open_quick_add(self):
        """打开简易记账输入窗口"""
        popup = tk.Toplevel(self.root)
        popup.title("快捷记账")
        popup.geometry("280x260")
        popup.resizable(False, False)
        popup.configure(bg=BG_DARK)
        popup.attributes("-topmost", True)

        # 居中于悬浮窗
        popup.transient(self.root)
        x = self.root.winfo_x() + (self.root.winfo_width() - 280) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
        popup.geometry(f"+{x}+{y}")

        # ── 内容 ────────────────────────────────────────────────
        inner = tk.Frame(popup, bg=BG_DARK, padx=12, pady=10)
        inner.pack(fill="both", expand=True)

        tk.Label(
            inner, text="＋ 快捷记账", fg=FG_PRIMARY, bg=BG_DARK,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        # 金额
        tk.Label(
            inner, text="金额", fg=FG_SECONDARY, bg=BG_DARK, font=("Segoe UI", 9),
        ).pack(anchor="w")
        amount_var = tk.StringVar()
        amount_entry = tk.Entry(
            inner, textvariable=amount_var, bg=BG_CARD, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, relief="flat", font=("Segoe UI", 11),
        )
        amount_entry.pack(fill="x", ipady=2, pady=(0, 6))
        amount_entry.focus_set()

        # 分类
        tk.Label(
            inner, text="分类", fg=FG_SECONDARY, bg=BG_DARK, font=("Segoe UI", 9),
        ).pack(anchor="w")
        category_var = tk.StringVar(value="餐饮")
        category_entry = tk.Entry(
            inner, textvariable=category_var, bg=BG_CARD, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, relief="flat", font=("Segoe UI", 11),
        )
        category_entry.pack(fill="x", ipady=2, pady=(0, 6))

        # 备注
        tk.Label(
            inner, text="备注（可选）", fg=FG_SECONDARY, bg=BG_DARK, font=("Segoe UI", 9),
        ).pack(anchor="w")
        note_var = tk.StringVar()
        note_entry = tk.Entry(
            inner, textvariable=note_var, bg=BG_CARD, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, relief="flat", font=("Segoe UI", 11),
        )
        note_entry.pack(fill="x", ipady=2, pady=(0, 8))

        # 按钮
        btn_frame = tk.Frame(inner, bg=BG_DARK)
        btn_frame.pack(fill="x")

        def _save():
            try:
                amt = float(amount_var.get())
            except ValueError:
                messagebox.showwarning("输入错误", "请输入有效的金额数字", parent=popup)
                return

            cat = category_var.get().strip() or "其他"
            note = note_var.get().strip()
            db = SessionLocal()
            try:
                db.add(Transaction(
                    date=date.today(),
                    type="expense",
                    category=cat,
                    amount=amt,
                    note=note if note else "快捷记账",
                ))
                db.commit()
            finally:
                db.close()
            popup.destroy()
            self._refresh_todos()

        tk.Button(
            btn_frame, text="保存", command=_save,
            bg=ACCENT_BLUE, fg="white", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=8, pady=2,
            activebackground="#2563eb", activeforeground="white", cursor="hand2",
        ).pack(side="right")
        tk.Button(
            btn_frame, text="取消", command=popup.destroy,
            bg=BG_CARD, fg=FG_PRIMARY, relief="flat",
            font=("Segoe UI", 10), padx=8, pady=2,
            activebackground=BG_HOVER, activeforeground=FG_PRIMARY, cursor="hand2",
        ).pack(side="right", padx=(0, 8))

    # ──────────────────────────────────────────────────────────────
    # 快捷新建待办
    # ──────────────────────────────────────────────────────────────

    def _open_quick_todo(self):
        """打开简易新建待办窗口"""
        popup = tk.Toplevel(self.root)
        popup.title("新建待办")
        popup.geometry("280x200")
        popup.resizable(False, False)
        popup.configure(bg=BG_DARK)
        popup.attributes("-topmost", True)
        popup.transient(self.root)
        x = self.root.winfo_x() + (self.root.winfo_width() - 280) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        popup.geometry(f"+{x}+{y}")

        inner = tk.Frame(popup, bg=BG_DARK, padx=12, pady=10)
        inner.pack(fill="both", expand=True)

        tk.Label(
            inner, text="+ 新建待办", fg=FG_PRIMARY, bg=BG_DARK,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            inner, text="标题", fg=FG_SECONDARY, bg=BG_DARK, font=("Segoe UI", 9),
        ).pack(anchor="w")
        title_var = tk.StringVar()
        title_entry = tk.Entry(
            inner, textvariable=title_var, bg=BG_CARD, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, relief="flat", font=("Segoe UI", 11),
        )
        title_entry.pack(fill="x", ipady=2, pady=(0, 6))
        title_entry.focus_set()

        # 优先级选择
        tk.Label(
            inner, text="优先级", fg=FG_SECONDARY, bg=BG_DARK, font=("Segoe UI", 9),
        ).pack(anchor="w")
        priority_var = tk.StringVar(value="2")
        prio_frame = tk.Frame(inner, bg=BG_DARK)
        prio_frame.pack(fill="x", pady=(0, 6))
        for val, label, color in [(1, "高", ACCENT_RED), (2, "中", ACCENT_YELLOW), (3, "低", ACCENT_GREEN)]:
            rb = tk.Radiobutton(
                prio_frame, text=label, variable=priority_var, value=str(val),
                bg=BG_DARK, fg=color, selectcolor=BG_DARK,
                activebackground=BG_DARK, activeforeground=color,
                font=("Segoe UI", 10),
            )
            rb.pack(side="left", padx=4)

        # 按钮
        btn_f = tk.Frame(inner, bg=BG_DARK)
        btn_f.pack(fill="x")

        def _save_todo():
            title = title_var.get().strip()
            if not title:
                messagebox.showwarning("输入错误", "请输入待办标题", parent=popup)
                return
            db = SessionLocal()
            try:
                db.add(Todo(
                    title=title,
                    priority=int(priority_var.get()),
                    due_date=date.today(),
                    date_created=date.today(),
                    is_completed=False,
                ))
                db.commit()
            finally:
                db.close()
            popup.destroy()
            self._refresh_todos()
            self._update_display()

        tk.Button(
            btn_f, text="保存", command=_save_todo,
            bg=ACCENT_GREEN, fg="white", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=8, pady=2,
            activebackground="#16a34a", activeforeground="white", cursor="hand2",
        ).pack(side="right")
        tk.Button(
            btn_f, text="取消", command=popup.destroy,
            bg=BG_CARD, fg=FG_PRIMARY, relief="flat",
            font=("Segoe UI", 10), padx=8, pady=2,
            activebackground=BG_HOVER, activeforeground=FG_PRIMARY, cursor="hand2",
        ).pack(side="right", padx=(0, 8))

    # ──────────────────────────────────────────────────────────────
    # 周期刷新
    # ──────────────────────────────────────────────────────────────

    def _schedule_periodic_refresh(self):
        """每 30 秒自动刷新数据"""
        self._refresh_data()
        self.root.after(30000, self._schedule_periodic_refresh)

    # ──────────────────────────────────────────────────────────────
    # 生命周期
    # ──────────────────────────────────────────────────────────────

    def run(self):
        """启动 tkinter 主循环（阻塞）"""
        self.root.mainloop()

    def destroy(self):
        """销毁悬浮窗（从其他线程安全关闭）"""
        try:
            if self.root.winfo_exists():
                self.root.after(0, self.root.destroy)
        except TclError:
            pass
