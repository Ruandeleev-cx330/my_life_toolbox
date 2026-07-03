# 🧰 My Life Toolbox (MLT)

个人生活管理工具箱 —— 桌面悬浮窗 + Web 完整面板，本地优先，数据自有。

---

## 目录

- [快速开始](#快速开始)
- [项目架构](#项目架构)
- [插件系统](#插件系统)
- [桌面悬浮窗](#桌面悬浮窗)
  - [天气显示](#天气显示)
  - [今日待办](#今日待办)
  - [本机 IP](#本机-ip)
  - [快捷记账](#快捷记账)
  - [置顶开关](#置顶开关)
  - [打开 Web 面板](#打开-web-面板)
  - [右键菜单](#右键菜单)
- [Web 完整面板](#web-完整面板)
  - [首页仪表盘](#首页仪表盘-)
  - [日历日程](#日历日程-calendar)
  - [记账管理](#记账管理-finance)
  - [日记编辑器](#日记编辑器-diary)
  - [Rnote 笔记管理](#rnote-笔记管理-rnote)
  - [小工具](#小工具-gadgets)
  - [插件管理](#插件管理-adminplugins)
  - [设置](#设置-settings)
- [开机自启动](#开机自启动)
- [系统托盘](#系统托盘)
- [定时任务](#定时任务)
- [全局搜索](#全局搜索)
- [配置说明](#配置说明)
- [数据库设计](#数据库设计)
- [工具模块](#工具模块)
- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [开发与调试](#开发与调试)

---

## 快速开始

### 环境要求

- Python >= 3.10
- Windows 10/11（macOS/Linux 部分功能受限）

### 安装与启动

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
.venv\Scripts\activate     # Windows
source .venv/bin/activate   # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动应用
python app.py
```

启动后，桌面右下角会出现一个**深色半透明悬浮窗**，Web 面板不会自动打开（按需启动）。

### 首次使用

```bash
# 可选：插入测试数据，验证各页面功能
python seed_test_data.py
```

---

## 项目架构

```
┌─────────────────────────────────────────────────┐
│                    app.py                        │
│         (主入口，协调所有组件的生命周期)            │
├──────────────┬──────────────┬───────────────────┤
│  主线程       │  后台线程 1    │  后台线程 2        │
│  tkinter      │  NiceGUI     │  pystray          │
│  悬浮窗        │  Web 服务器   │  系统托盘          │
│  (前台阻塞)    │  :18520      │                   │
└──────────────┴──────────────┴───────────────────┘
        │              │               │
        └──────────────┼───────────────┘
                       │
              ┌────────┴────────┐
              │  data/toolbox.db │
              │    (SQLite)      │
              └─────────────────┘
```

**启动流程**：

1. 初始化数据库 + 注册页面路由
2. 启动定时任务（APScheduler）
3. 启动 NiceGUI Web 服务器（后台线程，端口 18520，**不自动打开浏览器**）
4. 启动系统托盘（后台线程）
5. 显示桌面悬浮窗（tkinter 主循环，前台阻塞）
6. 关闭悬浮窗 → 停止全部组件 → 进程退出

---

## 插件系统

MLT 采用插件化架构，日记、记账、日历、Rnote、小工具等功能模块均为独立插件，可在 Web 管理页面按需启用/禁用。

### 架构

```
plugins/
├── __init__.py            # BasePlugin 基类 + PluginLoader
├── finance_plugin.py      # 记账插件
├── diary_plugin.py        # 日记插件
├── calendar_plugin.py     # 日历日程插件
├── rnote_plugin.py        # Rnote 笔记管理插件
├── gadgets_plugin.py      # 小工具插件
└── admin_plugin.py        # 插件管理页面
```

### BasePlugin 接口

```python
class BasePlugin(ABC):
    name: str          # 唯一标识 (kebab-case)
    title: str         # 菜单显示名称
    version: str       # 版本号
    author: str        # 作者
    description: str   # 描述

    def register(self)       # 注册 NiceGUI 路由（@ui.page）
    def menu_item(self)      # 返回 (label, path) 菜单项
    def on_enable(self)      # 启用回调
    def on_disable(self)     # 禁用回调
```

### 编写新插件

```python
from plugins import BasePlugin

class MyPlugin(BasePlugin):
    name = "my-plugin"
    title = "我的插件"
    version = "1.0.0"
    author = "Me"

    def register(self):
        from nicegui import ui

        @ui.page("/my-plugin")
        def my_page():
            ui.label("Hello from plugin!")

    def menu_item(self):
        return ("我的插件", "/my-plugin")
```

将文件放入 `plugins/` 目录，启动时自动发现。

---

## 桌面悬浮窗

悬浮窗是 MLT 的**日常快速入口**，常驻桌面，提供即时信息查看和快捷操作。

### 外观与交互

| 特性 | 说明 |
|------|------|
| 样式 | 无边框、深色半透明（默认 88% 不透明度） |
| 位置 | 默认桌面右下角 |
| 尺寸 | 260 × 400 像素 |
| 拖拽 | 拖拽标题栏「🧰 MLT」移动窗口 |
| 刷新 | 每 30 秒自动刷新数据和天气 |
| 置顶 | 点击 📌 按钮切换窗口是否始终在最前 |

### 天气显示

```
┌──────────────────────┐
│ ☀️  Beijing +25°C   │
└──────────────────────┘
```

- 调用 `utils/weather.py` → wttr.in 免费天气 API
- 默认城市：Beijing（可在 `utils/weather.py` 中修改 `fetch_weather(city="Shanghai")`）
- 超时 3 秒，失败时显示「天气获取中...」
- 每 30 秒自动刷新

### 今日待办

```
┌──────────────────────┐
│ 待办: 3 项       ▶  │  ← 点击展开/收起
├──────────────────────┤
│ ☐ 🔴 完成联调        │  ← 展开后显示列表
│ ☐ 🟡 整理笔记        │     可勾选完成
│ ☐ 🟢 回复邮件        │
└──────────────────────┘
```

- 从 `todos` 表读取：`due_date == today` 且 `is_completed == False`
- 点击「待办: N 项」展开/收起列表
- **勾选复选框** → 立即写入数据库，Web 面板端刷新后可同步看到
- 优先级配色：🔴 高 / 🟡 中 / 🟢 低
- 底部 **+ 待办** 按钮快速新建当天到期的待办

### 本机 IP

```
┌──────────────────────────┐
│ 🖥 内网          → 外网  │  ← 点击切换内外网
│                          │
│ 192.168.3.126       [cp] │  ← 上行：IPv4（独立复制）
│ 240e:393:3413:...    [cp] │  ← 下行：IPv6（wraplength 自动换行）
└──────────────────────────┘
```

- 点击 IP 区域**切换内网/外网**显示
- 每行独立 **[cp]** 按钮，一键复制 v4 或 v6
- IPv6 自动换行适配悬浮窗窄宽度
- IPv4：UDP 连接法获取（避免返回 127.0.0.1）
- IPv6：连接 Google DNS IPv6 地址获取，降级遍历网卡
- 获取失败显示 `--`

### 快捷记账

点击「+ 记账」按钮弹出简易窗口：

```
┌──────────────────────┐
│      + 快捷记账       │
│                      │
│ 金额                  │
│ ┌──────────────────┐ │
│ │ 36.5             │ │
│ └──────────────────┘ │
│ 分类                  │
│ ┌──────────────────┐ │
│ │ 餐饮              │ │
│ └──────────────────┘ │
│ 备注（可选）           │
│ ┌──────────────────┐ │
│ │ 午餐外卖           │ │
│ └──────────────────┘ │
│          [取消] [保存]│
└──────────────────────┘
```

- 默认类型：`expense`（支出）
- 默认分类：`餐饮`
- 可选备注字段，用于消费详情记录，写入数据库供高频词统计
- 保存后**立即写入数据库**

### 置顶开关

| 状态 | 图标 | 颜色 | 含义 |
|------|------|------|------|
| 置顶中 | 📌 | 蓝色 `#3b82f6` | 窗口始终在最前，不会被其他窗口遮挡 |
| 未置顶 | 📍 | 灰色 `#a0a0a0` | 普通窗口层级，可被覆盖 |

- 点击 📌/📍 切换
- 状态保存到 `config.json` → `always_on_top`
- 下次启动自动恢复上次状态
- 使用 Win32 `SetWindowPos(HWND_TOPMOST)` API 实现，不依赖 `overrideredirect`

### 打开 Web 面板

| 操作 | 方式 |
|------|------|
| **双击悬浮窗任意位置** | 打开 Web 面板 |
| **点击底部 🖥 面板 按钮** | 打开 Web 面板 |
| **右键菜单 → 打开完整面板** | 打开 Web 面板 |

- 自动等待 NiceGUI 服务器就绪（最多 5 秒）
- 在默认浏览器中打开 `http://127.0.0.1:18520`

### 右键菜单

在悬浮窗上右键弹出：

| 菜单项 | 功能 |
|--------|------|
| 打开完整面板 | 打开 Web 面板 |
| 切换置顶状态 | 切换窗口是否置顶 |
| ☐ 开机自启动 | 勾选后系统启动时自动运行 MLT |
| ☐ 启动时自动打开 Web | 勾选后每次启动自动打开浏览器 |
| 立即刷新 | 立即刷新天气/IP/待办数据 |
| 退出 | 退出整个程序 |

---

## Web 完整面板

Web 界面通过 NiceGUI (Quasar 组件库) 构建，提供完整的数据管理功能。

访问地址：**`http://127.0.0.1:18520`**

所有页面共享：
- **左侧导航抽屉**：点击 ☰ 打开，列出全部页面链接
- **顶部搜索头栏**：全局跨表搜索

### 首页仪表盘 `/`

```
┌────────────────────────────────────────────┐
│ ☰ 🧰 MLT          [搜索记账/待办/日记...] 🔍 │
├────────────────────────────────────────────┤
│ 2026年07月03日 星期四    ☀️ +25°C            │
│ 🏠 首页  📅 日历  📂 Rnote  💰 记账 ...      │
├────────────────────────────────────────────┤
│ 📋 今日待办                                 │
│ ☑ 🔴 完成联调     📅 2026-07-03             │
│ ☐ 🟡 整理笔记     📅 2026-07-03             │
├────────────────────────────────────────────┤
│ ⚡ 快速入口                                 │
│ [📝 记账] [✅ 新建待办] [📖 写日记] [📂 归类Rnote] │
└────────────────────────────────────────────┘
```

- 顶部显示中文化日期和实时天气
- 中间列出今日待办，**勾选复选框即更新数据库**
- 底部快速入口按钮，跳转到各功能页面

### 日历日程 `/calendar`

左右分栏布局（35% / 65%）：

**左侧月历**：

- ◀ ▶ 切换月份
- 日期格子右下角**小圆点标记**：
  - 🔵 蓝色 = 当日有待办或记账（无日记）
  - 🟢 绿色 = 当日仅有日记
  - 🟣 紫色 = 当日既有日记又有待办/记账
  - 无圆点 = 当日无任何记录
- 点击某一天 → 右侧 Feed 更新
- 今天日期显示琥珀色背景

**右侧 Feed 时间线**（按选中日期展示）：

1. **日记预览**：显示心情图标 + 正文前 200 字
2. **待办清单**：按优先级排列，可勾选完成
3. **记账流水**：收入/支出汇总 + 逐条明细

每条记录旁有 ✏️ 编辑按钮，点击弹出编辑对话框。

### 记账管理 `/finance`

**KPI 卡片**（按月）：

| 卡片 | 内容 |
|------|------|
| 📈 总收入 | 当月收入合计 |
| 📉 总支出 | 当月支出合计 |
| 💰 结余 | 收入 - 支出 |
| 📊 环比 | 支出较上月增长率 |

**消费洞察**：

- 🍩 **支出分类占比环形图**（ECharts donut）—— Top 5 分类 + 其他
- 🏷 **备注高频词标签云** —— 从备注中提取中文高频词，按频率调整字号

**收支折线图**：

- 当月每日收入/支出双线图（ECharts）
- 带面积填充，平滑曲线

**数据表格**：

- 按月份筛选
- 显示：日期 / 类型 / 分类 / 金额 / 备注
- 支持 ✏️ 编辑 和 🗑 删除
- ➕ 新增记账 按钮

### 日记编辑器 `/diary`

```
┌──────────────────────────────────────────────┐
│ 📅 选择日期                                   │
│ ◀ [2026-07-03] ▶                             │
│ [📅 回到今天]                                 │
│                                              │
│ 2026年07月03日                                │
│ 星期四                                        │
│ 📍 今天                                       │
├──────────────────────────────────────────────┤
│ 心情 [😊 开心 ▾]  天气 [晴]    [💾 保存]      │
│ ┌──────────────────────────────────────────┐ │
│ │ # 今日总结                                │ │
│ │                                          │ │
│ │ 今天完成了代码重构...                      │ │
│ └──────────────────────────────────────────┘ │
│ 📄 实时预览                                   │
│ ┌──────────────────────────────────────────┐ │
│ │ 今日总结                                  │ │
│ │ 今天完成了代码重构...                      │ │
│ └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

- 左侧日期选择器，支持 ◀ ▶ 切换或直接选择日期
- 中间 Markdown 编辑器（`ui.textarea`）
- 下方 **实时 Markdown 预览**（`ui.markdown`）
- 心情选择：😊 开心 / 😢 难过 / 😐 平静
- 天气手动记录
- 一天仅一篇日记（同日期自动合并）

### Rnote 笔记管理 `/rnote`

`.rnote` 文件（本质是 zip 压缩包，包含 `document.svg` + `document.xml`）的分类管理器。

**使用流程**：

1. **选择根目录** → 手动输入路径或点击 📂 浏览
2. **🔍 扫描** → 递归查找所有 `.rnote` 文件
3. **勾选文件** → 在表格中多选要归类的文件（支持全选）
4. **填写分类名** → 如「数学」「物理」「项目笔记」
5. **🚀 执行归类** → 文件移动到 `data/classified_notes/[分类名]/`

**表格信息**：

| 列 | 内容 |
|----|------|
| ☑ | 复选框（支持全选） |
| 文件名 | `.rnote` 文件名 |
| 大小 | 可读格式（KB/MB/GB） |
| 修改时间 | 文件最后修改时间 |
| 状态 | 已归类至「xxx」（蓝色）/ 未分类（灰色） |

**安全机制**：

- 重名处理：自动添加 `(1)` `(2)` 后缀
- 数据库保留 `original_path`，支持未来撤销
- 移动失败时自动回滚（文件移回原位）

### 小工具 `/gadgets`

**🖥 本机 IP**（2×1 布局，每卡 v4/v6 双行）：

| 内网 IP | 公网 IP |
|---------|---------|
| v4 `192.168.x.x` [copy] | v4 `x.x.x.x` [copy] |
| v6 `240e:...` [copy] | v6 `240e:...` [copy] |

- 每行独立 copy 按钮
- 支持 IPv4 + IPv6 双栈

**📱 二维码生成器**：

- 输入任意文本/网址
- 生成 240×240 像素 QR 码
- 自动适配 `data:image/png;base64` 显示

**🔑 密码生成器**：

- 可调长度（6~64 位）
- 可选包含数字、符号
- 一键生成 + 📋 复制

### 插件管理 `/admin/plugins`

- 列表展示所有已加载插件（名称 / 版本 / 作者 / 描述）
- 开关按钮启用/禁用插件
- 禁用后路由不可访问、侧边栏菜单隐藏
- 状态持久化到数据库 `settings` 表
- 需重启应用生效

### 设置 `/settings`

**开机自启动**：

- 开关控制 Windows 开机时自动启动 MLT
- 在 `Startup` 目录创建 `MLT_autostart.bat`（使用 `pythonw.exe` 无窗口运行）

**天气设置**：

- 输入城市英文名（如 `Shanghai`），保存到 `config.json`
- 重启后悬浮窗天气显示对应城市

**📤 一键导出**：

- 将全部数据（记账/待办/日记/Rnote）导出为 JSON 文件
- 自动触发浏览器下载

**📥 一键导入**：

- 选择之前导出的 JSON 备份文件
- **二次确认弹窗**防止误操作
- 先清空后恢复（按表顺序：transactions → todos → diaries → rnote_files）

**🤖 自动备份**：

- 每周日凌晨 03:00 自动导出 JSON 到 `data/auto_backup/`
- 自动清理超过 30 天的旧备份
- 文件名格式：`backup_YYYYMMDD.json`

**清空数据**：

- 二次确认对话框，删除全部四张表数据
- 建议先导出备份
- 不可撤销操作

---

## 开机自启动

启用后，Windows 启动时自动在后台运行 MLT（悬浮窗 + Web 服务器静默启动）。

| 特性 | 说明 |
|------|------|
| 实现方式 | Startup 目录 + `.bat` 脚本 + `pythonw.exe`（无控制台黑窗） |
| 管理入口 | Web 设置页 + 悬浮窗右键菜单 |
| 跨平台 | 当前仅 Windows（macOS LaunchAgent / Linux autostart 预留接口） |

---

## 系统托盘

程序启动后，系统托盘（Windows 右下角）显示 MLT 图标。

| 托盘菜单 | 功能 |
|----------|------|
| 📌 显示悬浮窗 | 恢复/显示悬浮窗（短暂置顶后恢复原状态） |
| 🖥 打开 Web 面板 | 在浏览器中打开完整面板 |
| ❌ 退出 | 停止所有定时任务 → 关闭悬浮窗 → 关闭 Web 服务器 → 退出托盘 |

- 托盘图标：优先使用 `static/icon.ico`，否则生成 64×64 蓝色占位图

---

## 定时任务

所有定时任务使用 **APScheduler**（`core/scheduler.py`），时区 `Asia/Shanghai`。

| 任务 | 时间 | 说明 |
|------|------|------|
| 自动备份 | 每周日 03:00 | 导出全库 JSON 到 `data/auto_backup/`，自动清理 30 天前的旧备份 |
| 待办到期提醒 | 每天 08:30 | 检查 `due_date == today` 且未完成的待办，弹窗通知 |
| 待办到期提醒 | 每天 12:00 | 同上（中午二次提醒） |
| 每日日记提醒 | 每天 21:00 | 若当天无日记记录，提醒写日记 |
| Rnote 积压提醒 | 每周一 10:00 | 若存在未分类的笔记，提醒整理 |

**通知机制**（`utils/notifier.py`）：

- 策略 1：`plyer.notification`（Windows/macOS/Linux 原生通知）
- 策略 2：`ctypes.MessageBoxW`（Windows 弹窗）
- 策略 3：控制台 `print`（最后兜底）

---

## 全局搜索

在 Web 界面顶部搜索框输入关键词（回车或点击 🔍），弹出全屏搜索对话框。

**搜索范围**：

| 类型 | 搜索字段 |
|------|----------|
| 📊 记账 | `note`（备注）、`category`（分类） |
| ✅ 待办 | `title`（标题）、`description`（描述） |
| 📖 日记 | `content`（全文，含关键词上下文摘要） |
| 📁 笔记 | `filename`（文件名）、`tags`（标签） |

每类最多返回 20 条，按日期倒序排列。每条结果包含「→ 跳转」按钮，直接导航到对应页面。

---

## 配置说明

配置文件位于项目根目录 `config.json`：

```json
{
  "always_on_top": true,
  "auto_open_web": false,
  "opacity": 0.88
}
```

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `always_on_top` | bool | `true` | 悬浮窗是否始终置顶 |
| `auto_open_web` | bool | `false` | 启动时是否自动打开 Web 面板 |
| `opacity` | float | `0.88` | 悬浮窗不透明度（0.0 ~ 1.0） |
| `city` | string | `"Beijing"` | 天气城市（英文名，如 `Shanghai`、`Tokyo`） |

**修改方式**：

- **置顶**：点击悬浮窗 📌 按钮自动保存
- **自动打开 Web**：右键悬浮窗 → 勾选/取消「开机自动打开 Web」
- **透明度**：手动编辑 `config.json`

---

## 数据库设计

数据库文件：`data/toolbox.db`（SQLite，首次启动自动创建）

### transactions（记账）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 主键 |
| `date` | DATE | 消费/收入日期（有索引） |
| `type` | VARCHAR(10) | `income` 或 `expense` |
| `category` | VARCHAR(50) | 分类，如 餐饮/购物/工资 |
| `amount` | FLOAT | 金额 |
| `note` | VARCHAR(255) | 备注 |
| `created_at` | DATETIME | 创建时间 |

### todos（待办事项）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 主键 |
| `title` | VARCHAR(100) | 标题 |
| `description` | VARCHAR(255) | 描述 |
| `due_date` | DATE | 截止日期（有索引） |
| `priority` | INTEGER | 1=高 2=中 3=低 |
| `is_completed` | BOOLEAN | 是否完成 |
| `date_created` | DATE | 创建日期（当日待办锚点） |

### diaries（日记）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 主键 |
| `date` | DATE UNIQUE | 日期（一天仅一篇，有索引） |
| `content` | TEXT | Markdown 格式正文 |
| `mood` | VARCHAR(20) | 心情：`happy` / `sad` / `neutral` |
| `weather_override` | VARCHAR(20) | 手动记录天气（可选） |
| `updated_at` | DATETIME | 最后更新时间 |

### rnote_files（Rnote 笔记）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 主键 |
| `original_path` | VARCHAR(512) UNIQUE | 原始绝对路径 |
| `filename` | VARCHAR(255) | 文件名 |
| `target_category` | VARCHAR(100) | 分类标签（有索引） |
| `target_path` | VARCHAR(512) | 移动后的新路径 |
| `file_size` | INTEGER | 字节数 |
| `last_modified` | DATETIME | 文件最后修改时间 |
| `classified_date` | DATE | 归类日期 |
| `tags` | VARCHAR(200) | 额外标签（逗号分隔） |

### settings（键值配置）

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | VARCHAR(100) PK | 配置键名 |
| `value` | TEXT | 配置值 |

示例记录：
- `plugin.finance.enabled` = `"true"`
- `plugin.diary.enabled` = `"false"`

---

## 工具模块

### `utils/weather.py` —— 天气获取

```python
from utils.weather import fetch_weather
weather = fetch_weather()              # 默认 Beijing
weather = fetch_weather("Shanghai")    # 指定城市
weather = fetch_weather(timeout=5.0)   # 自定义超时
```

- 调用 [wttr.in](https://wttr.in) 免费天气 API
- 返回格式：`☀️ +25°C`
- 超时或异常返回 `"天气获取中"`

### `utils/ip_tool.py` —— IP 查询（IPv4 + IPv6）

```python
from utils.ip_tool import (
    get_internal_ipv4, get_external_ipv4,
    get_internal_ipv6, get_external_ipv6,
)

local_v4 = get_internal_ipv4()   # 内网 IPv4（UDP → 8.8.8.8）
local_v6 = get_internal_ipv6()   # 内网 IPv6（连接 Google DNS IPv6 / 遍历网卡）
public_v4 = get_external_ipv4()  # 公网 IPv4（ipify.org 等）
public_v6 = get_external_ipv6()  # 公网 IPv6（api6.ipify.org 等）
```

- IPv4：UDP 连接法 + 多服务降级（ipify → httpbin → ipapi → ifconfig）
- IPv6：Google DNS IPv6 连接法，降级遍历网卡全局单播地址；公网使用 IPv6 专用 API
- IPv6 不可用时返回 `"IPv6 不可用"`
- 兼容旧 API：`get_internal_ip()` / `get_external_ip()` → 等同 v4 版本

### `utils/autostart.py` —— 开机自启动

```python
from utils.autostart import is_autostart_enabled, set_autostart

set_autostart(True)             # 启用开机自启动
set_autostart(False)            # 禁用
print(is_autostart_enabled())   # 查询状态
```

- Windows：在 `Startup` 目录创建 `.bat` 脚本，使用 `pythonw.exe` 无窗口启动
- macOS / Linux：预留接口

### `utils/notifier.py` —— 系统通知

```python
from utils.notifier import send_notification
send_notification("标题", "消息内容", timeout=10)
```

降级链：`plyer` 原生通知 → `ctypes.MessageBoxW` 弹窗 → `print` 控制台

### `utils/search_engine.py` —— 全局搜索

```python
from utils.search_engine import search_all
results = search_all("火锅")
# 返回: [{"type": "transaction", "type_label": "📊 记账", "title": ..., "detail": ..., "url": ...}, ...]
```

跨四张表模糊搜索，每表最多 20 条，按日期倒序排列。

---

## 项目结构

```
my_life_toolbox/
├── app.py                      # 主入口（悬浮窗优先 + 插件加载 + NiceGUI 后台）
├── config.json                 # 用户配置（置顶/自动Web/透明度/城市）
├── README.md                   # 本文件
├── seed_test_data.py           # 测试数据生成脚本
│
├── core/                       # 核心模块
│   ├── database.py             # ORM 模型（含 Setting 键值表）
│   └── scheduler.py            # 定时任务引擎
│
├── plugins/                    # 插件系统
│   ├── __init__.py             # BasePlugin + PluginLoader
│   ├── finance_plugin.py       # 记账插件
│   ├── diary_plugin.py         # 日记插件
│   ├── calendar_plugin.py      # 日历日程插件
│   ├── rnote_plugin.py         # Rnote 管理插件
│   ├── gadgets_plugin.py       # 小工具插件
│   └── admin_plugin.py         # 插件管理页面 /admin/plugins
│
├── modules/                    # Web 页面模块（@ui.page 路由）
│   ├── layout.py               # 共享布局（动态菜单注入）
│   ├── dashboard.py            # 首页仪表盘  /
│   ├── calendar_feed.py        # 日历日程    /calendar
│   ├── finance.py              # 记账管理    /finance
│   ├── diary.py                # 日记编辑器  /diary
│   ├── rnote_manager.py        # Rnote 管理  /rnote
│   ├── gadgets.py              # 小工具      /gadgets
│   └── settings.py             # 设置        /settings
│
├── utils/                      # 工具模块
│   ├── weather.py              # wttr.in 天气查询
│   ├── ip_tool.py              # IPv4 + IPv6 双栈 IP 查询
│   ├── notifier.py             # 系统原生通知
│   ├── search_engine.py        # 跨表全文搜索
│   └── autostart.py            # 开机自启动管理
│
├── widget/                     # 桌面悬浮窗
│   └── floating_window.py      # tkinter 悬浮窗（Win32 去边框 + 置顶）
│
├── data/                       # 运行时数据（自动创建）
│   ├── toolbox.db              # SQLite 数据库
│   ├── auto_backup/            # 自动备份目录
│   └── classified_notes/       # Rnote 分类归档目录
│
└── static/                     # 静态资源
    └── icon.ico                # 托盘图标（可选）
```

---

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| Web 框架 | NiceGUI (Quasar) | 1.4.30 |
| 桌面悬浮窗 | tkinter + Win32 API | 内置 |
| 数据库 ORM | SQLAlchemy | 2.0.36 |
| 数据库引擎 | SQLite | 内置 |
| 定时任务 | APScheduler | 3.10.4 |
| 系统托盘 | pystray + Pillow | 0.19.0 / 11.1.0 |
| 二维码生成 | qrcode | 7.4.2 |
| HTTP 请求 | requests | 内置 |
| 图表 | ECharts (via NiceGUI) | - |
| ASGI 服务器 | uvicorn | 0.49.0 |

---

## 开发与调试

### 单独测试各模块

```bash
# 测试数据库初始化
python core/database.py

# 测试天气获取
python utils/weather.py

# 测试 IP 查询
python utils/ip_tool.py

# 测试系统通知
python utils/notifier.py

# 插入测试数据
python seed_test_data.py
```

### 调试技巧

- **数据库日志**：将 `core/database.py` 中的 `echo=False` 改为 `echo=True` 查看 SQL 语句
- **悬浮窗样式**：修改 `widget/floating_window.py` 中的配色常量（`BG_DARK`、`ACCENT_BLUE` 等）
- **Web 端口**：修改 `app.py` 中的 `NICE_PORT` 常量
- **刷新频率**：修改 `widget/floating_window.py` 中的 `root.after(30000, ...)` 毫秒数
- **备份保留天数**：修改 `core/scheduler.py` 中的 `keep_days=30`

### 退出程序

- 关闭悬浮窗（点击 ✕）
- 系统托盘右键 → ❌ 退出
- 悬浮窗右键 → ❌ 退出

所有退出路径均会：停止定时任务 → 关闭悬浮窗 → 清理后台线程 → 进程完全退出。
