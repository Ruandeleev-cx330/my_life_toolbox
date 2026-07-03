"""小工具插件"""
from plugins import BasePlugin


class GadgetsPlugin(BasePlugin):
    name = "gadgets"
    title = "小工具"
    version = "1.0.0"
    author = "MLT"
    description = "本机 IP 展示 + 二维码生成器 + 密码生成器"

    def register(self):
        import modules.gadgets  # noqa: F401

    def menu_item(self):
        return ("小工具", "/gadgets")
