"""日记插件"""
from plugins import BasePlugin


class DiaryPlugin(BasePlugin):
    name = "diary"
    title = "写日记"
    version = "1.0.0"
    author = "MLT"
    description = "按日期存取 Markdown 日记，支持实时预览和心情标记"

    def register(self):
        import modules.diary  # noqa: F401

    def menu_item(self):
        return ("写日记", "/diary")
