# CLAUDE.me - My Life Toolbox 项目开发说明书

> **项目代号**：MLT (My Life Toolbox)  
> **核心哲学**：本地优先、模块化插件、单文件启动即用  
> **目标用户**：开发者自用，未来开源给极客群体

---

## 1. 项目全景与核心约束

### 1.1 三大交互形态（BCD实现策略）
- **B (桌面软件GUI)**：使用 `NiceGUI` 的 `ui.run(native=True)` 模式，启动时无浏览器地址栏，看起来像原生窗口。
- **C (Web网页版)**：同一套代码，切换 `native=False` 即可在浏览器打开 `127.0.0.1:8080`，支持手机/平板访问。
- **D (悬浮助手)**：通过 `pystray` 创建系统托盘图标。左键点击托盘图标**弹出/隐藏**主窗口；右键菜单提供“快速记账”、“新建待办”等快捷动作。

### 1.2 技术栈强制锁定（防版本冲突）
```txt
python >= 3.10
nicegui == 1.4.30        # Web UI 框架（稳定版）
pystray == 0.19.0        # 系统托盘
pillow == 10.3.0         # 托盘图标与图像处理
sqlalchemy == 2.0.30     # ORM 数据库操作
apscheduler == 3.10.4    # 定时任务引擎（留给2.0自动化）
requests == 2.31.0       # HTTP 请求（天气/IP）
python-dateutil == 2.9.0 # 日期递归与解析
2. 数据持久化设计（SQLite + SQLAlchemy）
数据库文件位于 data/toolbox.db。以下为必须严格遵守的模型定义：

2.1 记账模型 (Transaction)
python
class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)        # 消费日期
    type = Column(String(10), nullable=False)              # 'income' 或 'expense'
    category = Column(String(50), nullable=False)          # 如 '餐饮', '购物', '工资'
    amount = Column(Float, nullable=False)
    note = Column(String(255), default='')
    created_at = Column(DateTime, default=datetime.utcnow)
2.2 待办事项模型 (Todo)
python
class Todo(Base):
    __tablename__ = 'todos'
    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(String(255), default='')
    due_date = Column(Date, nullable=True, index=True)     # 截止日期，关联日历
    priority = Column(Integer, default=2)                  # 1高 2中 3低
    is_completed = Column(Boolean, default=False)
    date_created = Column(Date, default=date.today)        # 创建日期（用于当日待办锚点）
2.3 日记模型 (Diary)
python
class Diary(Base):
    __tablename__ = 'diaries'
    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False, index=True) # 一天仅一篇日记
    content = Column(Text, default='')                     # 存储 Markdown 格式
    mood = Column(String(20), default='neutral')           # 心情标签: happy/sad/neutral
    weather_override = Column(String(20))                  # 手动记录天气（可选）
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
2.4 Rnote文件管理模型 (RnoteFile)
python
class RnoteFile(Base):
    __tablename__ = 'rnote_files'
    id = Column(Integer, primary_key=True)
    original_path = Column(String(512), unique=True)       # 原始绝对路径
    filename = Column(String(255))                         # 文件名
    target_category = Column(String(100), index=True)      # 分类标签，如 'Math', 'ProjectX'
    target_path = Column(String(512))                      # 移动/归类后的新路径
    file_size = Column(Integer)                            # 字节
    last_modified = Column(DateTime)
    classified_date = Column(Date, default=date.today)     # 归类日期
    tags = Column(String(200), default='')                 # 额外标签，逗号分隔
3. 模块职责与路由规划（NiceGUI页面）
所有UI页面文件置于 /modules 目录下，在 app.py 中通过 @ui.page('/') 注册。

3.1 锚点面板 (dashboard.py) —— 路径 /
功能要求：

顶部显示当前日期与天气（调用 utils/weather.py）。

中间展示今日待办（date_created == today 且未完成），每个待办左侧带复选框（点击后实时更新完成状态）。

底部放置 快速入口按钮：+ 记账、+ 待办、写日记、归类Rnote。

3.2 融合日历与日程 (calendar_feed.py) —— 路径 /calendar
严格按照你选择的“C类”交互设计：

左侧（占比 30%）：渲染月历网格。每天格子右下角显示小圆点标记（有日程/记账的日子显示蓝色，仅日记显示绿色，都有显示紫色）。点击某一天触发右侧更新。

右侧（占比 70%）：混排 Feed 时间线。按时间先后（或类型分组）展示所选日期的所有内容：

先展示当天的日记（若有，显示内容预览及心情图标）。
再展示当天的待办（显示完成状态和优先级）。
最后展示当天的记账流水（收入和支出分别汇总小计）。
交互细节：点击Feed中的“编辑”图标，弹出对应的详情编辑抽屉（Dialog）。

3.3 记账独立页面 (finance.py) —— 路径 /finance
提供按月份筛选的收支折线图（使用 NiceGUI 的 ui.plotly 或 ui.echart）。

数据表格支持增删改操作。

3.4 日记独立编辑器 (diary.py) —— 路径 /diary
集成 ui.markdown 实时预览。

左侧日期选择器，右侧编辑区。

3.5 Rnote 分类管理器 (rnote_manager.py) —— 路径 /rnote
这是本次开发的核心挑战，逻辑必须清晰：

扫描模式：用户选择顶层文件夹（如 ~/Documents/Notes），点击“扫描”，程序递归查找所有 .rnote 文件并列出。

分类规则：用户可以为选中的文件批量设定 target_category（如输入框填写“数学”或“物理”）。

执行动作：点击“执行归类”，程序将文件从原目录移动到 ~/Documents/Notes/分类后的笔记/[target_category]/ 目录下，并更新数据库记录。

回滚机制：在数据库中保留 original_path，以便未来实现“撤销归类”。

3.6 小工具抽屉 (gadgets.py) —— 路径 /gadgets
显示本机内外网IP（调用 utils/ip_tool.py）。

二维码生成（输入文本生成二维码图片）。

密码生成器。

4. 针对 .rnote 文件分类的底层实现细节
由于 .rnote 本质是 zip 压缩包（内部包含 document.svg 和 document.xml），在分类逻辑上，我们不解析内容（避免性能损耗），只基于文件名和用户打标进行移动。

执行流程伪代码：

python
def classify_rnote_files(source_paths: List[str], target_category: str):
    base_dir = Path.home() / "Documents" / "Notes" / "分类后的笔记" / target_category
    base_dir.mkdir(parents=True, exist_ok=True)
    for src in source_paths:
        src_path = Path(src)
        dest = base_dir / src_path.name
        # 重名处理：若存在则添加 (1) 后缀
        if dest.exists():
            dest = dest.with_name(f"{dest.stem} (1){dest.suffix}")
        shutil.move(str(src_path), str(dest))
        # 更新数据库记录...
5. 定时任务与“自动化占位”（2.0预留）
尽管 scheduler.py 已存在，但当前版本只实现纯提醒功能：

每日 08:00 检查是否有待办即将到期（due_date == today），通过 system_notify（Windows 通知或 plyer）弹窗提醒。

抢票/校园跑模块只保留 auto_tasks 空接口，用注释标明“待用户提供具体 API/选择器后接入”。

6. AI 协作与代码生成规范（给你的“大肥鱼”指令）
既然你熟练使用AI，我们的协作遵循以下规矩，可大幅提升效率：

禁止一次性输出超过 3 个文件：否则上下文爆炸。我会分批次给你文件。

标记法：我在代码中会插入 # 🐟 AI: 请在此处补全 xxx 逻辑，你直接将这句话连带上下文复制给AI，即可生成精确代码。

测试优先：所有工具函数（如 weather.py）必须包含 if __name__ == "__main__": 测试块，便于你单独调试。

注释量：核心业务逻辑必须用中文写注释，方便未来开源时他人阅读。

7. 打包与分发规划（自用 -> 开源）
开发阶段：直接 python app.py 运行。

打包阶段：使用 PyInstaller 打包成单文件 .exe（或 .app）。

bash
pyinstaller --onefile --windowed --icon=static/icon.ico --add-data "static;static" app.py
开源协议：推荐 MIT License。

8. 当前开发阶段（MVP最小可行产品）首批交付清单
请AI（也就是我）立刻、马上为你输出以下 3个基础文件 的完整代码：

requirements.txt（锁定版本）

core/database.py（包含 Base、engine、SessionLocal，以及 init_db() 函数）

app.py（包含系统托盘图标 + NiceGUI 主窗口路由 + 三个页面 / /calendar /rnote 的基础骨架，确保可以空跑不报错）

9. 开发环境约定
虚拟环境使用 venv，目录名 .venv。

所有日期处理统一使用 datetime.date.today()，时区定为 Asia/Shanghai。

最后寄语：这份 CLAUDE.me 将作为项目的唯一真理解档。每次开启新会话开发时，请将此文件内容发给AI，它便能瞬间恢复所有设计上下文。现在，去让那条“大肥鱼”给你生成第一批代码吧！🐟

text

---

### 🐟 接下来的行动指令

既然 `CLAUDE.me` 已经落地，**我作为你的AI，此刻已经准备就绪**。按照第8条的承诺，我现在将为你生成 **`requirements.txt`**、**`core/database.py`** 和 **`app.py`** 这三个种子文件。

你只需要在IDE里新建项目，把这3个文件复制进去，运行 `pip install -r requirements.txt` 和 `python app.py`，你就能看到一个带托盘图标和空白页面的“工具箱雏形”！

**请回复“开工”**，我立刻把这三份代码贴出来（为避免刷屏，我会分次发送，第一波先发 `requirements.txt` 和 `database.py`，等你确认跑通再发 `app.py`）。等你指令！⌨️