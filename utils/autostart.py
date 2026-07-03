"""
开机自启动管理

Windows:  在 Startup 目录创建快捷方式 (.bat)
macOS:    创建 LaunchAgent plist（待实现）
Linux:    创建 ~/.config/autostart 桌面文件（待实现）

用法:
    from utils.autostart import is_autostart_enabled, enable_autostart, disable_autostart
"""

import os
import sys
from pathlib import Path

# ── 启动脚本名 ──────────────────────────────────────────────────
SCRIPT_NAME = "MLT_autostart.bat"


def _startup_dir() -> Path:
    """获取系统 Startup 目录"""
    if sys.platform == "win32":
        # %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents"
    else:
        return Path.home() / ".config" / "autostart"


def _startup_file() -> Path:
    return _startup_dir() / SCRIPT_NAME


def is_autostart_enabled() -> bool:
    """检测是否已设置开机自启动"""
    return _startup_file().exists()


def enable_autostart() -> bool:
    """
    启用开机自启动。

    Windows: 在 Startup 目录创建 .bat 脚本，静默启动 MLT。
    返回 True 表示成功。
    """
    try:
        startup_dir = _startup_dir()
        startup_dir.mkdir(parents=True, exist_ok=True)

        # 项目根目录
        project_dir = Path(__file__).resolve().parent.parent
        pythonw = project_dir / ".venv" / "Scripts" / "pythonw.exe"
        app = project_dir / "app.py"

        if not pythonw.exists():
            # 降级：使用系统 Python（需在 PATH 中）
            pythonw = Path("pythonw")

        bat_content = f'''@echo off
cd /d "{project_dir}"
start "" "{pythonw}" "{app}"
'''

        _startup_file().write_text(bat_content, encoding="gbk" if sys.platform == "win32" else "utf-8")
        return True
    except OSError:
        return False


def disable_autostart() -> bool:
    """
    禁用开机自启动。
    返回 True 表示成功（文件本就不存在也视为成功）。
    """
    try:
        f = _startup_file()
        if f.exists():
            f.unlink()
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """启用或禁用，返回是否成功"""
    return enable_autostart() if enabled else disable_autostart()


# ── 自测 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Startup 目录 : {_startup_dir()}")
    print(f"启动脚本     : {_startup_file()}")
    print(f"当前状态     : {'已启用' if is_autostart_enabled() else '未启用'}")

    if not is_autostart_enabled():
        ok = enable_autostart()
        print(f"启用自启动   : {'成功' if ok else '失败'}")
        print(f"脚本内容     :\\n{_startup_file().read_text() if ok else 'N/A'}")
    else:
        ok = disable_autostart()
        print(f"禁用自启动   : {'成功' if ok else '失败'}")
