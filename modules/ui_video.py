import flet as ft
from modules.i18n import _


def build_video_converter(page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.VIDEO_FILE, size=72, color=ft.Colors.PURPLE_400),
            ft.Container(height=16),
            ft.Text(_("视频转换器"), size=24, weight=ft.FontWeight.BOLD),
            ft.Container(height=8),
            ft.Text(_("即将推出"), size=14, color=ft.Colors.GREY_500),
            ft.Container(height=24),
            ft.Container(content=ft.Divider(), width=300),
            ft.Container(height=16),
            ft.Row([
                _feature_card(_("视频格式转换"), _("MP4, AVI, MKV, MOV, WebM 等")),
                _feature_card(_("分辨率调整"), _("支持 4K / 1080p / 720p 等")),
                _feature_card(_("音频提取"), _("从视频中提取音频轨道")),
                _feature_card(_("批量处理"), _("一次转换多个视频文件")),
            ], spacing=16, wrap=True, alignment=ft.MainAxisAlignment.CENTER),
        ], alignment=ft.MainAxisAlignment.CENTER,
           horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        expand=True,
        alignment=ft.alignment.center,
        padding=ft.padding.all(40),
    )


def _feature_card(title: str, desc: str) -> ft.Container:
    return ft.Container(
        content=ft.Column([
            ft.Text(title, size=14, weight=ft.FontWeight.W_500),
            ft.Text(desc, size=12, color=ft.Colors.GREY_500),
        ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.padding.all(20),
        border_radius=12,
        border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
        bgcolor=ft.Colors.WHITE,
        width=220,
    )
