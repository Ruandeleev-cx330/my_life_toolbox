"""
My Life Toolbox - 数据库初始化模块
使用 SQLAlchemy 2.0 + SQLite，所有模型定义集中于此。
数据库文件自动创建于 data/toolbox.db。
"""

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ── 项目根目录定位 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # 确保 data/ 目录存在

DB_PATH = DATA_DIR / "toolbox.db"

# ── SQLAlchemy 引擎 & 会话工厂 ──────────────────────────────────
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,  # 生产环境关闭 SQL 日志；调试时可改为 True
    connect_args={"check_same_thread": False},  # SQLite 多线程兼容
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


# ══════════════════════════════════════════════════════════════════
# 模型定义 (依据 CLAUDE.me §2)
# ══════════════════════════════════════════════════════════════════

class Transaction(Base):
    """记账模型 —— 记录每一笔收入或支出"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)          # 消费/收入日期
    type = Column(String(10), nullable=False)                # 'income' 或 'expense'
    category = Column(String(50), nullable=False)            # 如 '餐饮', '购物', '工资'
    amount = Column(Float, nullable=False)
    note = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Todo(Base):
    """待办事项模型"""
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(String(255), default="")
    due_date = Column(Date, nullable=True, index=True)       # 截止日期，关联日历
    priority = Column(Integer, default=2)                    # 1=高  2=中  3=低
    is_completed = Column(Boolean, default=False)
    date_created = Column(Date, default=date.today)          # 创建日期（当日待办锚点）


class Diary(Base):
    """日记模型 —— 一天仅一篇，Markdown 存储"""
    __tablename__ = "diaries"

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False, index=True)
    content = Column(Text, default="")                       # Markdown 格式正文
    mood = Column(String(20), default="neutral")             # happy / sad / neutral
    weather_override = Column(String(20))                    # 手动记录天气（可选）
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class RnoteFile(Base):
    """Rnote 文件管理模型 —— 记录 .rnote 文件的分类与归档路径"""
    __tablename__ = "rnote_files"

    id = Column(Integer, primary_key=True)
    original_path = Column(String(512), unique=True)          # 原始绝对路径
    filename = Column(String(255))                            # 文件名
    target_category = Column(String(100), index=True)         # 分类标签，如 'Math', 'ProjectX'
    target_path = Column(String(512))                         # 移动/归类后的新路径
    file_size = Column(Integer)                               # 字节
    last_modified = Column(DateTime)
    classified_date = Column(Date, default=date.today)        # 归类日期
    tags = Column(String(200), default="")                    # 额外标签，逗号分隔


class Setting(Base):
    """键值配置表 —— 存储插件开关等运行时配置"""
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, default="")


# ══════════════════════════════════════════════════════════════════
# 初始化函数
# ══════════════════════════════════════════════════════════════════

def init_db():
    """
    创建所有 ORM 表（幂等：已存在的表不会重复创建）。
    在 app.py 启动时调用一次即可。
    """
    Base.metadata.create_all(bind=engine)
    print(f"[DB] 数据库已就绪 -> {DB_PATH}")


# ── 快速获取会话的依赖注入工具 ──────────────────────────────────

def get_db():
    """生成器函数，用于 NiceGUI 或其他上下文中获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── 自测块 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("[DB] 所有表创建成功，自测通过 √")
