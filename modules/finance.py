"""
记账独立页面（升级版）
路由：/finance
功能：月度消费洞察面板 + 收支折线图 + 可增删改的数据表格

新增模块（月度消费洞察）：
  · KPI 卡片：总收入 / 总支出 / 结余 / 支出环比增长率
  · 分类占比环形图（ui.echart donut）
  · 备注高频关键词标签云
"""

import calendar
import re
from collections import Counter
from datetime import date, datetime

from nicegui import ui

from core.database import SessionLocal, Transaction
from modules.layout import add_header

# ── ECharts 配色 ─────────────────────────────────────────────────
COLOR_INCOME = "#22c55e"
COLOR_EXPENSE = "#ef4444"


# ══════════════════════════════════════════════════════════════════
# 数据查询
# ══════════════════════════════════════════════════════════════════

def _query_month_txns(year: int, month: int):
    """查询指定月份的所有交易"""
    start = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end = date(year, month, last_day)
    db = SessionLocal()
    try:
        return (
            db.query(Transaction)
            .filter(Transaction.date >= start, Transaction.date <= end)
            .order_by(Transaction.date.asc(), Transaction.created_at.asc())
            .all()
        )
    finally:
        db.close()


def _query_expense_categories(year: int, month: int) -> list[tuple[str, float]]:
    """查询当月支出按分类汇总，按金额降序"""
    start = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end = date(year, month, last_day)
    db = SessionLocal()
    try:
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.type == "expense",
            )
            .all()
        )
    finally:
        db.close()

    totals: dict[str, float] = {}
    for t in txns:
        cat = t.category or "未分类"
        totals[cat] = totals.get(cat, 0) + t.amount
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)


def _query_total_expense(year: int, month: int) -> float:
    """查询某月总支出"""
    start = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end = date(year, month, last_day)
    db = SessionLocal()
    try:
        return (
            db.query(Transaction)
            .filter(
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.type == "expense",
            )
            .with_entities(Transaction.amount)
            .all()
        )
    finally:
        db.close()


def _build_chart_data(txns, year: int, month: int):
    """交易列表 → ECharts 折线图数据"""
    _, last_day = calendar.monthrange(year, month)
    income_by_day = {d: 0.0 for d in range(1, last_day + 1)}
    expense_by_day = {d: 0.0 for d in range(1, last_day + 1)}
    for txn in txns:
        day = txn.date.day
        if txn.type == "income":
            income_by_day[day] += txn.amount
        else:
            expense_by_day[day] += txn.amount
    days = [str(d) for d in range(1, last_day + 1)]
    income_data = [round(income_by_day[d], 2) for d in range(1, last_day + 1)]
    expense_data = [round(expense_by_day[d], 2) for d in range(1, last_day + 1)]
    return days, income_data, expense_data


def _extract_keywords(txns, top_n: int = 16) -> list[tuple[str, int]]:
    """从交易备注中提取高频中文词汇，用于标签云"""
    stop_words = {
        "的", "了", "在", "是", "和", "就", "不", "都", "一", "也", "很",
        "到", "要", "去", "会", "着", "没有", "看", "好", "自己", "这", "那",
        "用", "给", "从", "与", "或", "及", "元", "块", "钱", "个", "可",
        "以", "为", "被", "但", "而", "等", "等等", "什么", "怎么", "购买",
    }
    words: list[str] = []
    for txn in txns:
        if txn.note:
            # 提取中文词组（连续汉字）
            chinese = re.findall(r"[一-鿿]+", txn.note)
            for phrase in chinese:
                if len(phrase) >= 2 and phrase not in stop_words:
                    words.append(phrase)
    return Counter(words).most_common(top_n)


def _calc_mom_growth(year: int, month: int) -> float | None:
    """计算支出环比上月增长率，None 表示上月无数据"""
    # 上月
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    current = sum(r[0] for r in _query_total_expense(year, month))
    prev = sum(r[0] for r in _query_total_expense(prev_year, prev_month))

    if prev == 0:
        return None
    return round((current - prev) / prev * 100, 1)


# ══════════════════════════════════════════════════════════════════
# 编辑对话框（模块级，保持原有增删改查功能不变）
# ══════════════════════════════════════════════════════════════════

def _show_txn_dialog(txn, on_done):
    """编辑 / 新增记账对话框"""
    is_new = txn is None

    with ui.dialog() as dlg:
        with ui.card().style("width: 450px; max-width: 90vw;"):
            ui.label("➕ 新增记账" if is_new else "✏️ 编辑记账").classes("text-h6 font-bold pb-2")

            txn_type = ui.select(
                label="类型", options=["expense", "income"],
                value="expense" if is_new else txn.type,
            )
            if is_new:
                ui.label("📅 日期").classes("text-caption text-grey-6")
                txn_date = ui.date(value=date.today())
            else:
                ui.label(f"日期：{txn.date}").classes("text-caption")

            category = ui.input(
                label="分类", placeholder="餐饮/购物/工资...",
                value="" if is_new else txn.category,
            ).classes("w-full")
            amount = ui.number(
                label="金额", format="%.2f", min=0,
                value=0.0 if is_new else txn.amount,
            ).classes("w-full")
            note = ui.input(
                label="备注（可选）", value="" if is_new else (txn.note or ""),
            ).classes("w-full")

            def _save():
                s = SessionLocal()
                try:
                    if is_new:
                        raw = txn_date.value
                        if isinstance(raw, str):
                            parts = raw.split("-")
                            d = date(int(parts[0]), int(parts[1]), int(parts[2]))
                        else:
                            d = raw
                        s.add(Transaction(
                            date=d, type=txn_type.value,
                            category=category.value, amount=amount.value,
                            note=note.value or "",
                        ))
                    else:
                        r = s.query(Transaction).filter(Transaction.id == txn.id).first()
                        if r:
                            r.type = txn_type.value
                            r.category = category.value
                            r.amount = amount.value
                            r.note = note.value or ""
                    s.commit()
                finally:
                    s.close()
                dlg.close()
                on_done()

            def _delete():
                if is_new:
                    dlg.close()
                    return
                s = SessionLocal()
                try:
                    r = s.query(Transaction).filter(Transaction.id == txn.id).first()
                    if r:
                        s.delete(r)
                        s.commit()
                finally:
                    s.close()
                dlg.close()
                on_done()

            with ui.row().classes("gap-2 justify-between w-full pt-2"):
                if not is_new:
                    ui.button("🗑 删除", on_click=_delete).props("flat color=negative")
                else:
                    ui.element("div")
                with ui.row().classes("gap-2"):
                    ui.button("取消", on_click=dlg.close).props("flat")
                    ui.button("保存", on_click=_save).props("color=primary")
    dlg.open()


# ══════════════════════════════════════════════════════════════════
# 页面入口
# ══════════════════════════════════════════════════════════════════

@ui.page("/finance")
def finance_page():
    """记账独立页面（含月度消费洞察面板）"""

    add_header()

    today = date.today()
    view = {"year": today.year, "month": today.month}

    # ── 面包屑 ──────────────────────────────────────────────
    with ui.row().classes("items-center gap-4 px-3 pt-2 pb-1"):
        ui.link("🏠 首页", target="/").classes("text-grey-6 no-underline")
        ui.label("›").classes("text-grey-6")
        ui.label("💰 记账管理").classes("text-h6 font-bold")

    ui.separator()

    # ── 月份选择器 + 新增按钮 ──────────────────────────────
    with ui.row().classes("items-center gap-3 px-3 pb-2"):

        def _go_prev():
            if view["month"] == 1:
                view["year"] -= 1
                view["month"] = 12
            else:
                view["month"] -= 1
            month_label.set_text(f"{view['year']} 年 {view['month']:02d} 月")
            _refresh_all()

        def _go_next():
            if view["month"] == 12:
                view["year"] += 1
                view["month"] = 1
            else:
                view["month"] += 1
            month_label.set_text(f"{view['year']} 年 {view['month']:02d} 月")
            _refresh_all()

        ui.button("◀", on_click=_go_prev).props("flat dense round")
        month_label = ui.label(
            f"{view['year']} 年 {view['month']:02d} 月"
        ).classes("text-h5 font-bold")
        ui.button("▶", on_click=_go_next).props("flat dense round")
        ui.space()
        ui.button(
            "➕ 新增记账",
            on_click=lambda: _show_txn_dialog(None, _refresh_all),
        ).props("color=primary")

    # ── 容器 ────────────────────────────────────────────────
    kpi_container = ui.row().classes("gap-3 px-3 pb-3 w-full")
    insights_container = ui.row().classes("gap-3 px-3 pb-3 w-full")
    chart_container = ui.element("div").classes("w-full px-3")
    table_container = ui.column().classes("w-full px-3 pb-4")

    # ══════════════════════════════════════════════════════════
    # _refresh_all：刷新全部面板
    # ══════════════════════════════════════════════════════════
    def _refresh_all():
        txns = _query_month_txns(view["year"], view["month"])
        income_total = sum(t.amount for t in txns if t.type == "income")
        expense_total = sum(t.amount for t in txns if t.type == "expense")
        balance = income_total - expense_total
        mom_growth = _calc_mom_growth(view["year"], view["month"])

        # ── KPI 卡片 ────────────────────────────────────────
        kpi_container.clear()
        with kpi_container:
            # 总收入
            with ui.card().classes("flex-1"):
                ui.label(f"¥{income_total:,.2f}").classes("text-h4 font-bold text-green-6")
                ui.label("📈 总收入").classes("text-caption text-grey-6")

            # 总支出
            with ui.card().classes("flex-1"):
                ui.label(f"¥{expense_total:,.2f}").classes("text-h4 font-bold text-red-6")
                ui.label("📉 总支出").classes("text-caption text-grey-6")

            # 结余
            with ui.card().classes("flex-1"):
                bc = "text-green-6" if balance >= 0 else "text-red-6"
                ui.label(f"¥{balance:,.2f}").classes(f"text-h4 font-bold {bc}")
                ui.label("💰 结余").classes("text-caption text-grey-6")

            # 环比增长
            with ui.card().classes("flex-1"):
                if mom_growth is None:
                    ui.label("--").classes("text-h4 font-bold text-grey-6")
                    ui.label("📊 环比（上月无数据）").classes("text-caption text-grey-6")
                else:
                    arrow = "↑" if mom_growth > 0 else "↓" if mom_growth < 0 else "→"
                    gc = "text-red-6" if mom_growth > 0 else "text-green-6" if mom_growth < 0 else "text-grey-6"
                    ui.label(f"{arrow} {abs(mom_growth)}%").classes(f"text-h4 font-bold {gc}")
                    ui.label("📊 支出环比上月").classes("text-caption text-grey-6")

        # ── 消费洞察面板（环形图 + 标签云）──────────────────
        insights_container.clear()
        with insights_container:
            # 左侧：分类占比环形图
            with ui.card().classes("flex-1"):
                ui.label("🍩 支出分类占比").classes("text-h6 font-bold pb-2")
                categories = _query_expense_categories(view["year"], view["month"])
                _render_donut_chart(categories)

            # 右侧：备注关键词标签云
            with ui.card().classes("flex-1"):
                ui.label("🏷 备注高频词").classes("text-h6 font-bold pb-2")
                keywords = _extract_keywords(txns)
                _render_tag_cloud(keywords)

        # ── 收支折线图 ──────────────────────────────────────
        chart_container.clear()
        days, income_data, expense_data = _build_chart_data(
            txns, view["year"], view["month"]
        )
        with chart_container:
            if any(v > 0 for v in income_data + expense_data):
                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "legend": {"data": ["收入", "支出"], "bottom": 0},
                    "grid": {"left": 50, "right": 20, "top": 20, "bottom": 30},
                    "xAxis": {"type": "category", "data": days, "name": "日"},
                    "yAxis": {"type": "value", "name": "金额 (¥)"},
                    "series": [
                        {
                            "name": "收入", "type": "line", "data": income_data,
                            "smooth": True,
                            "lineStyle": {"color": COLOR_INCOME, "width": 2},
                            "itemStyle": {"color": COLOR_INCOME},
                            "areaStyle": {"color": {
                                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                "colorStops": [
                                    {"offset": 0, "color": "rgba(34,197,94,0.3)"},
                                    {"offset": 1, "color": "rgba(34,197,94,0.02)"},
                                ],
                            }},
                        },
                        {
                            "name": "支出", "type": "line", "data": expense_data,
                            "smooth": True,
                            "lineStyle": {"color": COLOR_EXPENSE, "width": 2},
                            "itemStyle": {"color": COLOR_EXPENSE},
                            "areaStyle": {"color": {
                                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                "colorStops": [
                                    {"offset": 0, "color": "rgba(239,68,68,0.3)"},
                                    {"offset": 1, "color": "rgba(239,68,68,0.02)"},
                                ],
                            }},
                        },
                    ],
                }).classes("w-full").style("height: 280px")
            else:
                ui.label("📭 本月暂无收支数据").classes("text-grey-6 p-4")

        # ── 数据表格 ────────────────────────────────────────
        table_container.clear()
        with table_container:
            if not txns:
                ui.label("📭 本月暂无记账记录").classes("text-grey-6 p-4")
            else:
                ui.label(f"共 {len(txns)} 条记录").classes("text-caption text-grey-6 pb-1")
                with ui.row().classes(
                    "items-center gap-2 py-2 px-3 bg-grey-2 rounded text-caption font-bold"
                ):
                    ui.label("日期").classes("w-28")
                    ui.label("类型").classes("w-16")
                    ui.label("分类").classes("flex-1")
                    ui.label("金额").classes("w-24 text-right")
                    ui.label("备注").classes("w-32")
                    ui.label("操作").classes("w-16")

                for txn in txns:
                    type_label = "📈 收入" if txn.type == "income" else "📉 支出"
                    amt_str = (
                        f"+¥{txn.amount:.2f}" if txn.type == "income"
                        else f"-¥{txn.amount:.2f}"
                    )
                    amt_color = "text-green-6" if txn.type == "income" else "text-red-6"

                    with ui.row().classes(
                        "items-center gap-2 py-1 px-3 border-b border-grey-2 text-sm"
                    ):
                        ui.label(str(txn.date)).classes("w-28")
                        ui.label(type_label).classes("w-16")
                        ui.label(txn.category).classes("flex-1")
                        ui.label(amt_str).classes(f"w-24 text-right font-bold {amt_color}")
                        ui.label(txn.note or "-").classes("w-32 text-grey-6")
                        ui.button(
                            "✏️",
                            on_click=lambda tx=txn: _show_txn_dialog(tx, _refresh_all),
                        ).props("flat dense size=sm")

    # ── 首次加载 ─────────────────────────────────────────────
    _refresh_all()


# ══════════════════════════════════════════════════════════════════
# 子组件渲染
# ══════════════════════════════════════════════════════════════════

# 环形图配色
DONUT_COLORS = [
    "#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f43f5e", "#6366f1",
]


def _render_donut_chart(categories: list[tuple[str, float]]):
    """渲染分类占比环形图（Top 5 + 其他）"""
    if not categories:
        ui.label("本月无支出记录").classes("text-grey-6 p-4 text-center")
        return

    # Top 5
    top5 = categories[:5]
    other_sum = sum(v for _, v in categories[5:])

    pie_data = [{"name": name, "value": round(val, 2)} for name, val in top5]
    if other_sum > 0:
        pie_data.append({"name": "其他", "value": round(other_sum, 2)})

    ui.echart({
        "tooltip": {"trigger": "item", "formatter": "{b}: ¥{c} ({d}%)"},
        "legend": {"bottom": 0, "textStyle": {"fontSize": 11}},
        "series": [{
            "type": "pie",
            "radius": ["45%", "75%"],
            "center": ["50%", "45%"],
            "avoidLabelOverlap": False,
            "itemStyle": {"borderRadius": 4, "borderColor": "#fff", "borderWidth": 2},
            "label": {"show": False},
            "emphasis": {
                "label": {"show": True, "fontSize": 14, "fontWeight": "bold"},
            },
            "data": pie_data,
            "color": DONUT_COLORS,
        }],
    }).classes("w-full").style("height: 240px")


def _render_tag_cloud(keywords: list[tuple[str, int]]):
    """渲染备注高频关键词标签云"""
    if not keywords:
        ui.label("本月暂无备注关键词").classes("text-grey-6 p-4 text-center")
        return

    # 字号映射：最小 12px，最大 28px
    max_count = keywords[0][1] if keywords else 1
    min_count = keywords[-1][1] if keywords else 1

    def _font_size(count: int) -> str:
        if max_count == min_count:
            return "16px"
        ratio = (count - min_count) / (max_count - min_count)
        px = 12 + int(ratio * 16)  # 12 → 28 px
        return f"{px}px"

    # 颜色池
    bg_colors = [
        "bg-red-50 text-red-6", "bg-orange-50 text-orange-6",
        "bg-amber-50 text-amber-6", "bg-green-50 text-green-6",
        "bg-blue-50 text-blue-6", "bg-purple-50 text-purple-6",
        "bg-pink-50 text-pink-6", "bg-teal-50 text-teal-6",
        "bg-indigo-50 text-indigo-6", "bg-cyan-50 text-cyan-6",
    ]

    with ui.element("div").classes("flex flex-wrap gap-2 items-center p-2"):
        for i, (word, count) in enumerate(keywords):
            color_cls = bg_colors[i % len(bg_colors)]
            size = _font_size(count)
            ui.label(f"#{word}").classes(
                f"px-3 py-1 rounded-full {color_cls}"
            ).style(f"font-size:{size};")
