"""日历日程插件"""
from plugins import BasePlugin


class CalendarPlugin(BasePlugin):
    name = "calendar"
    title = "日历日程"
    version = "1.0.0"
    author = "MLT"
    description = "月历视图 + Feed 时间线，展示日记、待办、记账流水"

    def register(self):
        import modules.calendar_feed  # noqa: F401

    def menu_item(self):
        return ("日历日程", "/calendar")
