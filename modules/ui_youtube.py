import flet as ft
from modules.i18n import _


def build_youtube_downloader(page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.YOUTUBE_SEARCHED_FOR, size=72, color=ft.Colors.RED_400),
            ft.Container(height=16),
            ft.Text(_("YouTube 视频下载"), size=24, weight=ft.FontWeight.BOLD),
            ft.Container(height=8),
            ft.Text(_("即将推出"), size=14, color=ft.Colors.GREY_500),
            ft.Container(height=24),
            ft.Container(content=ft.Divider(), width=300),
            ft.Container(height=16),
            ft.Row([
                _feature_card(_("视频下载"), _("支持 720p / 1080p / 4K")),
                _feature_card(_("音频下载"), _("提取 MP3 / AAC 音频")),
                _feature_card(_("字幕下载"), _("下载多语言字幕")),
                _feature_card(_("播放列表"), _("支持批量下载播放列表")),
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
