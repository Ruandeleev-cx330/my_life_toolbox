"""
日记独立编辑器
路由：/diary
功能：按日期存取 Markdown 日记，支持实时预览和心情标记
"""

from datetime import date, timedelta

from nicegui import ui

from core.database import Diary, SessionLocal
from modules.layout import add_header

MOOD_OPTIONS = {"😊 开心": "happy", "😢 难过": "sad", "😐 平静": "neutral"}


# ══════════════════════════════════════════════════════════════════
# 页面入口
# ══════════════════════════════════════════════════════════════════

@ui.page("/diary")
def diary_page():
    """日记编辑页面"""

    add_header()

    today = date.today()
    selected = {"date": today}

    # ── 面包屑 ──────────────────────────────────────────────
    with ui.row().classes("items-center gap-4 px-3 pt-2 pb-1"):
        ui.link("🏠 首页", target="/").classes("text-grey-6 no-underline")
        ui.label("›").classes("text-grey-6")
        ui.label("📖 写日记").classes("text-h6 font-bold")

    ui.separator()

    # ── 容器 ────────────────────────────────────────────────
    date_info_container = ui.column().classes("gap-1 pt-4")
    action_row = ui.row().classes("items-center gap-3 w-full")
    editor_area = ui.column().classes("w-full gap-2")
    preview_container = ui.column().classes("w-full")

    # 保存对当前 editor_textarea 的引用（供事件回调读取值）
    state = {"editor": None, "mood": None, "weather": None}

    # ══════════════════════════════════════════════════════════
    # 所有函数定义（在 UI 之前，避免闭包时序问题）
    # ══════════════════════════════════════════════════════════

    def _load_diary(d: date):
        db = SessionLocal()
        try:
            return db.query(Diary).filter(Diary.date == d).first()
        finally:
            db.close()

    def _render_preview():
        """用当前 editor 的值刷新 Markdown 预览"""
        preview_container.clear()
        editor = state.get("editor")
        content = editor.value if editor else ""
        with preview_container:
            if content and content.strip():
                ui.markdown(content).classes("p-3 border rounded bg-white w-full").style(
                    "min-height: 120px;"
                )
            else:
                with ui.card().classes("w-full p-4 bg-grey-50"):
                    ui.label("（输入 Markdown 内容后此处自动预览）").classes("text-grey-6")

    def _refresh_all():
        """加载 selected["date"] 的日记并刷新全部 UI"""
        diary = _load_diary(selected["date"])

        # ── 刷新日期信息 ──
        date_info_container.clear()
        with date_info_container:
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            wd = weekdays[selected["date"].weekday()]
            ui.label(
                f"{selected['date'].year}年{selected['date'].month:02d}月{selected['date'].day:02d}日"
            ).classes("font-bold")
            ui.label(f"星期{wd}").classes("text-caption text-grey-6")
            if selected["date"] == today:
                ui.label("📍 今天").classes("text-caption text-blue-6")
            if diary and diary.updated_at:
                ui.label(
                    f"更新于 {diary.updated_at.strftime('%m-%d %H:%M')}"
                ).classes("text-caption text-grey-6 pt-2")

        # ── 刷新编辑器 ──
        editor_area.clear()
        with editor_area:
            editor_textarea = (
                ui.textarea(
                    label="Markdown 正文",
                    value=diary.content if diary else "",
                )
                .classes("w-full")
                .style("min-height: 240px; font-family: monospace;")
            )
            state["editor"] = editor_textarea

            # 实时预览绑定
            editor_textarea.on("update:model-value", lambda: _render_preview())

            ui.label("📄 实时预览").classes("text-caption font-bold text-grey-6 pt-2")

        # ── 刷新操作栏 ──
        action_row.clear()
        with action_row:
            current_mood = diary.mood if diary else "neutral"
            current_mood_label = {v: k for k, v in MOOD_OPTIONS.items()}.get(
                current_mood, "😐 平静"
            )
            mood_select = ui.select(
                label="心情", options=list(MOOD_OPTIONS.keys()),
                value=current_mood_label,
            ).classes("w-36")

            weather_input = ui.input(
                label="天气", placeholder="晴/雨/阴...",
                value=diary.weather_override if diary else "",
            ).classes("w-32")

            ui.space()

            def _save():
                mood_val = MOOD_OPTIONS.get(mood_select.value, "neutral")
                s = SessionLocal()
                try:
                    existing = s.query(Diary).filter(
                        Diary.date == selected["date"]
                    ).first()
                    if existing:
                        existing.content = editor_textarea.value
                        existing.mood = mood_val
                        existing.weather_override = weather_input.value or None
                    else:
                        s.add(Diary(
                            date=selected["date"],
                            content=editor_textarea.value,
                            mood=mood_val,
                            weather_override=weather_input.value or None,
                        ))
                    s.commit()
                finally:
                    s.close()
                ui.notify("日记已保存 ✅")

            ui.button("💾 保存", on_click=_save).props("color=primary")

        # ── 刷新预览 ──
        _render_preview()

        # ── 更新日期选择器 ──
        date_picker.value = selected["date"].isoformat()

    def _on_picker_change(e):
        """日期选择器值变更 → 解析日期 → 刷新"""
        val = getattr(e, "value", None) or str(e)
        parts = str(val).split("-")
        if len(parts) == 3:
            selected["date"] = date(int(parts[0]), int(parts[1]), int(parts[2]))
            _refresh_all()

    def _go_day(delta: int):
        selected["date"] = selected["date"] + timedelta(days=delta)
        _refresh_all()

    def _go_today():
        selected["date"] = date.today()
        _refresh_all()

    # ══════════════════════════════════════════════════════════
    # UI 布局
    # ══════════════════════════════════════════════════════════
    with ui.row().classes("w-full gap-0 flex-wrap"):
        # ── 左侧：日期选择 ────────────────────────────────
        with ui.column().classes("p-3 gap-2").style("width: 220px; min-width: 200px;"):
            ui.label("📅 选择日期").classes("text-h6 font-bold pb-2")

            with ui.row().classes("gap-1 items-center"):
                ui.button("◀", on_click=lambda: _go_day(-1)).props("flat dense round")
                date_picker = ui.date(value=selected["date"], on_change=_on_picker_change)
                date_picker.style("width: 140px;")
                ui.button("▶", on_click=lambda: _go_day(1)).props("flat dense round")

            ui.button("📅 回到今天", on_click=_go_today).props("flat size=sm")

            date_info_container

        # ── 右侧：编辑器 + 预览 ──────────────────────────
        with ui.column().classes("flex-1 p-3 gap-2").style("min-width: 300px;"):
            action_row
            editor_area
            preview_container

    # ── 首次加载 ─────────────────────────────────────────────
    _refresh_all()
