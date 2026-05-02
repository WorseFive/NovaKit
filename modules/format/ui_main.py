import os
from datetime import datetime
import flet as ft

from modules.pdf.config import load_config, save_config

# 输入类型 → 可选输出格式
FORMAT_DEFS = {
    "image": {
        "label": "图片",
        "icon": ft.Icons.IMAGE_OUTLINED,
        "color": ft.Colors.ORANGE_400,
        "outputs": ["PDF", "JPG", "PNG", "WebP", "BMP", "TIFF"],
        "exts": ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.heic', '.gif', '.jfif'),
    },
    "video": {
        "label": "视频",
        "icon": ft.Icons.VIDEO_FILE,
        "color": ft.Colors.PURPLE_400,
        "outputs": ["MP4", "MOV", "AVI", "MKV", "WebM", "GIF", "MP3"],
        "exts": ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv'),
    },
    "audio": {
        "label": "音频",
        "icon": ft.Icons.AUDIO_FILE,
        "color": ft.Colors.TEAL_400,
        "outputs": ["MP3", "WAV", "FLAC", "AAC", "OGG"],
        "exts": ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'),
    },
    "document": {
        "label": "文档",
        "icon": ft.Icons.DESCRIPTION,
        "color": ft.Colors.BLUE_400,
        "outputs": ["PDF", "DOCX", "EPUB", "MOBI", "TXT"],
        "exts": ('.pdf', '.docx', '.doc', '.epub', '.mobi', '.txt'),
    },
}


def _detect_type(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    for key, fd in FORMAT_DEFS.items():
        if ext in fd["exts"]:
            return key
    return None


def _type_icon(filepath):
    t = _detect_type(filepath)
    if t and t in FORMAT_DEFS:
        return ft.Icon(FORMAT_DEFS[t]["icon"], color=FORMAT_DEFS[t]["color"], size=20)
    return ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.GREY_400, size=20)


def _default_output(filepath):
    """根据文件类型返回默认输出格式"""
    t = _detect_type(filepath)
    if not t:
        return None
    outputs = FORMAT_DEFS[t]["outputs"]
    # 图片默认 → JPG, 视频默认 → MP4, 音频默认 → MP3, 文档默认 → PDF
    defaults = {"image": "JPG", "video": "MP4", "audio": "MP3", "document": "PDF"}
    default = defaults.get(t, outputs[0])
    return default if default in outputs else outputs[0]


def _outputs_for_files(files):
    """汇总所有文件的可行输出格式"""
    all_outputs = []
    seen_types = set()
    for fp in files:
        t = _detect_type(fp)
        if t and t not in seen_types:
            seen_types.add(t)
            all_outputs.extend(FORMAT_DEFS[t]["outputs"])
    seen = set()
    unique = []
    for o in all_outputs:
        if o not in seen:
            seen.add(o)
            unique.append(o)
    return unique


class FormatConverterUI:
    """格式转换器 UI —— 支持全局/单独两种输出模式。"""

    def __init__(self, page: ft.Page, output_dir: str = None):
        self.page = page
        self.output_dir = output_dir or load_config()
        self.files = []

        # 模式: True = 全局设置, False = 单独设置
        self.use_global = True
        self.global_output = None
        self.global_quality = "high"
        self.global_bitrate = ""

        # 每个文件的独立设置 {filepath: {"output": str, "quality": str, "bitrate": str}}
        self.file_settings = {}

        # 控件引用
        self.log_list = None
        self.dir_text = None
        self.file_list = None
        self.file_count = None
        self.btn_clear = None
        self.btn_convert = None

        # 右侧全局控件
        self.output_dd = None
        self.gear_btn = None
        self.adv_panel = None
        self.adv_visible = False
        self.adv_quality = None
        self.adv_bitrate = None
        self.mode_toggle = None

    def add_log(self, message):
        if self.log_list is None:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_list.controls.append(
            ft.Text(f"[{ts}]  {message}", size=12, color=ft.Colors.GREY_800)
        )
        if len(self.log_list.controls) > 200:
            self.log_list.controls.pop(0)
        self.page.update()

    def show_snack(self, message, is_error=False):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.RED_600 if is_error else ft.Colors.GREEN_700,
            behavior=ft.SnackBarBehavior.FLOATING,
            duration=3000,
        )
        self.page.snack_bar.open = True
        self.page.update()

    # ===================== 文件管理 =====================
    def _on_files_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            for f in e.files:
                if f.path not in self.files:
                    self.files.append(f.path)
            self._after_files_changed()

    def _add_files_via_picker(self, picker):
        picker.pick_files(
            dialog_title="选择要转换的文件",
            allow_multiple=True,
            file_type=ft.FilePickerFileType.ANY,
        )

    def _after_files_changed(self):
        """文件列表变更后统一更新。"""
        # 初始化新文件的独立设置
        for fp in self.files:
            if fp not in self.file_settings:
                def_out = _default_output(fp)
                self.file_settings[fp] = {
                    "output": def_out,
                    "quality": "high",
                    "bitrate": "",
                }

        # 更新全局输出
        all_outputs = _outputs_for_files(self.files)
        if all_outputs:
            if self.global_output not in all_outputs:
                self.global_output = all_outputs[0]
        else:
            self.global_output = None

        self._rebuild_file_list()
        self._update_global_controls()

    def _rebuild_file_list(self):
        self.file_list.controls.clear()
        for i, fpath in enumerate(self.files):
            settings = self.file_settings.get(fpath, {})
            file_output = settings.get("output", "")

            # 单独模式下的输出行
            per_file_row = ft.Row(visible=not self.use_global)
            out_dd = ft.Dropdown(
                value=file_output,
                width=110, text_size=12, dense=True,
                options=[ft.dropdown.Option(o, o) for o in _outputs_for_files([fpath])],
                on_change=lambda e, fp=fpath: self._on_per_file_output(fp, e.control.value),
            )
            per_gear = ft.IconButton(
                icon=ft.Icons.SETTINGS, icon_size=16,
                tooltip="高级选项",
                icon_color=ft.Colors.GREY_500,
                on_click=lambda _, fp=fpath: self._show_per_file_advanced(fp),
            )
            per_file_row.controls = [
                ft.Text("Output:", size=11, color=ft.Colors.GREY_500),
                out_dd,
                per_gear,
            ]
            # store refs for later update
            per_file_row._out_dd = out_dd

            self.file_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.ListTile(
                            leading=_type_icon(fpath),
                            title=ft.Text(os.path.basename(fpath), size=13, max_lines=1),
                            subtitle=ft.Text(fpath, size=11, color=ft.Colors.GREY_500, max_lines=1),
                            trailing=ft.IconButton(
                                icon=ft.Icons.CLOSE, icon_size=18,
                                on_click=lambda _, idx=i: self._remove_file(idx),
                            ),
                            shape=ft.RoundedRectangleBorder(radius=8),
                            content_padding=ft.padding.only(right=4),
                        ),
                        per_file_row,
                    ], spacing=0),
                    border_radius=8,
                )
            )

        self._update_buttons()
        self.page.update()

    def _remove_file(self, idx):
        if 0 <= idx < len(self.files):
            fp = self.files.pop(idx)
            self.file_settings.pop(fp, None)
        self._after_files_changed()

    def _clear_files(self):
        if not self.files:
            return
        dlg = ft.AlertDialog(
            title=ft.Text("确认清空"),
            content=ft.Text(f"确定要清空全部 {len(self.files)} 个文件吗？"),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self.page.close(dlg)),
                ft.FilledButton("清空", on_click=lambda _: self._do_clear(dlg)),
            ],
        )
        self.page.open(dlg)

    def _do_clear(self, dlg):
        self.page.close(dlg)
        self.files.clear()
        self.file_settings.clear()
        self.global_output = None
        self._after_files_changed()
        self.add_log("已清空全部文件")

    def _update_buttons(self):
        n = len(self.files)
        self.btn_clear.disabled = (n == 0)
        self.btn_convert.disabled = (n == 0)
        self.file_count.value = f" ({n} 个文件)" if n else ""

    # ===================== 模式切换 =====================
    def _on_mode_changed(self, e):
        self.use_global = (self.mode_toggle.value == "global")
        self._rebuild_file_list()
        self._update_global_controls()

    # ===================== 全局控制面板 =====================
    def _update_global_controls(self):
        all_outputs = _outputs_for_files(self.files)
        if all_outputs and self.use_global:
            self.output_dd.options = [ft.dropdown.Option(o, o) for o in all_outputs]
            if self.global_output not in all_outputs:
                self.global_output = all_outputs[0]
            self.output_dd.value = self.global_output
            self.output_dd.visible = True
            self.gear_btn.visible = True
        else:
            self.output_dd.visible = False
            self.gear_btn.visible = False
        self.page.update()

    def _on_global_output_change(self, e):
        self.global_output = e.control.value

    def _toggle_advanced(self, e):
        self.adv_visible = not self.adv_visible
        if self.adv_panel:
            self.adv_panel.visible = self.adv_visible
        self.page.update()

    # ===================== 单独模式 =====================
    def _on_per_file_output(self, fp, value):
        if fp in self.file_settings:
            self.file_settings[fp]["output"] = value
        self.add_log(f"{os.path.basename(fp)} → 输出格式: {value}")

    def _show_per_file_advanced(self, fp):
        settings = self.file_settings.get(fp, {})
        quality_dd = ft.Dropdown(
            label="输出质量", value=settings.get("quality", "high"), width=160,
            options=[
                ft.dropdown.Option("low", "低"),
                ft.dropdown.Option("medium", "中"),
                ft.dropdown.Option("high", "高"),
                ft.dropdown.Option("lossless", "无损"),
            ],
        )
        bitrate_field = ft.TextField(
            label="码率 (kbps)", value=settings.get("bitrate", ""),
            width=160, hint_text="留空 = 自动", text_size=13,
        )

        def on_save(e):
            self.file_settings[fp]["quality"] = quality_dd.value
            self.file_settings[fp]["bitrate"] = bitrate_field.value
            self.page.close(dlg)
            self.add_log(f"{os.path.basename(fp)} 高级选项已更新")
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text(f"高级选项 - {os.path.basename(fp)}"),
            content=ft.Column([
                quality_dd,
                bitrate_field,
            ], tight=True, width=280, spacing=12),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self.page.close(dlg)),
                ft.FilledButton("保存", on_click=on_save),
            ],
        )
        self.page.open(dlg)

    # ===================== 全局高级选项 =====================
    def _build_global_advanced_panel(self):
        self.adv_quality = ft.Dropdown(
            label="输出质量", value="high", width=160,
            options=[
                ft.dropdown.Option("low", "低"),
                ft.dropdown.Option("medium", "中"),
                ft.dropdown.Option("high", "高"),
                ft.dropdown.Option("lossless", "无损"),
            ],
        )
        self.adv_bitrate = ft.TextField(
            label="码率 (kbps)", value="", width=160,
            hint_text="留空 = 自动", text_size=13,
        )

        self.adv_panel = ft.Container(
            visible=False,
            content=ft.Column([
                ft.Divider(height=8),
                ft.Text("高级选项", size=13, weight=ft.FontWeight.W_500),
                ft.Row([self.adv_quality, self.adv_bitrate], spacing=12, wrap=True),
            ], spacing=8),
            padding=ft.padding.only(top=4),
        )
        return self.adv_panel

    # ===================== 转换执行 =====================
    def _do_convert(self):
        if not self.files:
            self.show_snack("请先添加文件", is_error=True)
            return
        if self.use_global:
            fmt = self.global_output
            if not fmt:
                self.show_snack("请选择输出格式", is_error=True)
                return
            self.add_log(f"开始转换 {len(self.files)} 个文件 → {fmt}（全局模式）")
        else:
            formats = set(
                self.file_settings.get(f, {}).get("output", "?")
                for f in self.files
            )
            self.add_log(
                f"开始转换 {len(self.files)} 个文件 → "
                + ", ".join(f"{os.path.basename(f)}:{self.file_settings.get(f, {}).get('output', '?')}"
                           for f in self.files)
                + "（单独模式）"
            )
        self.show_snack("转换功能即将实现，当前为界面预览")

    # ===================== 设置 =====================
    def _show_settings(self, _):
        top_switch = ft.Switch(value=self.page.window.always_on_top)

        def on_top_change(e):
            self.page.window.always_on_top = top_switch.value
            self.page.update()

        top_switch.on_change = on_top_change

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.SETTINGS, size=20),
                ft.Text("设置", size=18, weight=ft.FontWeight.W_500),
            ]),
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("窗口置顶", weight=ft.FontWeight.W_500, size=14),
                            ft.Text("保持窗口始终在其他窗口之上", size=12, color=ft.Colors.GREY_600),
                        ], expand=True),
                        top_switch,
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(vertical=8),
                ),
                ft.Divider(height=1),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("拖放导入", weight=ft.FontWeight.W_500, size=14),
                            ft.Text("将任意文件直接拖入窗口即可导入", size=12,
                                    color=ft.Colors.GREY_600),
                        ], expand=True),
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.GREEN_600, size=20),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(vertical=8),
                ),
            ], spacing=0, width=360),
            actions=[
                ft.TextButton("关闭", on_click=lambda _: self.page.close(dlg)),
            ],
        )
        self.page.open(dlg)

    # ===================== 拖放处理 =====================
    def handle_drop(self, files):
        if not files:
            return
        added = 0
        for f in files:
            if f not in self.files:
                self.files.append(f)
                added += 1
        if added > 0:
            self._after_files_changed()
            self.add_log(f"📥 拖放导入 {added} 个文件")

    # ===================== 目录选择 =====================
    def _on_dir_pick(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.output_dir = e.path
            self.dir_text.value = self.output_dir
            save_config(self.output_dir)
            self.add_log(f"输出目录已更改为: {self.output_dir}")

    # ===================== UI 构建 =====================
    def build(self):
        """返回 (top_bar, content, log_panel)。布局与 PDF 转换器一致。"""
        page = self.page

        # --- FilePickers ---
        dir_picker = ft.FilePicker(on_result=self._on_dir_pick)
        file_picker = ft.FilePicker(on_result=self._on_files_pick)
        page.overlay.extend([dir_picker, file_picker])

        # --- 日志 ---
        self.log_list = ft.ListView(expand=True, auto_scroll=True, spacing=2)

        # --- 顶部栏 ---
        self.dir_text = ft.Text(
            self.output_dir, color=ft.Colors.BLUE_700, size=13, italic=True,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
        )
        top_bar = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.FOLDER_OPEN, color=ft.Colors.BLUE_600),
                ft.Text("保存至:", weight=ft.FontWeight.W_500),
                ft.TextButton(
                    "更改目录",
                    icon=ft.Icons.EDIT_LOCATION_OUTLINED,
                    on_click=lambda _: dir_picker.get_directory_path(dialog_title="选择文件保存目录"),
                ),
                self.dir_text,
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS, icon_size=20,
                    tooltip="设置", icon_color=ft.Colors.GREY_600,
                    on_click=self._show_settings,
                ),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            bgcolor=ft.Colors.GREY_100,
            border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )

        # --- 文件列表 (左侧) ---
        self.file_count = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.file_list = ft.ListView(expand=True, spacing=2)

        # --- 模式切换 ---
        self.mode_toggle = ft.RadioGroup(
            value="global",
            content=ft.Row([
                ft.Radio(value="global", label="全局"),
                ft.Radio(value="perfile", label="单独"),
            ], spacing=8),
            on_change=self._on_mode_changed,
        )

        # --- 全局输出控件 ---
        self.output_dd = ft.Dropdown(
            label="Output", width=140, visible=False, options=[],
            on_change=self._on_global_output_change,
        )
        self.gear_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS, icon_size=20,
            tooltip="高级选项", icon_color=ft.Colors.GREY_600,
            visible=False, on_click=self._toggle_advanced,
        )

        # --- 按钮 ---
        self.btn_clear = ft.IconButton(
            icon=ft.Icons.CLEAR_ALL, tooltip="清空列表", disabled=True,
            on_click=lambda _: self._clear_files(),
        )
        self.btn_convert = ft.FilledButton(
            "转换", icon=ft.Icons.SWAP_HORIZ, disabled=True,
            on_click=lambda _: self._do_convert(),
        )

        # --- 内容区 ---
        content = ft.Container(
            content=ft.Row([
                # 左侧：文件列表（与 PDF 合并列表布局一致）
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("待转换列表", size=15, weight=ft.FontWeight.W_500),
                            self.file_count,
                        ]),
                        ft.Divider(height=4),
                        self.file_list,
                    ], expand=True),
                    expand=True, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                    bgcolor=ft.Colors.WHITE, padding=12,
                ),
                # 右侧：控制面板
                ft.Container(
                    content=ft.Column([
                        ft.IconButton(
                            icon=ft.Icons.ADD, tooltip="添加文件",
                            icon_color=ft.Colors.BLUE_600,
                            on_click=lambda _: self._add_files_via_picker(file_picker),
                        ),
                        ft.Divider(height=8),
                        ft.Text("设置模式:", size=12, weight=ft.FontWeight.W_500),
                        self.mode_toggle,
                        ft.Divider(height=8),
                        ft.Text("Output:", size=13, weight=ft.FontWeight.W_500),
                        ft.Row([self.output_dd, self.gear_btn], spacing=4,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self._build_global_advanced_panel(),
                        ft.Divider(height=12),
                        self.btn_clear,
                        ft.Divider(height=8),
                        self.btn_convert,
                    ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(horizontal=12, vertical=12),
                    width=200,
                ),
            ], spacing=12, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 日志面板 ---
        log_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.TERMINAL, size=16, color=ft.Colors.GREY_600),
                    ft.Text("运行日志", weight=ft.FontWeight.W_500, size=13),
                ]),
                ft.Divider(height=4),
                self.log_list,
            ], expand=True),
            padding=ft.padding.all(12),
            bgcolor=ft.Colors.GREY_100,
            border=ft.border.only(top=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            height=140,
        )

        return top_bar, content, log_panel
