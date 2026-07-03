"""
插件管理页面 —— /admin/plugins

展示所有已加载插件，提供启用/禁用开关。
状态持久化到 settings 表。
"""

from nicegui import ui

from modules.layout import add_header
from plugins import BasePlugin, plugin_loader


class AdminPlugin(BasePlugin):
    name = "admin"
    title = "插件管理"
    version = "1.0.0"
    author = "MLT"
    description = "管理所有插件的启用/禁用状态"

    def register(self):
        @ui.page("/admin/plugins")
        def admin_plugins_page():
            add_header()

            # 面包屑
            with ui.row().classes("items-center gap-4 px-3 pt-2 pb-1"):
                ui.link("首页", target="/").classes("text-grey-6 no-underline")
                ui.label(">").classes("text-grey-6")
                ui.label("插件管理").classes("text-h6 font-bold")
            ui.separator()

            ui.label("已加载的插件").classes("text-h6 px-4 pt-4 pb-2")
            ui.label("启用或禁用插件后需重启应用生效。").classes("text-caption text-grey-6 px-4 pb-2")

            def _render_list():
                """渲染插件列表（refreshable）"""
                plugins_info = plugin_loader.list_plugins()

                if not plugins_info:
                    ui.label("未发现任何插件").classes("text-grey-6 px-4 py-8")
                    return

                for p in plugins_info:
                    with ui.card().classes("w-full mx-3 mb-2"):
                        with ui.row().classes("items-center justify-between w-full"):
                            with ui.column().classes("gap-0"):
                                ui.label(p["title"]).classes("font-bold")
                                ui.label(
                                    f"v{p['version']} · {p['author']} · {p['description']}"
                                ).classes("text-caption text-grey-6")

                            switch = ui.switch(
                                value=p["enabled"],
                                on_change=lambda e, name=p["name"]: _on_toggle(name, e.value),
                            )

            def _on_toggle(name: str, enabled: bool):
                plugin_loader.set_enabled(name, enabled)
                status = "已启用" if enabled else "已禁用"
                ui.notify(f"「{name}」{status}，重启后生效")

            _render_list()

            ui.separator().classes("my-4")

            with ui.card().classes("w-full mx-3 mb-4"):
                ui.label("说明").classes("text-h6 font-bold pb-2")
                ui.label(
                    "插件状态存储在数据库中。禁用插件后："
                ).classes("text-grey-6 pb-1")
                ui.label("  - 对应路由不可访问（404）").classes("text-caption text-grey-6")
                ui.label("  - 侧边栏菜单隐藏").classes("text-caption text-grey-6")
                ui.label("  - 悬浮窗和系统托盘不受影响").classes("text-caption text-grey-6")

    def menu_item(self):
        return ("插件管理", "/admin/plugins")
