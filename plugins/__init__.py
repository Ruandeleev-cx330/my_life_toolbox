"""
插件系统核心 —— BasePlugin + PluginLoader

用法：
    from plugins import PluginLoader
    loader = PluginLoader()
    loader.discover()          # 扫描 /plugins 目录
    loader.register_enabled()  # 为启用的插件注册路由
    menu_items = loader.get_menu_items()  # 获取侧边栏菜单
"""

import importlib
import json
import os
import pkgutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

from core.database import SessionLocal, Setting


# ═══════════════════════════════════════════════════════════════════
# 插件基类
# ═══════════════════════════════════════════════════════════════════

class BasePlugin(ABC):
    """
    所有插件必须继承此类。

    属性：
        name:        插件唯一标识（kebab-case）
        title:       菜单显示名称
        version:     版本号
        author:      作者
        description: 描述文本

    方法：
        register()    注册 NiceGUI 路由（@ui.page）
        menu_item()   返回 (label, path) 或 None（不显示在菜单）
        on_enable()   启用时的回调
        on_disable()  禁用时的回调
    """

    name: str = ""
    title: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

    @abstractmethod
    def register(self) -> None:
        """注册 NiceGUI 路由。在此方法内使用 @ui.page() 装饰器。"""
        ...

    def menu_item(self) -> Optional[tuple[str, str]]:
        """返回 (label, path) 用于侧边栏菜单，返回 None 则不显示。"""
        return None

    def on_enable(self) -> None:
        """插件被启用时调用"""
        pass

    def on_disable(self) -> None:
        """插件被禁用时调用"""
        pass


# ═══════════════════════════════════════════════════════════════════
# 插件加载器
# ═══════════════════════════════════════════════════════════════════

class PluginLoader:
    """
    扫描、加载、管理插件的生命周期。

    职责：
      1. 扫描 /plugins 目录，发现所有 BasePlugin 子类
      2. 管理启用/禁用状态（持久化到 settings 表）
      3. 注册/注销路由
      4. 提供动态菜单数据
    """

    def __init__(self):
        self._plugins: dict[str, BasePlugin] = {}       # name -> instance
        self._plugin_classes: list[type] = []
        self._menu_items: list[tuple[str, str]] = []

    # ── 发现 ──────────────────────────────────────────────────

    def discover(self, package_path: str = "plugins") -> None:
        """
        扫描插件包，找到所有 BasePlugin 子类并实例化。
        默认扫描当前 plugins/ 目录。
        """
        self._plugin_classes.clear()
        self._plugins.clear()

        package = importlib.import_module(package_path)
        pkg_dir = Path(package.__file__).parent if package.__file__ else Path(package_path)

        for _, name, is_pkg in pkgutil.iter_modules([str(pkg_dir)]):
            if name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"{package_path}.{name}")
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin
                    ):
                        instance = attr()
                        self._plugins[instance.name] = instance
            except Exception as e:
                print(f"[PluginLoader] Failed to load {name}: {e}")

    # ── 注册 / 注销 ──────────────────────────────────────────

    def register_enabled(self) -> None:
        """为所有启用状态的插件注册路由。在 ui.run() 之前调用。"""
        self._menu_items.clear()

        for name, plugin in self._plugins.items():
            if self.is_enabled(name):
                try:
                    plugin.register()
                    menu = plugin.menu_item()
                    if menu:
                        self._menu_items.append(menu)
                    print(f"[PluginLoader] Registered: {name}")
                except Exception as e:
                    print(f"[PluginLoader] Error registering {name}: {e}")

    # ── 启用 / 禁用 ──────────────────────────────────────────

    def is_enabled(self, name: str) -> bool:
        """查询插件是否启用。默认启用。"""
        db = SessionLocal()
        try:
            row = db.query(Setting).filter(Setting.key == f"plugin.{name}.enabled").first()
            if row is None:
                return True  # 首次加载默认启用
            return row.value.strip().lower() in ("true", "1", "yes")
        finally:
            db.close()

    def set_enabled(self, name: str, enabled: bool) -> None:
        """设置插件启用/禁用状态"""
        db = SessionLocal()
        try:
            row = db.query(Setting).filter(Setting.key == f"plugin.{name}.enabled").first()
            value = "true" if enabled else "false"
            if row:
                row.value = value
            else:
                db.add(Setting(key=f"plugin.{name}.enabled", value=value))
            db.commit()

            plugin = self._plugins.get(name)
            if plugin:
                if enabled:
                    plugin.on_enable()
                else:
                    plugin.on_disable()
        finally:
            db.close()

    # ── 查询接口 ─────────────────────────────────────────────

    def get_menu_items(self) -> list[tuple[str, str]]:
        """获取所有已启用插件的菜单项 [(label, path), ...]"""
        return list(self._menu_items)

    def list_plugins(self) -> list[dict]:
        """获取所有插件信息列表（供管理页面使用）"""
        result = []
        for name, plugin in self._plugins.items():
            result.append({
                "name": name,
                "title": plugin.title or name,
                "version": plugin.version,
                "author": plugin.author,
                "description": plugin.description,
                "enabled": self.is_enabled(name),
                "has_menu": plugin.menu_item() is not None,
            })
        result.sort(key=lambda p: p["name"])
        return result

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """按名称获取插件实例"""
        return self._plugins.get(name)


# ── 全局单例 ──────────────────────────────────────────────────────
plugin_loader = PluginLoader()
