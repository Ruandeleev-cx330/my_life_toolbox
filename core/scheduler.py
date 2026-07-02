"""
定时任务引擎 —— 自动备份 + 智能提醒
用法：在 app.py 中调用 start_scheduler() 启动所有后台定时任务。

任务清单：
  1. 自动备份      每周日   03:00   导出全库 JSON 到 data/auto_backup/
  2. 待办到期提醒   每天     08:30   检查 due_date==today 且未完成的待办
  3. 待办到期提醒   每天     12:00   同上（中午二次提醒）
  4. 每日日报提醒   每天     21:00   若当天无日记，提醒写日记
  5. Rnote 积压提醒 每周一   10:00   若存在未分类笔记，提醒整理
"""

import json
from datetime import date, datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func

from core.database import DATA_DIR, Diary, RnoteFile, SessionLocal, Todo, Transaction
from utils.notifier import send_notification

# ── 目录 ────────────────────────────────────────────────────────
AUTO_BACKUP_DIR = DATA_DIR / "auto_backup"
AUTO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ── 全局调度器实例 ──────────────────────────────────────────────
_scheduler: BackgroundScheduler | None = None


# ══════════════════════════════════════════════════════════════════
# 序列化工具（自动备份用）
# ══════════════════════════════════════════════════════════════════

def _model_to_dict(obj) -> dict:
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        result[col.name] = val
    return result


# ══════════════════════════════════════════════════════════════════
# 任务 1：自动备份
# ══════════════════════════════════════════════════════════════════

def _auto_backup_job():
    """每周日 03:00——导出全库 JSON"""
    db = SessionLocal()
    try:
        data = {
            "transactions": [_model_to_dict(r) for r in db.query(Transaction).all()],
            "todos": [_model_to_dict(r) for r in db.query(Todo).all()],
            "diaries": [_model_to_dict(r) for r in db.query(Diary).all()],
            "rnote_files": [_model_to_dict(r) for r in db.query(RnoteFile).all()],
        }
    finally:
        db.close()

    timestamp = date.today().strftime("%Y%m%d")
    backup_path = AUTO_BACKUP_DIR / f"backup_{timestamp}.json"
    json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    backup_path.write_text(json_str, encoding="utf-8")
    _cleanup_old_backups(keep_days=30)
    print(f"[Scheduler] [OK] 自动备份完成 -> {backup_path}")


def _cleanup_old_backups(keep_days: int = 30):
    """清理超过 keep_days 天的旧备份"""
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=keep_days)
    for f in AUTO_BACKUP_DIR.glob("backup_*.json"):
        try:
            date_str = f.stem.replace("backup_", "")
            file_date = date(
                int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
            )
            if file_date < cutoff:
                f.unlink()
                print(f"[Scheduler] [DEL] 清理旧备份 -> {f.name}")
        except (ValueError, IndexError):
            pass


# ══════════════════════════════════════════════════════════════════
# 任务 2：待办到期提醒（每天 08:30 + 12:00）
# ══════════════════════════════════════════════════════════════════

def _todo_reminder_job():
    """
    检查是否有今天到期的未完成待办，有则弹窗提醒。
    每天 08:30 和 12:00 各执行一次。
    """
    db = SessionLocal()
    try:
        today = date.today()
        due_todos = (
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

    if not due_todos:
        return  # 没有到期待办，不打扰

    count = len(due_todos)
    top_labels = []
    for t in due_todos[:5]:
        p_icon = {1: "🔴", 2: "🟡", 3: "🟢"}.get(t.priority, "")
        top_labels.append(f"{p_icon} {t.title}")

    body = f"共 {count} 项待办今日到期：\n" + "\n".join(top_labels)
    if count > 5:
        body += f"\n... 还有 {count - 5} 项"
    body += "\n\n打开 My Life Toolbox 查看详情。"

    send_notification(
        title=f"📋 今日待办到期提醒（{count} 项）",
        message=body,
    )


# ══════════════════════════════════════════════════════════════════
# 任务 3：每日日报提醒（每天 21:00）
# ══════════════════════════════════════════════════════════════════

def _diary_reminder_job():
    """
    每天晚上 21:00 检查当天是否有日记。
    若没有，提醒用户写日记。
    """
    db = SessionLocal()
    try:
        today = date.today()
        exists = (
            db.query(Diary).filter(Diary.date == today).first()
        )
    finally:
        db.close()

    if exists:
        return  # 今天已写日记，无需提醒

    send_notification(
        title="📖 每日日记提醒",
        message="今天还没写日记哦，记录一下此刻的心情吧！\n\n打开 MLT → 写日记，花两分钟回顾今天。",
    )


# ══════════════════════════════════════════════════════════════════
# 任务 4：Rnote 积压提醒（每周一 10:00）
# ══════════════════════════════════════════════════════════════════

def _rnote_backlog_job():
    """
    每周一 10:00 检查是否有 target_category 为空的未分类笔记。
    若有，提醒用户整理。
    """
    db = SessionLocal()
    try:
        unclassified_count = (
            db.query(func.count(RnoteFile.id))
            .filter(
                (RnoteFile.target_category == None)
                | (RnoteFile.target_category == "")
            )
            .scalar()
        )
    finally:
        db.close()

    if not unclassified_count:
        return  # 全部已分类

    send_notification(
        title="📂 Rnote 笔记积压提醒",
        message=(
            f"你有 {unclassified_count} 份笔记尚未分类，快来整理吧！\n\n"
            "打开 MLT → Rnote 管理器，扫描目录后批量归类。"
        ),
    )


# ══════════════════════════════════════════════════════════════════
# 调度器生命周期
# ══════════════════════════════════════════════════════════════════

def start_scheduler():
    """
    启动所有后台定时任务。
    在 app.py 中调用一次即可（幂等：重复调用不会创建多个调度器）。
    """
    global _scheduler

    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(
        timezone="Asia/Shanghai",
        job_defaults={"misfire_grace_time": 300},
    )

    # ── 自动备份：每周日 03:00 ──────────────────────────
    _scheduler.add_job(
        _auto_backup_job,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="Asia/Shanghai"),
        id="auto_backup_weekly",
        name="每周自动备份",
        replace_existing=True,
    )

    # ── 待办到期提醒：每天 08:30 ────────────────────────
    _scheduler.add_job(
        _todo_reminder_job,
        CronTrigger(hour=8, minute=30, timezone="Asia/Shanghai"),
        id="todo_reminder_morning",
        name="待办到期提醒（早晨）",
        replace_existing=True,
    )

    # ── 待办到期提醒：每天 12:00 ────────────────────────
    _scheduler.add_job(
        _todo_reminder_job,
        CronTrigger(hour=12, minute=0, timezone="Asia/Shanghai"),
        id="todo_reminder_noon",
        name="待办到期提醒（中午）",
        replace_existing=True,
    )

    # ── 每日日报提醒：每天 21:00 ────────────────────────
    _scheduler.add_job(
        _diary_reminder_job,
        CronTrigger(hour=21, minute=0, timezone="Asia/Shanghai"),
        id="diary_reminder_daily",
        name="每日日报提醒",
        replace_existing=True,
    )

    # ── Rnote 积压提醒：每周一 10:00 ────────────────────
    _scheduler.add_job(
        _rnote_backlog_job,
        CronTrigger(day_of_week="mon", hour=10, minute=0, timezone="Asia/Shanghai"),
        id="rnote_backlog_weekly",
        name="Rnote 积压提醒",
        replace_existing=True,
    )

    _scheduler.start()

    print("[Scheduler] [OK] 所有定时任务已就绪")
    print("  · 自动备份        每周日  03:00")
    print("  · 待办到期提醒     每天    08:30 / 12:00")
    print("  · 每日日报提醒     每天    21:00")
    print("  · Rnote 积压提醒   每周一  10:00")


def stop_scheduler():
    """停止所有定时任务（程序退出时调用）"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        print("[Scheduler] [STOP] 调度器已停止")
