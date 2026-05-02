import os
import asyncio
import tkinter as tk

from PIL import Image, ImageTk
import flet as ft

from modules.i18n import _, set_locale, get_locale

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
    tk.Label(inner, text=_("全能工具箱"), font=('Microsoft YaHei', 22, 'bold'),
             bg='white', fg='#0D47A1').pack(pady=(8, 0))

    # 版本
    tk.Label(inner, text=_("Version 1.0"), font=('Segoe UI', 10),
             bg='white', fg='#9E9E9E').pack(pady=(2, 14))

    # 进度条（Canvas 绘制）
    canvas = tk.Canvas(inner, width=290, height=6, bg='white', highlightthickness=0)
    canvas.pack()
    canvas.create_rectangle(0, 0, 290, 6, fill='#E3F2FD', outline='')
    bar_fg = canvas.create_rectangle(0, 0, 0, 6, fill='#1E88E5', outline='')

    # 状态文字
    status_var = tk.StringVar(value=_("正在初始化…"))
    tk.Label(inner, textvariable=status_var, font=('Microsoft YaHei', 9),
             bg='white', fg='#757575').pack(pady=(10, 0))

    # 版权
    tk.Label(inner, text=_("© 2026 Toolbox. All rights reserved."),
             font=('Segoe UI', 8), bg='white', fg='#BDBDBD').pack(pady=(14, 0))

    # ========== 加载步骤 ==========
    steps = [
        (_("正在初始化组件…"), 0.1),
        (_("正在加载 格式转换器…"), 0.25),
        (_("正在加载 PDF 转换器…"), 0.45),
        (_("正在加载 视频转换器…"), 0.65),
        (_("正在加载 YouTube 下载器…"), 0.85),
        (_("准备就绪"), 1.0),
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
    from modules.settings import load_app_settings, apply_theme

    # 加载持久化设置
    app_settings = load_app_settings()
    set_locale(app_settings["locale"])

    # 窗口配置
    page.window.width = 1100
    page.window.height = 820
    page.window.resizable = False
    page.title = _("全能工具箱")
    apply_theme(page, app_settings["theme_mode"])
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.window.always_on_top = app_settings["always_on_top"]

    # 设置应用图标
    icon_path = os.path.join(_SCRIPT_DIR, "icons", "repost.ico")
    if os.path.exists(icon_path):
        page.window.icon = icon_path

    if not _PYPDF2_OK:
        import tkinter.messagebox as mb
        mb.showerror(_("缺少依赖"), _("请先在终端运行：\npip install PyPDF2"))
        page.window.close()
        return

    # ========== UI 构建函数（启动 + 语言切换时复用） ==========
    format_ui = FormatConverterUI(page)
    pdf_ui = PDFConverterUI(page)

    selected_tab = [0]  # mutable box, preserved across rebuilds
    current_tabs = [None]  # mutable box, keeps reference to latest main_tabs

    def build_all_tabs():
        """Rebuild all tab contents. Called on startup and language change."""
        # Reload settings to pick up fresh locale/theme after save
        fresh = load_app_settings()
        set_locale(fresh["locale"])
        page.title = _("全能工具箱")

        fmt_top_bar, fmt_content, fmt_log = format_ui.build()
        pdf_top_bar, pdf_tabs, pdf_log = pdf_ui.build()
        video_content = build_video_converter(page)
        youtube_content = build_youtube_downloader(page)

        main_tabs = ft.Tabs(
            selected_index=selected_tab[0],
            scrollable=False,
            animation_duration=200,
            on_change=lambda e: selected_tab.__setitem__(0, e.control.selected_index),
            tabs=[
                ft.Tab(
                    text=_("格式转换器"),
                    icon=ft.Icons.SWAP_HORIZ,
                    content=ft.Column([
                        fmt_top_bar, fmt_content, fmt_log,
                    ], expand=True, spacing=0),
                ),
                ft.Tab(
                    text=_("PDF转换器"),
                    icon=ft.Icons.PICTURE_AS_PDF,
                    content=ft.Column([
                        pdf_top_bar, pdf_tabs, pdf_log,
                    ], expand=True, spacing=0),
                ),
                ft.Tab(
                    text=_("视频转换器"),
                    icon=ft.Icons.VIDEO_FILE,
                    content=video_content,
                ),
                ft.Tab(
                    text=_("YouTube下载"),
                    icon=ft.Icons.YOUTUBE_SEARCHED_FOR,
                    content=youtube_content,
                ),
            ],
            expand=True,
        )
        return main_tabs, format_ui

    main_tabs, format_ui_obj = build_all_tabs()
    page.add(main_tabs)
    format_ui_obj.add_log(_("程序已启动，等待操作..."))

    # 存储语言切换重建回调
    def on_rebuild_ui():
        page.clean()
        new_tabs, fmt_ui = build_all_tabs()
        current_tabs[0] = new_tabs
        page.add(new_tabs)
        fmt_ui.add_log(_("界面语言已切换"))
        page.update()

    page._on_rebuild_ui = on_rebuild_ui
    current_tabs[0] = main_tabs
    page.update()

    # ========== 统一拖放处理 ==========
    def handle_drop(files):
        if not files:
            return
        tabs = current_tabs[0]
        if tabs is None:
            return
        idx = tabs.selected_index
        if idx == 0:
            format_ui_obj.handle_drop(files)
        elif idx == 1:
            pdf_ui._handle_dropped_files(files)

    async def poll_drops():
        await asyncio.sleep(1.0)
        ok, msg = enable_dragdrop(_("全能工具箱"))
        if ok:
            format_ui.add_log(_("✅ {msg}", msg=msg))
        else:
            format_ui.add_log(_("⚠ 拖放未能启用: {msg}", msg=msg))
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
