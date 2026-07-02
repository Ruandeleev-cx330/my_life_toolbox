"""
锚点面板 —— 首页 Dashboard
路由：/
功能：日期天气展示 + 今日待办清单 + 快速入口按钮
"""

from datetime import date

from nicegui import ui

from core.database import SessionLocal, Todo
from modules.layout import add_header
from utils.weather import fetch_weather


# ── 页面路由 ────────────────────────────────────────────────────
@ui.page("/")
def dashboard_page():
    """首页锚点面板"""

    # 导航抽屉
    add_header()

    # ══════════════════════════════════════════════════════════════
    # 顶部区域：日期 + 天气 + 导航
    # ══════════════════════════════════════════════════════════════
    with ui.row().classes("items-center justify-between w-full px-4 pt-4"):
        # 中文日期
        today = date.today()
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        wd = weekdays[today.weekday()]
        date_str = f"{today.year}年{today.month:02d}月{today.day:02d}日 星期{wd}"
        ui.label(date_str).classes("text-h5 font-bold")

        # 天气（同步请求，3 秒超时）
        weather_text = fetch_weather()
        ui.label(weather_text).classes("text-h6 text-grey-7")

    # 页面快捷导航
    with ui.row().classes("px-4 pb-1 gap-4"):
        ui.link("🏠 首页", target="/").classes("text-blue-5 font-bold no-underline")
        ui.link("📅 日历", target="/calendar").classes("text-grey-6 no-underline")
        ui.link("📂 Rnote", target="/rnote").classes("text-grey-6 no-underline")
        ui.link("💰 记账", target="/finance").classes("text-grey-6 no-underline")
        ui.link("📖 日记", target="/diary").classes("text-grey-6 no-underline")
        ui.link("🧰 工具", target="/gadgets").classes("text-grey-6 no-underline")

    ui.separator()

    # ══════════════════════════════════════════════════════════════
    # 主体区域：今日待办清单
    # ══════════════════════════════════════════════════════════════
    ui.label("📋 今日待办").classes("text-h6 px-4 pt-2")

    # 查询数据库：今日创建且未完成的待办
    db = SessionLocal()
    try:
        todos = (
            db.query(Todo)
            .filter(
                Todo.date_created == today,
                Todo.is_completed == False,
            )
            .order_by(Todo.priority.asc(), Todo.due_date.asc())
            .all()
        )
    finally:
        db.close()

    if not todos:
        ui.label("🎉 今天没有待办事项，享受轻松的一天！").classes(
            "text-grey-6 px-4 py-8"
        )
    else:
        with ui.column().classes("px-4 gap-2 w-full"):
            for todo in todos:
                _render_todo_item(todo)

    ui.separator()

    # ══════════════════════════════════════════════════════════════
    # 底部区域：快速入口按钮
    # ══════════════════════════════════════════════════════════════
    ui.label("⚡ 快速入口").classes("text-h6 px-4 pt-2")

    with ui.row().classes("px-4 pb-4 gap-3 flex-wrap"):
        ui.button("📝 记账", on_click=lambda: ui.navigate("/finance")).classes("text-lg")
        ui.button("✅ 新建待办", on_click=lambda: ui.notify("新建待办页面开发中...")).classes("text-lg")
        ui.button("📖 写日记", on_click=lambda: ui.navigate("/diary")).classes("text-lg")
        ui.button("📂 归类Rnote", on_click=lambda: ui.navigate("/rnote")).classes("text-lg")


# ── 辅助组件 ────────────────────────────────────────────────────
def _render_todo_item(todo: Todo):
    """渲染单条待办：复选框 + 标题 + 优先级标签"""

    # 优先级配色
    priority_labels = {1: ("🔴 高", "text-red-6"), 2: ("🟡 中", "text-amber-6"), 3: ("🟢 低", "text-green-6")}
    label, color_class = priority_labels.get(todo.priority, ("🟡 中", "text-amber-6"))

    def on_check(e, t=todo):
        """勾选复选框 → 更新数据库完成状态"""
        db = SessionLocal()
        try:
            record = db.query(Todo).filter(Todo.id == t.id).first()
            if record:
                record.is_completed = e.value
                db.commit()
        finally:
            db.close()

    with ui.row().classes("items-center gap-2"):
        ui.checkbox(
            text=f"{todo.title}　{label}",
            value=todo.is_completed,
            on_change=on_check,
        ).classes(color_class)

        if todo.due_date:
            ui.label(f"📅 {todo.due_date}").classes("text-caption text-grey-6")
