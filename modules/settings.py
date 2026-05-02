"""
Unified app settings management.
Extends the existing config.json with locale, theme_mode, always_on_top.
Also provides the shared settings dialog.
"""
import os
import json
import flet as ft
from modules.i18n import _, set_locale, get_locale, LOCALES

CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json",
)


def load_app_settings():
    """Load all app settings from config.json. Returns dict with defaults."""
    defaults = {
        "output_dir": _get_desktop_path(),
        "locale": "zh-CN",
        "theme_mode": "light",
        "always_on_top": False,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "output_dir" in data and os.path.isdir(data["output_dir"]):
                defaults["output_dir"] = data["output_dir"]
            if "locale" in data and data["locale"] in LOCALES:
                defaults["locale"] = data["locale"]
            if "theme_mode" in data and data["theme_mode"] in ("light", "dark"):
                defaults["theme_mode"] = data["theme_mode"]
            if "always_on_top" in data:
                defaults["always_on_top"] = bool(data["always_on_top"])
        except Exception:
            pass
    return defaults


def save_app_settings(output_dir=None, locale=None, theme_mode=None, always_on_top=None):
    """Save settings. Only provided kwargs are updated."""
    current = load_app_settings()
    if output_dir is not None:
        current["output_dir"] = output_dir
    if locale is not None:
        current["locale"] = locale
    if theme_mode is not None:
        current["theme_mode"] = theme_mode
    if always_on_top is not None:
        current["always_on_top"] = always_on_top
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def _get_desktop_path():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def apply_theme(page: ft.Page, theme_mode: str):
    """Apply light/dark theme to page."""
    if theme_mode == "dark":
        page.theme_mode = ft.ThemeMode.DARK
    else:
        page.theme_mode = ft.ThemeMode.LIGHT


# ===================== Theme Color Helpers =====================

def get_card_bg(mode: str):
    """Container card background color for light/dark mode."""
    return ft.Colors.SURFACE_CONTAINER_HIGHEST if mode == "dark" else ft.Colors.WHITE


def get_log_bg(mode: str):
    """Log panel background color."""
    return ft.Colors.SURFACE_CONTAINER_HIGHEST if mode == "dark" else ft.Colors.GREY_100


def get_topbar_bg(mode: str):
    """Top bar background color."""
    return ft.Colors.SURFACE_CONTAINER_HIGHEST if mode == "dark" else ft.Colors.GREY_100


def get_border_color(mode: str):
    """Border / outline color for containers."""
    return ft.Colors.OUTLINE_VARIANT


def get_log_text_color(mode: str):
    """Log entry text color."""
    return ft.Colors.GREY_400 if mode == "dark" else ft.Colors.GREY_800


def get_dir_text_color(mode: str):
    """Directory path text color."""
    return ft.Colors.BLUE_300 if mode == "dark" else ft.Colors.BLUE_700


# ===================== Shared Settings Dialog =====================

def build_settings_dialog(page: ft.Page, on_close=None, show_startup=False,
                          on_startup_change=None, is_startup_enabled=False,
                          on_language_changed=None):
    """Build a shared settings AlertDialog.

    Args:
        page: Flet Page instance
        on_close: callback after dialog closes
        show_startup: whether to show the "Start with Windows" toggle (PDF only)
        on_startup_change: callable(enabled: bool) -> bool (returns success)
        is_startup_enabled: current startup state
        on_language_changed: callable() called when language is saved (triggers UI rebuild)
    """
    settings = load_app_settings()

    # -- Language selector --
    locale_options = []
    for code, label in LOCALES.items():
        locale_options.append(ft.dropdown.Option(code, label))
    locale_dd = ft.Dropdown(
        label=_("语言"),
        value=settings["locale"],
        width=200,
        options=locale_options,
    )

    # -- Theme toggle --
    theme_switch = ft.Switch(value=(settings["theme_mode"] == "dark"))
    theme_label = ft.Text(
        _("暗色模式") if not theme_switch.value else _("暗色模式"),
        size=14,
        weight=ft.FontWeight.W_500,
    )

    def on_theme_change(e):
        theme_label.value = _("暗色模式") if theme_switch.value else _("暗色模式")
        page.update()

    theme_switch.on_change = on_theme_change

    # -- Always on top toggle --
    top_switch = ft.Switch(value=page.window.always_on_top)

    # -- Startup toggle (optional) --
    startup_switch = None
    if show_startup:
        startup_switch = ft.Switch(value=is_startup_enabled)

    has_changes = [False]

    def on_save(e):
        new_locale = locale_dd.value
        new_theme = "dark" if theme_switch.value else "light"
        new_top = top_switch.value

        old_locale = settings["locale"]
        language_did_change = (new_locale != old_locale)

        # Apply changes
        set_locale(new_locale)
        apply_theme(page, new_theme)
        page.window.always_on_top = new_top

        # Persist
        save_app_settings(locale=new_locale, theme_mode=new_theme, always_on_top=new_top)
        has_changes[0] = True

        if show_startup and startup_switch and on_startup_change:
            on_startup_change(startup_switch.value)

        page.close(dlg)
        if on_close:
            on_close()

        # Rebuild UI if language changed
        if language_did_change and on_language_changed:
            on_language_changed()

    dlg = ft.AlertDialog(
        title=ft.Row([
            ft.Icon(ft.Icons.SETTINGS, size=20),
            ft.Text(_("设置"), size=18, weight=ft.FontWeight.W_500),
        ]),
        content=ft.Column([
            # Language
            ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(_("语言"), weight=ft.FontWeight.W_500, size=14),
                        ft.Text(_("选择界面语言"), size=12, color=ft.Colors.GREY_600),
                    ], expand=True),
                    locale_dd,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=8),
            ),
            ft.Divider(height=1),
            # Theme
            ft.Container(
                content=ft.Row([
                    ft.Column([
                        theme_label,
                        ft.Text(_("切换暗色/亮色主题"), size=12, color=ft.Colors.GREY_600),
                    ], expand=True),
                    theme_switch,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=8),
            ),
            ft.Divider(height=1),
            # Always on top
            ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(_("窗口置顶"), weight=ft.FontWeight.W_500, size=14),
                        ft.Text(_("保持窗口始终在其他窗口之上"), size=12, color=ft.Colors.GREY_600),
                    ], expand=True),
                    top_switch,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=8),
            ),
            # Startup (optional)
            *([
                ft.Divider(height=1),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(_("开机自启动"), weight=ft.FontWeight.W_500, size=14),
                            ft.Text(_("系统启动时自动运行本程序"), size=12, color=ft.Colors.GREY_600),
                        ], expand=True),
                        startup_switch,
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(vertical=8),
                ),
            ] if show_startup and startup_switch else []),
            # Drag-and-drop info
            ft.Divider(height=1),
            ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(_("拖放导入"), weight=ft.FontWeight.W_500, size=14),
                        ft.Text(
                            _("将 PDF / ZIP 文件直接拖入窗口即可导入")
                            if show_startup
                            else _("将任意文件直接拖入窗口即可导入"),
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                    ], expand=True),
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.GREEN_600, size=20),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=8),
            ),
        ], spacing=0, width=400),
        actions=[
            ft.TextButton(_("关闭"), on_click=lambda _: page.close(dlg)),
            ft.FilledButton(_("保存设置"), on_click=on_save),
        ],
    )
    page.open(dlg)
    return dlg

dummy_page = None  # for type hint
