"""
锚点面板 —— 首页 Dashboard
路由：/
功能：日期天气展示 + 今日待办清单（可刷新） + 快速入口按钮
"""

from datetime import date

from nicegui import ui

from core.database import SessionLocal, Todo
from modules.layout import add_header
from utils.weather import fetch_weather


# ══════════════════════════════════════════════════════════════════
# 新建待办对话框
# ══════════════════════════════════════════════════════════════════

def _show_todo_dialog(todo: Todo | None, on_done):
    """新建或编辑待办事项对话框"""
    is_new = todo is None

    with ui.dialog() as dlg:
        with ui.card().style("width: 450px; max-width: 90vw;"):
            ui.label("➕ 新建待办" if is_new else "✏️ 编辑待办").classes("text-h6 font-bold pb-2")

            title = ui.input(
                label="标题", placeholder="待办事项标题...",
                value="" if is_new else todo.title,
            ).classes("w-full")

            desc = ui.textarea(
                label="描述（可选）", value="" if is_new else (todo.description or ""),
            ).classes("w-full").props("rows=3")

            with ui.row().classes("gap-4"):
                if is_new:
                    ui.label("📅 截止日期（可选）").classes("text-caption text-grey-6")
                    due_date = ui.date(value=str(date.today()))
                else:
                    ui.label(f"创建于：{todo.date_created}").classes("text-caption")

                priority = ui.select(
                    label="优先级",
                    options={1: "🔴 高", 2: "🟡 中", 3: "🟢 低"},
                    value=todo.priority if not is_new else 2,
                )

            def _save():
                s = SessionLocal()
                try:
                    if is_new:
                        raw = due_date.value
                        # ui.date.value 可能返回 str("YYYY-MM-DD") 或 date 对象
                        if isinstance(raw, date):
                            d = raw
                        elif isinstance(raw, str) and raw:
                            parts = raw.split("-")
                            d = date(int(parts[0]), int(parts[1]), int(parts[2]))
                        else:
                            d = date.today()  # 未选择时默认今天
                        s.add(Todo(
                            title=title.value,
                            description=desc.value or "",
                            due_date=d,
                            priority=priority.value,
                            date_created=date.today(),
                            is_completed=False,
                        ))
                    else:
                        record = s.query(Todo).filter(Todo.id == todo.id).first()
                        if record:
                            record.title = title.value
                            record.description = desc.value or ""
                            record.priority = priority.value
                    s.commit()
                finally:
                    s.close()
                dlg.close()
                on_done()
                ui.notify("待办已保存" if is_new else "待办已更新")

            with ui.row().classes("gap-2 justify-end w-full pt-2"):
                ui.button("取消", on_click=dlg.close).props("flat")
                ui.button("保存", on_click=_save).props("color=primary")
    dlg.open()


# ══════════════════════════════════════════════════════════════════
# 今日待办列表（可刷新）
# ══════════════════════════════════════════════════════════════════

@ui.refreshable
def _today_todo_list(today: date):
    """查询并渲染今日待办列表"""
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
    finally:
        db.close()

    if not todos:
        ui.label("今天没有待办事项").classes(
            "text-grey-6 px-4 py-8"
        )
    else:
        with ui.column().classes("px-4 gap-2 w-full"):
            for todo in todos:
                _render_todo_item(todo)


# ══════════════════════════════════════════════════════════════════
# 页面入口
# ══════════════════════════════════════════════════════════════════

@ui.page("/")
def dashboard_page():
    """首页锚点面板"""

    add_header()

    today = date.today()

    # ══════════════════════════════════════════════════════════
    # 顶部区域：日期 + 天气 + 导航
    # ══════════════════════════════════════════════════════════
    with ui.row().classes("items-center justify-between w-full px-4 pt-4"):
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        wd = weekdays[today.weekday()]
        date_str = f"{today.year}年{today.month:02d}月{today.day:02d}日 星期{wd}"
        ui.label(date_str).classes("text-h5 font-bold")

        weather_text = fetch_weather()
        ui.label(weather_text).classes("text-h6 text-grey-7")

    # 页面快捷导航
    with ui.row().classes("px-4 pb-1 gap-4"):
        ui.link("首页", target="/").classes("text-blue-5 font-bold no-underline")
        ui.link("日历", target="/calendar").classes("text-grey-6 no-underline")
        ui.link("Rnote", target="/rnote").classes("text-grey-6 no-underline")
        ui.link("记账", target="/finance").classes("text-grey-6 no-underline")
        ui.link("日记", target="/diary").classes("text-grey-6 no-underline")
        ui.link("工具", target="/gadgets").classes("text-grey-6 no-underline")

    ui.separator()

    # ══════════════════════════════════════════════════════════
    # 主体区域：今日待办清单
    # ══════════════════════════════════════════════════════════
    ui.label("今日待办").classes("text-h6 px-4 pt-2")
    _today_todo_list(today)

    ui.separator()

    # ══════════════════════════════════════════════════════════
    # 底部区域：快速入口按钮
    # ══════════════════════════════════════════════════════════
    def _on_todo_done():
        """新建/编辑待办后的回调：刷新列表"""
        _today_todo_list.refresh()

    ui.label("快速入口").classes("text-h6 px-4 pt-2")

    with ui.row().classes("px-4 pb-4 gap-3 flex-wrap"):
        ui.button("记账", on_click=lambda: ui.navigate.to("/finance")).classes("text-lg")
        ui.button("新建待办", on_click=lambda: _show_todo_dialog(None, _on_todo_done)).classes("text-lg")
        ui.button("写日记", on_click=lambda: ui.navigate.to("/diary")).classes("text-lg")
        ui.button("归类Rnote", on_click=lambda: ui.navigate.to("/rnote")).classes("text-lg")


# ══════════════════════════════════════════════════════════════════
# 辅助组件
# ══════════════════════════════════════════════════════════════════

def _render_todo_item(todo: Todo):
    """渲染单条待办：复选框 + 标题 + 优先级标签"""

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

        ui.button(
            "✏️",
            on_click=lambda t=todo: _show_todo_dialog(t, _today_todo_list.refresh),
        ).props("flat dense size=sm")

        if todo.due_date:
            ui.label(f"📅 {todo.due_date}").classes("text-caption text-grey-6")
