"""
记账插件 —— 将 modules/finance.py 封装为插件

这是插件改造的参考示例，展示如何将现有模块封装为 BasePlugin 子类。
"""

from plugins import BasePlugin


class FinancePlugin(BasePlugin):
    name = "finance"
    title = "记账管理"
    version = "1.0.0"
    author = "MLT"
    description = "月度消费洞察面板 + 收支折线图 + 可增删改的数据表格"

    def register(self):
        """
        注册路由：导入原模块即触发 @ui.page('/finance') 装饰器。
        仅在插件启用时调用，因此禁用后路由不可达。
        """
        import modules.finance  # noqa: F401

    def menu_item(self):
        return ("记账管理", "/finance")

    def on_enable(self):
        print(f"[{self.name}] 插件已启用")

    def on_disable(self):
        print(f"[{self.name}] 插件已禁用")
