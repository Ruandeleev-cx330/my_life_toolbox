"""Rnote 笔记管理插件"""
from plugins import BasePlugin


class RnotePlugin(BasePlugin):
    name = "rnote"
    title = "Rnote 管理器"
    version = "1.0.0"
    author = "MLT"
    description = "扫描 .rnote 文件、批量归类移动、数据库记录"

    def register(self):
        import modules.rnote_manager  # noqa: F401

    def menu_item(self):
        return ("Rnote 管理器", "/rnote")
