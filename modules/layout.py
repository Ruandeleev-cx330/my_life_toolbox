"""
共享布局组件 —— 导航抽屉 + 全局搜索头栏
每个页面导入 add_header() 即可获得统一的汉堡菜单导航和顶部搜索框。
"""

from nicegui import ui

from utils.search_engine import search_all

NAV_ITEMS = [
    ("🏠", "首页", "/"),
    ("📅", "日历日程", "/calendar"),
    ("💰", "记账管理", "/finance"),
    ("📖", "写日记", "/diary"),
    ("📂", "Rnote 管理器", "/rnote"),
    ("🧰", "小工具", "/gadgets"),
    ("⚙️", "数据保险箱", "/settings"),
]


def add_header():
    """
    为当前页面添加：
    1. 顶部搜索头栏（汉堡菜单 + 标题 + 搜索框）
    2. 左侧滑出导航抽屉，包含所有页面链接
    3. 全局搜索对话框（回车或点击 🔍 触发）
    """
    # ── 导航抽屉 ──────────────────────────────────────────
    drawer = ui.left_drawer(value=False, fixed=False).classes("bg-blue-50")

    with drawer:
        with ui.column().classes("p-4 gap-1 w-full"):
            ui.label("🧰 My Life Toolbox").classes("text-h6 font-bold pb-2")
            ui.separator()
            for icon, label, target in NAV_ITEMS:
                ui.link(f"{icon}  {label}", target=target).classes(
                    "no-underline text-base py-2 px-2 rounded hover:bg-blue-100 w-full block"
                )

    # ── 搜索对话框（模块级，只创建一次）───────────────
    search_dialog = ui.dialog().props("maximized")

    with search_dialog, ui.card().classes("w-full max-w-3xl mx-auto q-pa-lg"):
        with ui.row().classes("items-center justify-between w-full pb-4"):
            ui.label("🔍 全局搜索").classes("text-h5 font-bold")
            ui.button("✕", on_click=search_dialog.close).props("flat dense round")

        search_results_container = ui.column().classes("w-full gap-2")

    # ── 搜索功能 ──────────────────────────────────────────
    def _do_search():
        query = search_input.value.strip()
        if not query:
            ui.notify("请输入搜索关键词", type="warning")
            return

        results = search_all(query)

        search_results_container.clear()
        with search_results_container:
            if not results:
                with ui.card().classes("w-full p-6 text-center"):
                    ui.label(f"🔍 未找到与「{query}」相关的内容").classes(
                        "text-grey-6 text-lg"
                    )
                    ui.label("尝试其他关键词，如「餐饮」「数学」「日记」").classes(
                        "text-caption text-grey-5"
                    )
            else:
                ui.label(
                    f"找到 {len(results)} 条与「{query}」相关的结果"
                ).classes("text-caption text-grey-6 pb-2")

                for r in results:
                    with ui.card().classes("w-full p-3"):

                        def _make_nav(url):
                            return lambda: _navigate(url)

                        with ui.row().classes("items-center justify-between w-full"):
                            with ui.column().classes("gap-0"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(r["type_label"]).classes(
                                        f"text-caption font-bold {r['type_color']}"
                                    )
                                    if r.get("date"):
                                        ui.label(r["date"]).classes(
                                            "text-caption text-grey-5"
                                        )
                                ui.label(r["title"]).classes("font-bold")
                                ui.label(r["detail"]).classes(
                                    "text-caption text-grey-6"
                                )
                            ui.button(
                                "→ 跳转",
                                on_click=_make_nav(r["url"]),
                            ).props("flat dense color=primary")

        search_dialog.open()

    def _navigate(url: str):
        """关闭搜索对话框并跳转到目标页面"""
        search_dialog.close()
        ui.navigate(to=url)

    # ── 顶部头栏 ──────────────────────────────────────────
    with ui.row().classes(
        "items-center gap-3 w-full px-3 py-2 bg-blue-50 border-b border-grey-3"
    ):
        ui.button("☰", on_click=lambda: drawer.toggle()).props("flat dense round")
        with ui.row().classes("items-center gap-1"):
            ui.link("🧰 MLT", target="/").classes(
                "text-h6 font-bold no-underline text-grey-9"
            )
        ui.space()

        search_input = (
            ui.input(placeholder="搜索记账/待办/日记/笔记…")
            .props("dense outlined clearable")
            .classes("w-56")
        )
        search_input.on("keydown.enter", _do_search)
        ui.button("🔍", on_click=_do_search).props("flat dense round")

    return drawer
