"""
数据保险箱 —— 设置 / 数据管理
路由：/settings
功能：一键导出 JSON 备份 + 一键导入恢复 + 自动备份说明
"""

import json
from datetime import date, datetime
from pathlib import Path

from nicegui import ui

from core.database import (
    BASE_DIR,
    DATA_DIR,
    Diary,
    RnoteFile,
    SessionLocal,
    Todo,
    Transaction,
)
from modules.layout import add_header

# ── 自动备份目录 ────────────────────────────────────────────────
AUTO_BACKUP_DIR = DATA_DIR / "auto_backup"
AUTO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# 序列化 / 反序列化工具
# ══════════════════════════════════════════════════════════════════

def _model_to_dict(obj) -> dict:
    """SQLAlchemy 模型 → 可 JSON 序列化的 dict"""
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        result[col.name] = val
    return result


def _dict_to_model(data: dict, model_class):
    """dict → SQLAlchemy 模型实例（不写入 DB）"""
    from sqlalchemy import Date as SADate, DateTime as SADateTime

    instance = model_class()
    for col in model_class.__table__.columns:
        if col.name in data:
            val = data[col.name]
            if val is not None:
                if isinstance(col.type, (SADate, SADateTime)) and isinstance(val, str):
                    if "T" in val:
                        val = datetime.fromisoformat(val)
                    else:
                        val = date.fromisoformat(val)
            setattr(instance, col.name, val)
    return instance


def _export_all_tables() -> dict:
    """导出全部四张表为 dict"""
    db = SessionLocal()
    try:
        return {
            "transactions": [_model_to_dict(r) for r in db.query(Transaction).all()],
            "todos": [_model_to_dict(r) for r in db.query(Todo).all()],
            "diaries": [_model_to_dict(r) for r in db.query(Diary).all()],
            "rnote_files": [_model_to_dict(r) for r in db.query(RnoteFile).all()],
        }
    finally:
        db.close()


def _import_from_json(filepath: str) -> int:
    """从 JSON 文件恢复数据，返回恢复的总条数"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    table_model_map = {
        "transactions": Transaction,
        "todos": Todo,
        "diaries": Diary,
        "rnote_files": RnoteFile,
    }

    db = SessionLocal()
    total = 0
    try:
        # 按顺序清空并恢复
        for table_name, model_class in table_model_map.items():
            records = data.get(table_name, [])
            # 清空
            db.query(model_class).delete()
            # 恢复
            for record in records:
                instance = _dict_to_model(record, model_class)
                db.add(instance)
                total += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return total


# ══════════════════════════════════════════════════════════════════
# 页面入口
# ══════════════════════════════════════════════════════════════════

@ui.page("/settings")
def settings_page():
    """数据保险箱页面"""

    add_header()

    # ── 面包屑 ──────────────────────────────────────────────
    with ui.row().classes("items-center gap-4 px-3 pt-2 pb-1"):
        ui.link("首页", target="/").classes("text-grey-6 no-underline")
        ui.label(">").classes("text-grey-6")
        ui.label("设置").classes("text-h6 font-bold")

    ui.separator()

    # ══════════════════════════════════════════════════════════
    # 天气城市设置
    # ══════════════════════════════════════════════════════════
    from pathlib import Path as _Path
    _config_path = _Path(__file__).resolve().parent.parent / "config.json"

    def _load_config():
        if _config_path.exists():
            return json.loads(_config_path.read_text(encoding="utf-8"))
        return {}

    def _save_config(cfg: dict):
        _config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    current_cfg = _load_config()

    # ── 开机自启动 ────────────────────────────────────────────
    from utils.autostart import is_autostart_enabled, set_autostart

    with ui.card().classes("w-full mx-3 mt-3"):
        ui.label("开机自启动").classes("text-h6 font-bold pb-2")
        ui.label(
            "启用后，系统启动时自动在后台运行 MLT（悬浮窗 + Web 服务）。"
        ).classes("text-grey-6 pb-3")

        auto_switch = ui.switch(
            value=is_autostart_enabled(),
            on_change=lambda e: _on_autostart(e.value),
        )

        def _on_autostart(enabled: bool):
            ok = set_autostart(enabled)
            if ok:
                ui.notify(f"开机自启动已{'启用' if enabled else '禁用'}")
            else:
                ui.notify("操作失败，请检查权限", type="error")
                auto_switch.value = not enabled  # 回滚开关

        with ui.row().classes("items-center gap-2"):
            auto_switch
            ui.label("开机自动启动 MLT").classes("text-grey-7")

    # ── 天气设置 ──────────────────────────────────────────────

    with ui.card().classes("w-full mx-3 mt-3"):
        ui.label("天气设置").classes("text-h6 font-bold pb-2")
        ui.label("设置天气显示的城市（英文名，如 Beijing、Shanghai、Tokyo）").classes("text-grey-6 pb-3")

        with ui.row().classes("items-end gap-3"):
            city_input = ui.input(
                label="城市", value=current_cfg.get("city", "Beijing"),
            ).classes("w-48")

            def _save_city():
                cfg = _load_config()
                cfg["city"] = city_input.value.strip() or "Beijing"
                _save_config(cfg)
                ui.notify(f"城市已更新为 {cfg['city']}，重启后生效")

            ui.button("保存", on_click=_save_city).props("color=primary")

    # ══════════════════════════════════════════════════════════
    # 一键导出
    # ══════════════════════════════════════════════════════════
    with ui.card().classes("w-full mx-3 mt-3"):
        ui.label("📤 一键导出").classes("text-h6 font-bold pb-2")
        ui.label(
            "将数据库中所有数据（记账、待办、日记、Rnote 分类记录）导出为 JSON 文件，"
            "可用于备份或迁移。"
        ).classes("text-grey-6 pb-3")

        async def _do_export():
            data = _export_all_tables()
            json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            timestamp = date.today().strftime("%Y%m%d_%H%M%S")
            filename = f"backup_{timestamp}.json"
            filepath = DATA_DIR / filename
            filepath.write_text(json_str, encoding="utf-8")
            ui.notify(f"✅ 备份已生成：{filename}")
            ui.download(str(filepath))

        ui.button("📤 导出全部数据", on_click=_do_export).props("color=primary")

    # ══════════════════════════════════════════════════════════
    # 一键导入
    # ══════════════════════════════════════════════════════════
    with ui.card().classes("w-full mx-3 mt-3"):
        ui.label("📥 一键导入").classes("text-h6 font-bold pb-2")
        ui.label(
            "选择一个之前导出的 JSON 备份文件，清空当前数据并恢复。"
        ).classes("text-grey-6 pb-2")
        ui.label("⚠️ 此操作会覆盖现有数据，请确认备份已完成！").classes(
            "text-red-6 text-caption font-bold pb-3"
        )

        uploaded_file = {"data": None, "name": ""}

        def _on_upload(e):
            if e.content:
                uploaded_file["data"] = e.content.read()
                uploaded_file["name"] = e.name or "unknown.json"
                ui.notify(f"📎 已选择：{uploaded_file['name']}")
            else:
                uploaded_file["data"] = None
                uploaded_file["name"] = ""

        ui.upload(
            label="选择 JSON 备份文件",
            on_upload=_on_upload,
            auto_upload=True,
        ).props('accept=".json"').classes("w-full")

        def _confirm_import():
            if not uploaded_file["data"]:
                ui.notify("请先选择一个 JSON 备份文件", type="warning")
                return

            # ── 二次确认弹窗 ──
            with ui.dialog() as dlg:
                with ui.card().style("width: 420px; max-width: 90vw;"):
                    ui.label("⚠️ 确认导入备份？").classes("text-h6 font-bold pb-2")
                    ui.label(
                        f"即将从「{uploaded_file['name']}」恢复数据。\n"
                        "当前所有数据将被清空并替换为备份内容，此操作不可撤销。"
                    ).classes("text-grey-7 pb-3")

                    def _do_import():
                        # 保存上传文件到临时路径
                        tmp_path = DATA_DIR / "_restore_temp.json"
                        tmp_path.write_bytes(uploaded_file["data"])
                        try:
                            count = _import_from_json(str(tmp_path))
                            ui.notify(
                                f"✅ 数据恢复成功！共导入 {count} 条记录。请刷新各页面查看。",
                                type="positive",
                            )
                        except Exception as ex:
                            ui.notify(f"❌ 导入失败：{ex}", type="error")
                        finally:
                            if tmp_path.exists():
                                tmp_path.unlink()
                        dlg.close()

                    with ui.row().classes("gap-2 justify-end w-full"):
                        ui.button("取消", on_click=dlg.close).props("flat")
                        ui.button("⚠️ 确认覆盖", on_click=_do_import).props(
                            "color=negative"
                        )
            dlg.open()

        ui.button(
            "📥 导入备份文件", on_click=_confirm_import
        ).props("color=negative").classes("mt-2")

    # ══════════════════════════════════════════════════════════
    # 自动备份说明
    # ══════════════════════════════════════════════════════════
    with ui.card().classes("w-full mx-3 mt-3"):
        ui.label("自动备份").classes("text-h6 font-bold pb-2")
        ui.label(
            "系统已配置每周日凌晨 3:00 自动在以下目录生成 JSON 备份："
        ).classes("text-grey-6 pb-1")
        ui.label(str(AUTO_BACKUP_DIR)).classes(
            "font-mono text-caption text-blue-6 bg-blue-50 p-2 rounded"
        )
        ui.label(
            "无需手动操作，系统会在后台静默执行。备份文件命名格式：backup_YYYYMMDD.json"
        ).classes("text-caption text-grey-6 pt-2")

    # ══════════════════════════════════════════════════════════
    # 清空全部数据
    # ══════════════════════════════════════════════════════════
    with ui.card().classes("w-full mx-3 mt-3 mb-4"):
        ui.label("清空数据").classes("text-h6 font-bold pb-2")
        ui.label(
            "删除数据库中的所有记录（记账、待办、日记、笔记分类），此操作不可撤销。"
        ).classes("text-grey-6 pb-3")

        def _clear_all():
            with ui.dialog() as dlg:
                with ui.card().style("width: 420px; max-width: 90vw;"):
                    ui.label("确认清空全部数据?").classes("text-h6 font-bold pb-2")
                    ui.label(
                        "即将删除数据库中所有记账、待办、日记和笔记分类记录。\n"
                        "建议先导出备份。此操作不可撤销。"
                    ).classes("text-grey-7 pb-3")

                    def _do_clear():
                        s = SessionLocal()
                        try:
                            s.query(Transaction).delete()
                            s.query(Todo).delete()
                            s.query(Diary).delete()
                            s.query(RnoteFile).delete()
                            s.commit()
                            ui.notify("全部数据已清空", type="positive")
                        except Exception as ex:
                            s.rollback()
                            ui.notify(f"清空失败: {ex}", type="error")
                        finally:
                            s.close()
                        dlg.close()

                    with ui.row().classes("gap-2 justify-end w-full"):
                        ui.button("取消", on_click=dlg.close).props("flat")
                        ui.button("确认清空", on_click=_do_clear).props("color=negative")
            dlg.open()

        ui.button("清空全部数据", on_click=_clear_all).props("color=negative")
