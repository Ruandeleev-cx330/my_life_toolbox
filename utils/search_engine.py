"""
全局搜索引擎
跨表联合查询：记账 / 待办 / 日记 / Rnote 笔记
用法：
    from utils.search_engine import search_all
    results = search_all("火锅")
"""

from sqlalchemy import or_

from core.database import Diary, RnoteFile, SessionLocal, Todo, Transaction

# ── 每页最多返回条数 ────────────────────────────────────────────
MAX_PER_TABLE = 20


def _fmt_size(size_bytes: int) -> str:
    """字节 → 可读大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def search_all(query: str) -> list[dict]:
    """
    在全部四张表中模糊搜索关键词。
    返回统一格式的 dict 列表，按来源分组排序。
    """
    if not query or not query.strip():
        return []

    pattern = f"%{query.strip()}%"
    results = []

    db = SessionLocal()
    try:
        # ── 记账 ──────────────────────────────────────────
        txns = (
            db.query(Transaction)
            .filter(
                or_(
                    Transaction.note.like(pattern),
                    Transaction.category.like(pattern),
                )
            )
            .order_by(Transaction.date.desc())
            .limit(MAX_PER_TABLE)
            .all()
        )
        for t in txns:
            results.append(
                {
                    "type": "transaction",
                    "type_label": "📊 记账",
                    "type_color": "text-green-6",
                    "title": f"{'📈' if t.type == 'income' else '📉'} {t.category}",
                    "detail": f"¥{t.amount:.2f}" + (f" — {t.note}" if t.note else ""),
                    "date": str(t.date),
                    "url": "/finance",
                }
            )

        # ── 待办 ──────────────────────────────────────────
        todos = (
            db.query(Todo)
            .filter(
                or_(
                    Todo.title.like(pattern),
                    Todo.description.like(pattern),
                )
            )
            .order_by(Todo.due_date.desc().nullslast(), Todo.priority.asc())
            .limit(MAX_PER_TABLE)
            .all()
        )
        for t in todos:
            status = "✅ 已完成" if t.is_completed else "⏳ 待完成"
            priority_icon = {1: "🔴", 2: "🟡", 3: "🟢"}.get(t.priority, "")
            detail_parts = [status]
            if t.description:
                detail_parts.append(t.description)
            if t.due_date:
                detail_parts.append(f"截止：{t.due_date}")

            results.append(
                {
                    "type": "todo",
                    "type_label": "✅ 待办",
                    "type_color": "text-amber-6",
                    "title": f"{priority_icon} {t.title}",
                    "detail": " · ".join(detail_parts),
                    "date": str(t.due_date) if t.due_date else "",
                    "url": "/calendar",
                }
            )

        # ── 日记 ──────────────────────────────────────────
        diaries = (
            db.query(Diary)
            .filter(Diary.content.like(pattern))
            .order_by(Diary.date.desc())
            .limit(MAX_PER_TABLE)
            .all()
        )
        for d in diaries:
            # 截取匹配关键词前后各 60 字作为摘要
            idx = d.content.lower().find(query.strip().lower())
            start = max(0, idx - 60)
            end = min(len(d.content), idx + len(query) + 60)
            snippet = d.content[start:end]
            if start > 0:
                snippet = "…" + snippet
            if end < len(d.content):
                snippet += "…"

            mood_icon = {"happy": "😊", "sad": "😢", "neutral": "😐"}.get(d.mood, "")

            results.append(
                {
                    "type": "diary",
                    "type_label": "📖 日记",
                    "type_color": "text-purple-6",
                    "title": f"{mood_icon} {d.date}",
                    "detail": snippet[:200],
                    "date": str(d.date),
                    "url": "/diary",
                }
            )

        # ── Rnote 文件 ─────────────────────────────────────
        rnotes = (
            db.query(RnoteFile)
            .filter(
                or_(
                    RnoteFile.filename.like(pattern),
                    RnoteFile.tags.like(pattern),
                )
            )
            .order_by(RnoteFile.classified_date.desc())
            .limit(MAX_PER_TABLE)
            .all()
        )
        for r in rnotes:
            detail_parts = []
            if r.target_category:
                detail_parts.append(f"分类：{r.target_category}")
            if r.tags:
                detail_parts.append(f"标签：{r.tags}")
            if r.file_size:
                detail_parts.append(_fmt_size(r.file_size))

            results.append(
                {
                    "type": "rnote",
                    "type_label": "📁 笔记",
                    "type_color": "text-blue-6",
                    "title": r.filename,
                    "detail": " · ".join(detail_parts),
                    "date": str(r.classified_date) if r.classified_date else "",
                    "url": "/rnote",
                }
            )

    finally:
        db.close()

    # 按日期倒序排列
    results.sort(key=lambda x: x.get("date") or "", reverse=True)
    return results
