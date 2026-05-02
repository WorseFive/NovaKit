import os
import asyncio
import tkinter as tk

from PIL import Image, ImageTk
import flet as ft

# 修复 Python 3.9 下 Flet 的 isinstance(Union[..., Enum]) 兼容性问题
import flet.core.tabs as _flet_tabs
import flet.core.cupertino_context_menu_action as _flet_ccma
_ICON_TUPLE = (str, ft.Icons, ft.CupertinoIcons)
_flet_tabs.IconValue = _ICON_TUPLE
_flet_ccma.IconValue = _ICON_TUPLE

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 检查 PyPDF2（延迟到 splash 之后）
_PYPDF2_OK = False


def _check_pypdf2():
    global _PYPDF2_OK
    try:
        from PyPDF2 import PdfReader  # noqa: F401
        _PYPDF2_OK = True
    except ImportError:
        pass


def show_splash():
    """Word 2003 风格的独立 Splash Screen —— 屏幕居中，加载完毕后自动关闭。"""
    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.attributes('-topmost', True)
    splash.withdraw()  # 先隐藏，计算好位置再显示

    # 尺寸与屏幕居中
    w, h = 420, 270
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    splash.geometry(f"{w}x{h}+{x}+{y}")

    # 蓝色边框
    frame = tk.Frame(splash, bg='#1565C0', padx=2, pady=2)
    frame.pack(fill='both', expand=True)
    inner = tk.Frame(frame, bg='white')
    inner.pack(fill='both', expand=True)

    # Logo
    logo_path = os.path.join(_SCRIPT_DIR, "icons", "repost.png")
    photo = None
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((56, 56), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            logo_label = tk.Label(inner, image=photo, bg='white')
            logo_label.image = photo
            logo_label.pack(pady=(30, 0))
        except Exception:
            pass

    if photo is None:
        logo_label = tk.Label(inner, text="📦", font=('Segoe UI', 40), bg='white', fg='#1565C0')
        logo_label.pack(pady=(30, 0))

    # 应用名
    tk.Label(inner, text="全能工具箱", font=('Microsoft YaHei', 22, 'bold'),
             bg='white', fg='#0D47A1').pack(pady=(8, 0))

    # 版本
    tk.Label(inner, text="Version 1.0", font=('Segoe UI', 10),
             bg='white', fg='#9E9E9E').pack(pady=(2, 14))

    # 进度条（Canvas 绘制）
    canvas = tk.Canvas(inner, width=290, height=6, bg='white', highlightthickness=0)
    canvas.pack()
    canvas.create_rectangle(0, 0, 290, 6, fill='#E3F2FD', outline='')
    bar_fg = canvas.create_rectangle(0, 0, 0, 6, fill='#1E88E5', outline='')

    # 状态文字
    status_var = tk.StringVar(value="正在初始化…")
    tk.Label(inner, textvariable=status_var, font=('Microsoft YaHei', 9),
             bg='white', fg='#757575').pack(pady=(10, 0))

    # 版权
    tk.Label(inner, text="© 2026 Toolbox. All rights reserved.",
             font=('Segoe UI', 8), bg='white', fg='#BDBDBD').pack(pady=(14, 0))

    # ========== 加载步骤 ==========
    steps = [
        ("正在初始化组件…", 0.1),
        ("正在加载 格式转换器…", 0.25),
        ("正在加载 PDF 转换器…", 0.45),
        ("正在加载 视频转换器…", 0.65),
        ("正在加载 YouTube 下载器…", 0.85),
        ("准备就绪", 1.0),
    ]

    def update_step(idx):
        if idx < len(steps):
            msg, prog = steps[idx]
            status_var.set(msg)
            canvas.coords(bar_fg, 0, 0, int(290 * prog), 6)
            splash.after(250, update_step, idx + 1)
        else:
            splash.after(300, splash.destroy)

    splash.deiconify()  # 显示窗口
    splash.after(150, update_step, 0)
    splash.mainloop()


# ===================== Flet 主程序 =====================
async def main(page: ft.Page):
    from modules.pdf.pdf_ui import PDFConverterUI
    from modules.format.ui_main import FormatConverterUI
    from modules.pdf.dragdrop import enable as enable_dragdrop, get_dropped_files as get_drop
    from modules.ui_video import build_video_converter
    from modules.ui_youtube import build_youtube_downloader

    # 窗口配置
    page.window.width = 1100
    page.window.height = 820
    page.window.resizable = False
    page.title = "全能工具箱"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)

    # 设置应用图标
    icon_path = os.path.join(_SCRIPT_DIR, "icons", "repost.ico")
    if os.path.exists(icon_path):
        page.window.icon = icon_path

    if not _PYPDF2_OK:
        import tkinter.messagebox as mb
        mb.showerror("缺少依赖", "请先在终端运行：\npip install PyPDF2")
        page.window.close()
        return

    # ========== 构建各模块 UI ==========
    format_ui = FormatConverterUI(page)
    fmt_top_bar, fmt_content, fmt_log = format_ui.build()

    pdf_ui = PDFConverterUI(page)
    pdf_top_bar, pdf_tabs, pdf_log = pdf_ui.build()

    video_content = build_video_converter(page)
    youtube_content = build_youtube_downloader(page)

    # ========== 主选项卡 ==========
    main_tabs = ft.Tabs(
        selected_index=0,
        scrollable=False,
        animation_duration=200,
        tabs=[
            ft.Tab(
                text="格式转换器",
                icon=ft.Icons.SWAP_HORIZ,
                content=ft.Column([
                    fmt_top_bar, fmt_content, fmt_log,
                ], expand=True, spacing=0),
            ),
            ft.Tab(
                text="PDF转换器",
                icon=ft.Icons.PICTURE_AS_PDF,
                content=ft.Column([
                    pdf_top_bar, pdf_tabs, pdf_log,
                ], expand=True, spacing=0),
            ),
            ft.Tab(
                text="视频转换器",
                icon=ft.Icons.VIDEO_FILE,
                content=video_content,
            ),
            ft.Tab(
                text="YouTube下载",
                icon=ft.Icons.YOUTUBE_SEARCHED_FOR,
                content=youtube_content,
            ),
        ],
        expand=True,
    )

    page.add(main_tabs)
    format_ui.add_log("程序已启动，等待操作...")
    page.update()

    # ========== 统一拖放处理 ==========
    def handle_drop(files):
        if not files:
            return
        idx = main_tabs.selected_index
        if idx == 0:
            format_ui.handle_drop(files)
        elif idx == 1:
            pdf_ui._handle_dropped_files(files)

    async def poll_drops():
        await asyncio.sleep(1.0)  # 等窗口完全就绪
        ok, msg = enable_dragdrop("全能工具箱")
        if ok:
            format_ui.add_log(f"✅ {msg}")
        else:
            format_ui.add_log(f"⚠ 拖放未能启用: {msg}")
        while True:
            files = get_drop(timeout=0.01)
            if files:
                handle_drop(files)
            await asyncio.sleep(0.3)

    page.run_task(poll_drops)


if __name__ == "__main__":
    # 先做依赖检查（轻量）
    _check_pypdf2()
    # 显示独立 Splash Screen，关闭后启动主程序
    show_splash()
    ft.app(target=main)
