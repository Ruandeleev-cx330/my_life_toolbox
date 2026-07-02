"""
Rnote 文件分类管理器
路由：/rnote
功能：扫描 .rnote 文件 → 多选 → 批量归类移动 → 记录数据库（见 CLAUDE.me §4）

.rnote 本质是 zip 压缩包（含 document.svg + document.xml），程序不做内容解析，
仅基于用户设定的分类标签进行文件移动和数据库记录。

回滚机制：original_path 始终保留在数据库中，支持未来"撤销归类"功能。
"""

import shutil
from datetime import date, datetime
from pathlib import Path

from nicegui import ui

from core.database import DATA_DIR, RnoteFile, SessionLocal
from modules.layout import add_header

# ── 归类目标：项目目录下的 data/classified_notes/ ─────────────────
CLASSIFIED_DIR = DATA_DIR / "classified_notes"

# ── 页面级状态 ──────────────────────────────────────────────────
_scan_results: list[dict] = []  # 每项: {path, filename, original_path, size, modified, status, selected}
_folder_path: str = ""
_target_category: str = ""


# ── 工具函数 ────────────────────────────────────────────────────
def _format_size(size_bytes: int) -> str:
    """将字节数转为可读字符串"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _browse_folder() -> str | None:
    """打开系统原生文件夹选择对话框，返回所选路径（可能阻塞 UI 1-2 秒）"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="选择笔记根目录")
        root.destroy()
        return path if path else None
    except Exception:
        # 如果 tkinter 不可用（极少数精简 Python），静默失败
        return None


def _resolve_dest_path(target_base: Path, filename: str) -> Path:
    """
    解决目标路径的重名冲突。
    若 target_base/filename 已存在，依次尝试 filename → filename (1) → filename (2) ...
    返回最终的目标路径。
    """
    dest = target_base / filename
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    counter = 1
    while True:
        dest = target_base / f"{stem} ({counter}){suffix}"
        if not dest.exists():
            return dest
        counter += 1


# ══════════════════════════════════════════════════════════════════
# 扫描逻辑
# ══════════════════════════════════════════════════════════════════

def _do_scan(folder_path: str):
    """
    递归扫描指定目录下所有 .rnote 文件，填充 _scan_results。
    同时查询数据库，标注每个文件的分类状态。
    """
    global _scan_results
    _scan_results = []

    path_str = folder_path.strip()
    if not path_str:
        ui.notify("请输入笔记根目录路径", type="warning")
        return

    root = Path(path_str)
    if not root.exists():
        ui.notify(f"目录不存在：{path_str}", type="error")
        return
    if not root.is_dir():
        ui.notify(f"路径不是目录：{path_str}", type="error")
        return

    # 递归查找所有 .rnote 文件
    rnote_files = list(root.rglob("*.rnote"))

    if not rnote_files:
        ui.notify("未找到任何 .rnote 文件", type="warning")
        _render_table.refresh()
        return

    # 查询数据库中已有的分类记录（用于状态标注）
    db = SessionLocal()
    try:
        classified_map = {}
        for r in db.query(RnoteFile).all():
            classified_map[r.original_path] = r.target_category
            # 同时登记 target_path，以便扫描分类目录时也能匹配到
            if r.target_path:
                classified_map[r.target_path] = r.target_category
    finally:
        db.close()

    # 构建结果列表
    for f in rnote_files:
        try:
            stat = f.stat()
        except OSError:
            continue  # 跳过无法读取的文件

        original = str(f)
        existing_category = classified_map.get(original)

        _scan_results.append(
            {
                "path": f,
                "filename": f.name,
                "original_path": original,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "status": f"已归类至「{existing_category}」" if existing_category else "未分类",
                "classified": existing_category is not None,
                "selected": False,
            }
        )

    ui.notify(f"找到 {len(_scan_results)} 个 .rnote 文件")
    _render_table.refresh()


# ══════════════════════════════════════════════════════════════════
# 归类执行逻辑
# ══════════════════════════════════════════════════════════════════

def _do_classify(category: str):
    """
    将选中的文件移动到 data/classified_notes/[category]/ 下，
    处理重名冲突，更新 RnoteFile 数据库记录。
    """
    global _scan_results

    category = category.strip()
    if not category:
        ui.notify("请输入目标分类名称", type="warning")
        return

    selected = [item for item in _scan_results if item["selected"]]
    if not selected:
        ui.notify("请至少选择一个文件", type="warning")
        return

    # 目标目录：项目 data/classified_notes/{category}/
    target_base = CLASSIFIED_DIR / category
    target_base.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    success = 0
    skipped = 0
    errors: list[str] = []

    for item in selected:
        src: Path = item["path"]
        dest = _resolve_dest_path(target_base, item["filename"])

        # ── 检查源文件是否仍存在 ──
        if not src.exists():
            skipped += 1
            errors.append(f"⚠️ 文件不存在（可能已被移动）：{item['filename']}")
            continue

        # ── 执行移动 ──
        try:
            shutil.move(str(src), str(dest))
        except PermissionError:
            errors.append(f"❌ 权限不足：{item['filename']}")
            continue
        except OSError as e:
            errors.append(f"❌ 系统错误（{item['filename']}）：{e}")
            continue

        # ── 更新数据库 ──
        try:
            existing = (
                db.query(RnoteFile)
                .filter(RnoteFile.original_path == item["original_path"])
                .first()
            )

            if existing:
                # 已存在记录 → 更新归类信息
                existing.target_category = category
                existing.target_path = str(dest)
                existing.file_size = item["size"]
                existing.last_modified = item["modified"]
                existing.classified_date = date.today()
            else:
                # 新记录
                db.add(
                    RnoteFile(
                        original_path=item["original_path"],
                        filename=item["filename"],
                        target_category=category,
                        target_path=str(dest),
                        file_size=item["size"],
                        last_modified=item["modified"],
                        classified_date=date.today(),
                        tags="",
                    )
                )
            db.commit()
            success += 1
        except Exception as e:
            db.rollback()
            errors.append(f"❌ 数据库写入失败（{item['filename']}）：{e}")
            # 尝试回滚文件移动
            try:
                shutil.move(str(dest), str(src))
            except Exception:
                pass
            continue

    db.close()

    # ── 结果通知 ──
    if success > 0:
        ui.notify(f"✅ 成功归类 {success} 个文件到「{category}」", type="positive")
    if skipped > 0:
        ui.notify(f"⚠️ 跳过 {skipped} 个不存在的文件", type="warning")
    for err in errors:
        ui.notify(err, type="error", timeout=5000)

    # ── 重新扫描，刷新表格 ──
    _do_scan(_folder_path)


# ══════════════════════════════════════════════════════════════════
# 文件表格渲染（refreshable）
# ══════════════════════════════════════════════════════════════════

@ui.refreshable
def _render_table():
    """渲染扫描结果表格：全选 + 逐行复选框 + 文件信息"""

    if not _scan_results:
        with ui.card().classes("w-full p-6 text-center"):
            ui.label("📭 暂无扫描结果").classes("text-grey-6")
            ui.label("请先选择笔记根目录，点击「🔍 扫描」开始。").classes("text-caption text-grey-5")
        return

    # ── 已分类 / 未分类计数 ──
    new_count = sum(1 for item in _scan_results if not item["classified"])
    classified_count = len(_scan_results) - new_count
    with ui.row().classes("items-center gap-4 pb-1"):
        ui.label(
            f"共 {len(_scan_results)} 个文件 · 🆕 未分类 {new_count} · 📦 已归类 {classified_count}"
        ).classes("text-caption text-grey-6")

    # ── 全选 ──
    all_selected = all(item["selected"] for item in _scan_results)

    def _toggle_all(e):
        for item in _scan_results:
            item["selected"] = e.value
        # 不刷新整个表格，只更新单个复选框会丢失引用；用 refresh 更干净
        _render_table.refresh()

    with ui.row().classes(
        "items-center gap-2 py-2 px-3 bg-grey-2 rounded font-bold text-caption"
    ):
        ui.checkbox("全选", value=all_selected, on_change=_toggle_all)
        ui.label("文件名").classes("flex-1")
        ui.label("大小").classes("w-20")
        ui.label("修改时间").classes("w-36")
        ui.label("状态").classes("w-28")

    # ── 文件行 ──
    with ui.scroll_area().classes("w-full").style("max-height: 340px"):
        for i, item in enumerate(_scan_results):
            # 闭包捕获当前索引
            def _make_on_check(idx: int):
                def _on_check(e):
                    _scan_results[idx]["selected"] = e.value

                return _on_check

            status_color = "text-blue-6" if item["classified"] else "text-grey-6"

            with ui.row().classes(
                "items-center gap-2 py-1 px-3 border-b border-grey-2"
            ):
                ui.checkbox(value=item["selected"], on_change=_make_on_check(i))
                ui.label(item["filename"]).classes("flex-1 text-sm")
                ui.label(_format_size(item["size"])).classes("w-20 text-caption text-grey-6")
                ui.label(item["modified"].strftime("%Y-%m-%d %H:%M")).classes(
                    "w-36 text-caption text-grey-6"
                )
                ui.label(item["status"]).classes(f"w-28 text-caption {status_color}")

    # ── 分类操作栏（有扫描结果时才显示）────────────────────────
    ui.separator().classes("my-3")

    global _target_category

    with ui.row().classes("items-end gap-3 w-full px-1"):
        category_input = (
            ui.input(
                label="🏷️ 目标分类名",
                placeholder="例如：数学、物理、项目笔记...",
                value=_target_category,
            )
            .classes("flex-1")
            .props("clearable")
        )

        def _on_execute():
            global _target_category
            _target_category = category_input.value or ""
            selected_count = sum(1 for item in _scan_results if item["selected"])
            if selected_count == 0:
                ui.notify("请先在表格中勾选要归类的文件", type="warning")
                return
            if not _target_category.strip():
                ui.notify("请输入目标分类名称", type="warning")
                return
            _do_classify(_target_category)

        ui.button(
            "🚀 执行归类",
            on_click=_on_execute,
        ).props("color=positive").classes("text-lg")


# ══════════════════════════════════════════════════════════════════
# 页面入口：/rnote
# ══════════════════════════════════════════════════════════════════

@ui.page("/rnote")
def rnote_manager_page():
    """Rnote 文件分类管理器"""

    global _folder_path
    add_header()

    # ── 面包屑导航 ──────────────────────────────────────────
    with ui.row().classes("items-center gap-4 px-3 pt-2 pb-1"):
        ui.link("🏠 首页", target="/").classes("text-grey-6 no-underline")
        ui.label("›").classes("text-grey-6")
        ui.link("📅 日历", target="/calendar").classes("text-grey-6 no-underline")
        ui.label("›").classes("text-grey-6")
        ui.label("📂 Rnote 管理器").classes("text-h6 font-bold")

    ui.separator()

    # ── 操作说明卡片 ────────────────────────────────────────
    with ui.card().classes("w-full mb-3 p-3 bg-blue-50"):
        ui.label(
            "📋 使用流程：选择根目录 → 扫描 .rnote 文件 → 勾选文件 → 填写分类名 → 执行归类"
        ).classes("text-caption")
        ui.label(
            "💡 文件将被移动到「data/classified_notes/[分类名]/」目录下，数据库保留原始路径以便日后撤销。"
        ).classes("text-caption text-grey-6")

    # ── 目录选择 + 扫描按钮 ──────────────────────────────────
    with ui.row().classes("items-end gap-3 w-full px-1"):
        folder_input = (
            ui.input(
                label="📁 笔记根目录",
                placeholder=str(DATA_DIR),
                value=_folder_path,
            )
            .classes("flex-1")
            .props("clearable")
        )

        def _on_browse():
            path = _browse_folder()
            if path:
                folder_input.value = path

        ui.button("📂 浏览...", on_click=_on_browse).props("flat")

        def _on_scan():
            global _folder_path
            _folder_path = folder_input.value or ""
            _do_scan(_folder_path)

        ui.button("🔍 扫描", on_click=_on_scan).props("color=primary")

    ui.separator().classes("my-2")

    # ── 扫描结果表格（含分类操作栏，随扫描结果刷新）──────────
    _render_table()
