"""
融合日历与日程 —— Calendar Feed
路由：/calendar
设计：C 类 — 左侧月历 (35%) + 右侧 Feed 时间线 (65%)（见 CLAUDE.me §3.2）

日历圆点规则：
  蓝色  = 当天有待办或记账（无日记）
  绿色  = 当天仅有日记（无待办/记账）
  紫色  = 当天既有日记又有待办/记账
  无点  = 当天无任何记录

Feed 展示顺序：① 日记预览 → ② 待办清单 → ③ 记账流水（含收支汇总）
"""

import calendar
from datetime import date, timedelta

from nicegui import ui

from core.database import Diary, SessionLocal, Todo, Transaction
from modules.layout import add_header

# ── 心情映射 ────────────────────────────────────────────────────
MOOD_ICONS = {"happy": "😊", "sad": "😢", "neutral": "😐"}
MOOD_LABELS = {"happy": "开心", "sad": "难过", "neutral": "平静"}


# ══════════════════════════════════════════════════════════════════
# 数据库查询工具
# ══════════════════════════════════════════════════════════════════

def _query_month_data(year: int, month: int):
    """
    查询指定月份所有有数据的日期，按类型返回三个 set[date]。
    返回: (diary_dates, todo_dates, txn_dates)
    """
    start = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end = date(year, month, last_day)

    db = SessionLocal()
    try:
        diaries = {
            r[0]
            for r in db.query(Diary.date)
            .filter(Diary.date >= start, Diary.date <= end)
            .all()
        }
        todos = {
            r[0]
            for r in db.query(Todo.due_date)
            .filter(Todo.due_date >= start, Todo.due_date <= end)
            .all()
        }
        txns = {
            r[0]
            for r in db.query(Transaction.date)
            .filter(Transaction.date >= start, Transaction.date <= end)
            .all()
        }
    finally:
        db.close()

    return diaries, todos, txns


def _dot_color(day_date: date, diaries: set, todos: set, txns: set) -> str | None:
    """判断某天的圆点颜色。None=无标记"""
    has_diary = day_date in diaries
    has_event = day_date in todos or day_date in txns
    if has_diary and has_event:
        return "#a855f7"  # purple
    elif has_diary:
        return "#22c55e"  # green
    elif has_event:
        return "#3b82f6"  # blue
    return None


# ══════════════════════════════════════════════════════════════════
# 页面级状态（单用户本地应用，模块级变量足够）
# ══════════════════════════════════════════════════════════════════

_today = date.today()
_selected_date = _today          # 当前选中日期
_view_year = _today.year         # 月历展示年
_view_month = _today.month       # 月历展示月


# ══════════════════════════════════════════════════════════════════
# 右侧 Feed：按日期展示 日记 → 待办 → 记账
# ══════════════════════════════════════════════════════════════════

@ui.refreshable
def day_feed(selected_date: date):
    """根据选中日期刷新右侧 Feed 面板"""

    db = SessionLocal()
    try:
        diary = db.query(Diary).filter(Diary.date == selected_date).first()
        todos = (
            db.query(Todo)
            .filter(Todo.due_date == selected_date)
            .order_by(Todo.priority.asc())
            .all()
        )
        txns = (
            db.query(Transaction)
            .filter(Transaction.date == selected_date)
            .order_by(Transaction.created_at.asc())
            .all()
        )
    finally:
        db.close()

    # 日期标题
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    wd = weekdays[selected_date.weekday()]
    ui.label(
        f"📅 {selected_date.year}年{selected_date.month:02d}月{selected_date.day:02d}日 星期{wd}"
    ).classes("text-h6 font-bold pb-2")

    has_any = diary or todos or txns
    if not has_any:
        with ui.card().classes("w-full p-6 text-center"):
            ui.label("📭 这一天暂无记录").classes("text-grey-6 text-lg")
        return

    # ── ① 日记预览 ──────────────────────────────────────────
    if diary:
        with ui.card().classes("w-full mb-3"):
            with ui.row().classes("items-center justify-between"):
                mood_icon = MOOD_ICONS.get(diary.mood, "😐")
                mood_label = MOOD_LABELS.get(diary.mood, "未知")
                ui.label(f"📖 日记 · {mood_icon} {mood_label}").classes("text-h6 font-bold")
                ui.button("✏️ 编辑", on_click=lambda d=diary: _edit_diary(d)).props("flat dense")

            preview = diary.content[:200] + ("..." if len(diary.content) > 200 else "")
            ui.label(preview or "（空内容）").classes("text-grey-7 whitespace-pre-wrap pl-2")
            if diary.weather_override:
                ui.label(f"🌤 天气：{diary.weather_override}").classes("text-caption text-grey-6 pl-2")

    # ── ② 待办清单 ──────────────────────────────────────────
    if todos:
        with ui.card().classes("w-full mb-3"):
            ui.label("✅ 待办事项").classes("text-h6 font-bold pb-1")
            for todo in todos:
                with ui.row().classes("items-center gap-2 py-1"):
                    priority_icon = {1: "🔴", 2: "🟡", 3: "🟢"}.get(todo.priority, "🟡")

                    def _make_on_check(t=todo):
                        def _on_check(e):
                            s = SessionLocal()
                            try:
                                r = s.query(Todo).filter(Todo.id == t.id).first()
                                if r:
                                    r.is_completed = e.value
                                    s.commit()
                            finally:
                                s.close()
                        return _on_check

                    ui.checkbox(
                        text=f"{priority_icon} {todo.title}",
                        value=todo.is_completed,
                        on_change=_make_on_check(),
                    )
                    ui.button("✏️", on_click=lambda t=todo: _edit_todo(t)).props("flat dense size=sm")

                if todo.description:
                    ui.label(f"    {todo.description}").classes("text-caption text-grey-6 pl-8")

    # ── ③ 记账流水 ──────────────────────────────────────────
    if txns:
        income_total = sum(t.amount for t in txns if t.type == "income")
        expense_total = sum(t.amount for t in txns if t.type == "expense")

        with ui.card().classes("w-full mb-3"):
            ui.label("💰 记账流水").classes("text-h6 font-bold pb-1")

            with ui.row().classes("gap-4 pb-2"):
                ui.label(f"📈 收入：¥{income_total:.2f}").classes("text-green-6 font-bold")
                ui.label(f"📉 支出：¥{expense_total:.2f}").classes("text-red-6 font-bold")
                balance = income_total - expense_total
                bc = "text-green-6" if balance >= 0 else "text-red-6"
                ui.label(f"💰 结余：¥{balance:.2f}").classes(f"{bc} font-bold")

            ui.separator()

            for txn in txns:
                icon = "📈" if txn.type == "income" else "📉"
                amt = f"+¥{txn.amount:.2f}" if txn.type == "income" else f"-¥{txn.amount:.2f}"
                ac = "text-green-6" if txn.type == "income" else "text-red-6"

                with ui.row().classes("items-center gap-2 py-1"):
                    ui.label(f"{icon} {txn.category}").classes("font-medium")
                    ui.label(amt).classes(f"{ac} font-bold")
                    if txn.note:
                        ui.label(f"({txn.note})").classes("text-caption text-grey-6")
                    ui.button("✏️", on_click=lambda tx=txn: _edit_txn(tx)).props("flat dense size=sm")


# ══════════════════════════════════════════════════════════════════
# 编辑对话框
# ══════════════════════════════════════════════════════════════════

def _edit_diary(diary: Diary):
    """日记编辑对话框"""
    with ui.dialog() as dlg, ui.card().classes("w-[500px]"):
        ui.label(f"📖 编辑日记 —— {diary.date}").classes("text-h6 font-bold pb-2")
        content = ui.textarea(label="Markdown 正文", value=diary.content or "").classes("w-full").props("rows=6")
        mood = ui.select(label="心情", options=["happy", "sad", "neutral"], value=diary.mood or "neutral")
        weather = ui.input(label="天气（可选）", value=diary.weather_override or "")

        async def _save():
            s = SessionLocal()
            try:
                r = s.query(Diary).filter(Diary.id == diary.id).first()
                if r:
                    r.content = content.value
                    r.mood = mood.value
                    r.weather_override = weather.value or None
                    s.commit()
            finally:
                s.close()
            dlg.close()
            day_feed.refresh()
            ui.notify("日记已保存 ✅")

        with ui.row().classes("gap-2 justify-end w-full pt-2"):
            ui.button("取消", on_click=dlg.close).props("flat")
            ui.button("保存", on_click=_save).props("color=primary")
    dlg.open()


def _edit_todo(todo: Todo):
    """待办编辑对话框"""
    with ui.dialog() as dlg, ui.card().classes("w-[450px]"):
        ui.label("✅ 编辑待办").classes("text-h6 font-bold pb-2")
        title = ui.input(label="标题", value=todo.title).classes("w-full")
        desc = ui.textarea(label="描述", value=todo.description or "").classes("w-full").props("rows=3")
        with ui.row().classes("gap-4"):
            priority = ui.select(label="优先级", options={1: "🔴 高", 2: "🟡 中", 3: "🟢 低"}, value=todo.priority)
            completed = ui.checkbox("已完成", value=todo.is_completed)

        async def _save():
            s = SessionLocal()
            try:
                r = s.query(Todo).filter(Todo.id == todo.id).first()
                if r:
                    r.title = title.value
                    r.description = desc.value
                    r.priority = priority.value
                    r.is_completed = completed.value
                    s.commit()
            finally:
                s.close()
            dlg.close()
            day_feed.refresh()
            ui.notify("待办已保存 ✅")

        with ui.row().classes("gap-2 justify-end w-full pt-2"):
            ui.button("取消", on_click=dlg.close).props("flat")
            ui.button("保存", on_click=_save).props("color=primary")
    dlg.open()


def _edit_txn(txn: Transaction):
    """记账编辑对话框"""
    with ui.dialog() as dlg, ui.card().classes("w-[450px]"):
        ui.label("💰 编辑记账").classes("text-h6 font-bold pb-2")
        txn_type = ui.select(label="类型", options=["income", "expense"], value=txn.type)
        category = ui.input(label="分类", value=txn.category).classes("w-full")
        amount = ui.number(label="金额", value=txn.amount, format="%.2f").classes("w-full")
        note = ui.input(label="备注", value=txn.note or "").classes("w-full")

        async def _save():
            s = SessionLocal()
            try:
                r = s.query(Transaction).filter(Transaction.id == txn.id).first()
                if r:
                    r.type = txn_type.value
                    r.category = category.value
                    r.amount = amount.value
                    r.note = note.value
                    s.commit()
            finally:
                s.close()
            dlg.close()
            day_feed.refresh()
            ui.notify("记账已保存 ✅")

        with ui.row().classes("gap-2 justify-end w-full pt-2"):
            ui.button("取消", on_click=dlg.close).props("flat")
            ui.button("保存", on_click=_save).props("color=primary")
    dlg.open()


# ══════════════════════════════════════════════════════════════════
# 左侧月历渲染
# ══════════════════════════════════════════════════════════════════

@ui.refreshable
def _render_calendar():
    """渲染月历网格（模块级 refreshable）"""
    global _view_year, _view_month, _selected_date

    year, month = _view_year, _view_month
    diaries, todos, txns = _query_month_data(year, month)

    # ── 月份切换条 ──────────────────────────────────────────
    with ui.row().classes("items-center justify-between w-full pb-2"):
        ui.button("◀", on_click=_go_prev).props("flat dense round")
        ui.label(f"{year} 年 {month:02d} 月").classes("text-h6 font-bold")
        ui.button("▶", on_click=_go_next).props("flat dense round")

    # ── 星期头 ──────────────────────────────────────────────
    with ui.row().classes("w-full"):
        for w in ["一", "二", "三", "四", "五", "六", "日"]:
            ui.label(w).classes("flex-1 text-center text-caption font-bold text-grey-6 py-1")

    # ── 计算格子列表 ────────────────────────────────────────
    _, last_day = calendar.monthrange(year, month)
    first_weekday = date(year, month, 1).weekday()  # 0=Mon

    cells = []
    if first_weekday > 0:
        prev_last = date(year, month, 1) - timedelta(days=1)
        for i in range(first_weekday):
            cells.append(("prev", prev_last - timedelta(days=first_weekday - 1 - i)))
    for d in range(1, last_day + 1):
        cells.append(("current", date(year, month, d)))
    rem = (7 - len(cells) % 7) % 7
    for d in range(1, rem + 1):
        cells.append(("next", date(year, month + 1 if month < 12 else 1, d)))

    # ── 按行渲染日期格子 ────────────────────────────────────
    for row_start in range(0, len(cells), 7):
        with ui.row().classes("w-full gap-[2px]"):
            for i in range(7):
                if row_start + i >= len(cells):
                    break
                kind, day_date = cells[row_start + i]
                _render_day_cell(kind, day_date, diaries, todos, txns)


def _go_prev():
    """切换到上一个月"""
    global _view_year, _view_month, _selected_date
    if _view_month == 1:
        _view_year -= 1
        _view_month = 12
    else:
        _view_month -= 1
    _selected_date = date(_view_year, _view_month, 1)
    _render_calendar.refresh()
    day_feed.refresh(_selected_date)


def _go_next():
    """切换到下一个月"""
    global _view_year, _view_month, _selected_date
    if _view_month == 12:
        _view_year += 1
        _view_month = 1
    else:
        _view_month += 1
    _selected_date = date(_view_year, _view_month, 1)
    _render_calendar.refresh()
    day_feed.refresh(_selected_date)


def _on_day_click(day_date: date):
    """点击日期格子 → 更新选中 → 刷新日历和 Feed"""
    global _selected_date
    _selected_date = day_date
    _render_calendar.refresh()
    day_feed.refresh(day_date)


def _render_day_cell(kind: str, day_date: date, diaries: set, todos: set, txns: set):
    """渲染单个日期格子：ui.button 做可点击单元格"""

    dot_c = _dot_color(day_date, diaries, todos, txns)
    is_today = day_date == _today
    is_selected = day_date == _selected_date
    is_other = kind in ("prev", "next")

    # 组装 Quasar button 属性
    props = ["flat", "dense", "square", "no-caps"]
    classes = ["flex-1"]

    if is_selected:
        # 选中日：蓝色边框 + 浅蓝底
        classes.append("bg-blue-100")
        style = "border: 2px solid #3b82f6; min-width: 0; min-height: 44px; position: relative;"
    elif is_today:
        # 今天：琥珀色底
        classes.append("bg-amber-50")
        style = "border: 1px solid #fcd34d; min-width: 0; min-height: 44px; position: relative;"
    else:
        # 普通日
        style = "border: 1px solid #e5e7eb; min-width: 0; min-height: 44px; position: relative;"

    if is_other:
        classes.append("text-grey-400")

    # 数字文本（用 ui.button 的 label 直接显示）
    label = str(day_date.day)
    if is_today:
        label = f"**{label}**"  # Quasar 不支持 markdown，用 html

    btn = ui.button().props(" ".join(props)).classes(" ".join(classes)).style(style)

    # 把数字和圆点放入 button 内部
    with btn:
        with ui.column().classes("items-center justify-center w-full h-full relative"):
            # 日期数字
            num_style = ""
            if is_today:
                num_style = "font-weight: bold;"
            if is_other:
                num_style += " color: #9ca3af;"
            ui.label(str(day_date.day)).style(num_style + "font-size: 14px; line-height: 1;")

            # 圆点标记
            if dot_c:
                ui.element("div").style(
                    f"width:6px;height:6px;border-radius:50%;background-color:{dot_c};"
                    "position:absolute;bottom:2px;right:4px;"
                )

    # 点击事件
    btn.on("click", lambda _, d=day_date: _on_day_click(d))

    # 禁用非当月日期
    if is_other:
        btn.props("disable")


# ══════════════════════════════════════════════════════════════════
# 页面入口：/calendar
# ══════════════════════════════════════════════════════════════════

@ui.page("/calendar")
def calendar_page():
    """融合日历与日程页面"""

    add_header()

    # 重置为真实今天（每次进入页面时）
    global _today, _selected_date, _view_year, _view_month
    _today = date.today()
    if _selected_date is None:
        _selected_date = _today
        _view_year = _today.year
        _view_month = _today.month

    # ── 顶部导航栏（返回首页）─────────────────────────────────
    with ui.row().classes("items-center gap-4 px-3 pt-2 pb-1"):
        ui.link("🏠 首页", target="/").classes("text-grey-6 no-underline")
        ui.label("›").classes("text-grey-6")
        ui.label("📅 日历日程").classes("text-h6 font-bold")

    ui.separator()

    # ── 左右分栏 ─────────────────────────────────────────────
    with ui.row().classes("w-full gap-0"):
        with ui.column().classes("w-[35%] p-3"):
            _render_calendar()
        with ui.column().classes("w-[65%] p-3"):
            day_feed(_selected_date)
