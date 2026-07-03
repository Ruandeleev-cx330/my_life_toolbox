"""
小工具抽屉
路由：/gadgets
功能：内外网 IP 展示 + 二维码生成器 + 密码生成器
"""

import io
import random
import string
from base64 import b64encode

import qrcode
from nicegui import ui

from modules.layout import add_header
from utils.ip_tool import (
    get_external_ipv4,
    get_external_ipv6,
    get_internal_ipv4,
    get_internal_ipv6,
)


# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════

def _make_qr_data_uri(text: str, size: int = 240) -> str:
    """将文本生成 QR 码，返回 data:image/png;base64 格式"""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").resize((size, size))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + b64encode(buf.getvalue()).decode()


def _generate_password(length: int = 16, use_digits: bool = True, use_symbols: bool = True) -> str:
    """生成随机密码"""
    chars = string.ascii_letters
    if use_digits:
        chars += string.digits
    if use_symbols:
        chars += "!@#$%^&*"
    return "".join(random.choice(chars) for _ in range(length))


# ══════════════════════════════════════════════════════════════════
# 页面入口
# ══════════════════════════════════════════════════════════════════

@ui.page("/gadgets")
def gadgets_page():
    """小工具页面"""

    add_header()

    # ── 面包屑 ──────────────────────────────────────────────
    with ui.row().classes("items-center gap-4 px-3 pt-2 pb-1"):
        ui.link("🏠 首页", target="/").classes("text-grey-6 no-underline")
        ui.label("›").classes("text-grey-6")
        ui.label("🧰 小工具").classes("text-h6 font-bold")

    ui.separator()

    # ══════════════════════════════════════════════════════════
    # IP 信息（内网 + 公网，各显 v4/v6）
    # ══════════════════════════════════════════════════════════

    v4_local = get_internal_ipv4()
    v6_local = get_internal_ipv6()
    v4_public = get_external_ipv4()
    v6_public = get_external_ipv6()

    def _ip_card(title: str, v4: str, v6: str):
        with ui.card().classes("flex-1"):
            ui.label(title).classes("text-h6 font-bold pb-2")
            # v4 行
            with ui.row().classes("items-center gap-2 pb-1"):
                ui.label("v4").classes("text-caption font-bold text-blue-6 w-6")
                ui.label(v4).classes("font-mono text-blue-6")
                ui.button("copy", on_click=lambda: _copy_and_notify(v4)).props("flat dense size=sm")
            # v6 行
            with ui.row().classes("items-center gap-2"):
                ui.label("v6").classes("text-caption font-bold text-purple-6 w-6")
                ui.label(v6).classes("font-mono text-purple-6 text-caption")
                ui.button("copy", on_click=lambda: _copy_and_notify(v6)).props("flat dense size=sm")

    with ui.row().classes("gap-4 px-3 pt-2 w-full"):
        _ip_card("内网 IP", v4_local, v6_local)
        _ip_card("公网 IP", v4_public, v6_public)

    # ══════════════════════════════════════════════════════════
    # 第二行：二维码生成器
    # ══════════════════════════════════════════════════════════
    ui.separator().classes("my-4")

    with ui.row().classes("gap-4 px-3 w-full"):
        # 左侧：输入区
        with ui.card().classes("flex-1"):
            ui.label("📱 二维码生成器").classes("text-h6 font-bold pb-3")

            qr_input = (
                ui.textarea(label="输入文本或网址", placeholder="https://example.com").classes("w-full").props("rows=3")
            )

            qr_preview = ui.column().classes("items-center w-full pt-3")

            def _gen_qr():
                text = qr_input.value.strip()
                if not text:
                    ui.notify("请输入文本或网址", type="warning")
                    return
                try:
                    uri = _make_qr_data_uri(text)
                    qr_preview.clear()
                    with qr_preview:
                        ui.image(uri).style("width: 240px; height: 240px;")
                        ui.label(f"✅ 已生成：{text[:30]}{'...' if len(text) > 30 else ''}").classes(
                            "text-caption text-grey-6 pt-2"
                        )
                except Exception as e:
                    ui.notify(f"生成失败：{e}", type="error")

            ui.button("🔮 生成二维码", on_click=_gen_qr).props("color=primary").classes("mt-2")

            with qr_preview:
                ui.label("（输入内容后点击生成）").classes("text-grey-6 p-8")

    # ══════════════════════════════════════════════════════════
    # 第三行：密码生成器
    # ══════════════════════════════════════════════════════════
    ui.separator().classes("my-4")

    with ui.card().classes("w-full mx-3"):
        ui.label("🔑 密码生成器").classes("text-h6 font-bold pb-3")

        with ui.row().classes("items-end gap-4"):
            length_input = ui.number(label="长度", value=16, min=6, max=64).classes("w-24")
            use_digits = ui.checkbox("包含数字", value=True)
            use_symbols = ui.checkbox("包含符号", value=True)

            pwd_display = ui.input(label="生成的密码").classes("flex-1").props("readonly")

            def _gen_pwd():
                pwd = _generate_password(
                    length=int(length_input.value),
                    use_digits=use_digits.value,
                    use_symbols=use_symbols.value,
                )
                pwd_display.value = pwd
                ui.notify("密码已生成 ✅")

            ui.button("🎲 生成", on_click=_gen_pwd).props("color=primary")
            ui.button(
                "📋 复制",
                on_click=lambda: _copy_and_notify(pwd_display.value),
            ).props("flat")


def _copy_and_notify(text: str):
    """复制文本到剪贴板（通过 JS）并弹出通知"""
    if not text:
        ui.notify("没有可复制的内容", type="warning")
        return
    # 转义单引号防止 JS 注入
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    ui.run_javascript(f"navigator.clipboard.writeText('{escaped}')")
    ui.notify(f"已复制：{text}")
