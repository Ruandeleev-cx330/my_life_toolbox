"""插入测试数据 —— 用于验证 Calendar Feed 页面"""
from datetime import date

from core.database import SessionLocal, Diary, Todo, Transaction

db = SessionLocal()

# 日记
db.add(Diary(date=date.today(), content="今天天气不错，代码写得顺。", mood="happy"))

# 待办（今日截止）
db.add(Todo(title="完成 calendar_feed 联调", due_date=date.today(), priority=1))
db.add(Todo(title="整理本周笔记", due_date=date.today(), priority=2))

# 记账
db.add(Transaction(date=date.today(), type="expense", category="餐饮", amount=36.5, note="午餐"))
db.add(Transaction(date=date.today(), type="income", category="工资", amount=500.0, note=""))

# 几天前的数据（测试月历圆点）
from datetime import timedelta

yesterday = date.today() - timedelta(days=1)
db.add(Diary(date=yesterday, content="昨天写了一篇日记", mood="neutral"))
db.add(Transaction(date=yesterday, type="expense", category="交通", amount=8.0, note="地铁"))

db.commit()
db.close()
print("[OK] 测试数据已写入 data/toolbox.db")
