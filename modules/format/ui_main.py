import os
from datetime import datetime
import flet as ft

from modules.i18n import _
from modules.settings import load_app_settings, save_app_settings, build_settings_dialog
from modules.format.converters import video_convert, image_convert

# 输入类型 → 可选输出格式
FORMAT_DEFS = {
    "image": {
        "label": _("图片"),
        "icon": ft.Icons.IMAGE_OUTLINED,
        "color": ft.Colors.ORANGE_400,
        "outputs": ["PDF", "JPG", "PNG", "WebP", "BMP", "TIFF"],
        "exts": ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.heic', '.gif', '.jfif'),
    },
    "video": {
        "label": _("视频"),
        "icon": ft.Icons.VIDEO_FILE,
        "color": ft.Colors.PURPLE_400,
        "outputs": ["MP4", "MOV", "AVI", "MKV", "WebM", "GIF", "MP3"],
        "exts": ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv'),
    },
    "audio": {
        "label": _("音频"),
        "icon": ft.Icons.AUDIO_FILE,
        "color": ft.Colors.TEAL_400,
        "outputs": ["MP3", "WAV", "FLAC", "AAC", "OGG"],
        "exts": ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'),
    },
    "document": {
        "label": _("文档"),
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
    t = _detect_type(filepath)
    if not t:
        return None
    outputs = FORMAT_DEFS[t]["outputs"]
    defaults = {"image": "JPG", "video": "MP4", "audio": "MP3", "document": "PDF"}
    default = defaults.get(t, outputs[0])
    return default if default in outputs else outputs[0]


def _outputs_for_files(files):
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
    """Format Converter UI — global / per-file output modes."""

    def __init__(self, page: ft.Page, output_dir: str = None):
        self.page = page
        settings = load_app_settings()
        self.output_dir = output_dir or settings["output_dir"]

        self.files = []
        self.use_global = True
        self.mixed_types = False
        self.global_output = None
        self.global_quality = "high"
        self.global_bitrate = ""
        # Video advanced (global)
        self.global_video_codec = "h264"
        self.global_resolution = "original"
        self.global_frame_rate = "original"
        self.global_audio_codec = "aac"
        self.global_audio_bitrate = ""
        self.global_cover_path = ""
        self.global_cover_as_content = False
        self.global_cover_fit_mode = "blur"
        # Image advanced (global)
        self.global_img_resize_mode = "original"
        self.global_img_max_width = ""
        self.global_img_max_height = ""
        self.global_img_scale_pct = "100"
        self.global_img_keep_aspect = True
        self.global_img_color_mode = "original"

        self.file_settings = {}

        # Control refs
        self.log_list = None
        self.dir_text = None
        self.file_list = None
        self.file_count = None
        self.btn_clear = None
        self.btn_convert = None
        self.output_dd = None
        self.gear_btn = None
        self.adv_panel = None
        self.adv_visible = False
        self.adv_quality = None
        self.adv_bitrate = None
        self.mode_toggle = None
        self.mixed_type_hint = None

        self.global_adv_video_codec = None
        self.global_adv_resolution = None
        self.global_adv_frame_rate = None
        self.global_adv_audio_codec = None
        self.global_adv_audio_bitrate = None
        self.global_adv_cover_path = None
        self.global_adv_cover_label = None
        self.global_adv_cover_as_content = None

        self.global_adv_img_resize_mode = None
        self.global_adv_img_max_width = None
        self.global_adv_img_max_height = None
        self.global_adv_img_scale_pct = None
        self.global_adv_img_keep_aspect = None
        self.global_adv_img_color_mode = None

        self._pf_cover_fp = None
        self._pf_cover_label_ref = None
        self._pf_cover_path_box = None
        self._pf_cover_picker = None
        self._global_cover_picker = None

        # Progress tracking during conversion
        self._progress_bars = {}   # filepath → ft.ProgressBar
        self._progress_labels = {}  # filepath → ft.Text
        self._converting = False

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

    # ===================== File Management =====================
    def _on_files_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            for f in e.files:
                if f.path not in self.files:
                    self.files.append(f.path)
            self._after_files_changed()

    def _add_files_via_picker(self, picker):
        picker.pick_files(
            dialog_title=_("选择要转换的文件"),
            allow_multiple=True,
            file_type=ft.FilePickerFileType.ANY,
        )

    def _after_files_changed(self):
        types_seen = set()
        for fp in self.files:
            t = _detect_type(fp)
            if t:
                types_seen.add(t)
        self.mixed_types = len(types_seen) > 1

        if self.mixed_types and self.use_global:
            self.use_global = False
            if self.mode_toggle:
                self.mode_toggle.value = "perfile"

        for fp in self.files:
            if fp not in self.file_settings:
                def_out = _default_output(fp)
                self.file_settings[fp] = {
                    "output": def_out, "quality": "high", "bitrate": "",
                    "video_codec": "h264", "resolution": "original",
                    "frame_rate": "original", "audio_codec": "aac",
                    "audio_bitrate": "", "cover_path": "", "cover_as_content": False,
                    "cover_fit_mode": "blur",
                    "img_resize_mode": "original", "img_max_width": "",
                    "img_max_height": "", "img_scale_pct": "100",
                    "img_keep_aspect": True, "img_color_mode": "original",
                }

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

            per_file_row = ft.Row(visible=not self.use_global)
            out_dd = ft.Dropdown(
                value=file_output, width=110, text_size=12, dense=True,
                options=[ft.dropdown.Option(o, o) for o in _outputs_for_files([fpath])],
                on_change=lambda e, fp=fpath: self._on_per_file_output(fp, e.control.value),
            )
            per_gear = ft.IconButton(
                icon=ft.Icons.SETTINGS, icon_size=16,
                tooltip=_("高级选项"),
                icon_color=ft.Colors.GREY_500,
                on_click=lambda _, fp=fpath: self._show_per_file_advanced(fp),
            )
            per_file_row.controls = [
                ft.Text(_("Output:"), size=11, color=ft.Colors.GREY_500),
                out_dd, per_gear,
            ]
            per_file_row._out_dd = out_dd

            # Progress bar (hidden by default, shown during conversion)
            prog_bar = ft.ProgressBar(width=300, visible=False, value=0.0)
            prog_label = ft.Text("", size=11, color=ft.Colors.GREY_500, visible=False)
            self._progress_bars[fpath] = prog_bar
            self._progress_labels[fpath] = prog_label

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
                        ft.Row([prog_bar, prog_label], spacing=8,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ], spacing=2),
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
            title=ft.Text(_("确认清空")),
            content=ft.Text(_("确定要清空全部 {n} 个文件吗？", n=len(self.files))),
            actions=[
                ft.TextButton(_("取消"), on_click=lambda _: self.page.close(dlg)),
                ft.FilledButton(_("清空"), on_click=lambda _: self._do_clear(dlg)),
            ],
        )
        self.page.open(dlg)

    def _do_clear(self, dlg):
        self.page.close(dlg)
        self.files.clear()
        self.file_settings.clear()
        self.global_output = None
        self._after_files_changed()
        self.add_log(_("已清空全部文件"))

    def _update_buttons(self):
        n = len(self.files)
        self.btn_clear.disabled = (n == 0)
        self.btn_convert.disabled = (n == 0)
        self.file_count.value = f" ({n} {_('个文件')})" if n else ""

    # ===================== Mode Toggle =====================
    def _on_mode_changed(self, e):
        if self.mixed_types:
            self.mode_toggle.value = "perfile"
            self.page.update()
            return
        self.use_global = (self.mode_toggle.value == "global")
        self._rebuild_file_list()
        self._update_global_controls()

    # ===================== Global Controls =====================
    def _update_global_controls(self):
        all_outputs = _outputs_for_files(self.files)
        has_files = len(self.files) > 0

        if has_files:
            if self.mixed_types:
                if self.mode_toggle:
                    self.mode_toggle.disabled = True
                    self.mode_toggle.value = "perfile"
                self.use_global = False
            else:
                if self.mode_toggle:
                    self.mode_toggle.disabled = False

        if self.mixed_type_hint:
            self.mixed_type_hint.visible = self.mixed_types

        if all_outputs and self.use_global and not self.mixed_types:
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

    # ===================== Cover Image Pickers =====================
    def _pick_global_cover(self):
        try:
            self._global_cover_picker.pick_files(
                dialog_title=_("选择视频封面图片"),
                allowed_extensions=["png", "jpg", "jpeg"],
                allow_multiple=False,
                file_type=ft.FilePickerFileType.IMAGE,
            )
        except Exception as ex:
            self.add_log(f"⚠ {_('封面选择器错误')}: {ex}")

    def _pick_perfile_cover(self):
        try:
            self._pf_cover_picker.pick_files(
                dialog_title=_("选择视频封面图片"),
                allowed_extensions=["png", "jpg", "jpeg"],
                allow_multiple=False,
                file_type=ft.FilePickerFileType.IMAGE,
            )
        except Exception as ex:
            self.add_log(f"⚠ {_('封面选择器错误')}: {ex}")

    # ===================== Per-File Mode =====================
    def _on_per_file_output(self, fp, value):
        if fp in self.file_settings:
            self.file_settings[fp]["output"] = value
        self.add_log(_("{name} → 输出格式: {fmt}", name=os.path.basename(fp), fmt=value))

    def _show_per_file_advanced(self, fp):
        settings = self.file_settings.get(fp, {})
        file_type = _detect_type(fp)

        quality_dd = ft.Dropdown(
            label=_("输出质量"), value=settings.get("quality", "high"), width=155,
            options=[
                ft.dropdown.Option("low", _("低")),
                ft.dropdown.Option("medium", _("中")),
                ft.dropdown.Option("high", _("高")),
                ft.dropdown.Option("lossless", _("无损")),
            ],
        )
        bitrate_field = ft.TextField(
            label=_("总码率 (kbps)"), value=settings.get("bitrate", ""),
            width=155, hint_text=_("留空 = 自动"), text_size=13,
        )

        vf = self._build_video_advanced_fields("perfile")
        vf["video_codec"].value = settings.get("video_codec", "h264")
        vf["resolution"].value = settings.get("resolution", "original")
        vf["frame_rate"].value = settings.get("frame_rate", "original")
        vf["audio_codec"].value = settings.get("audio_codec", "aac")
        vf["audio_bitrate"].value = settings.get("audio_bitrate", "")
        cov = settings.get("cover_path", "")
        vf["cover_label"].value = os.path.basename(cov) if cov else _("未选择")
        vf["cover_as_content"].value = settings.get("cover_as_content", False)
        vf["cover_fit"].value = settings.get("cover_fit_mode", "blur")

        pf_cover_path_box = [cov]
        self._pf_cover_fp = fp
        self._pf_cover_label_ref = vf["cover_label"]
        self._pf_cover_path_box = pf_cover_path_box

        is_video = file_type == "video"
        video_section = ft.Column([
            ft.Divider(height=8),
            ft.Text(_("视频编码"), size=12, weight=ft.FontWeight.W_500),
            ft.Row([vf["video_codec"], vf["resolution"], vf["frame_rate"]],
                   spacing=8, wrap=True),
            ft.Divider(height=4),
            ft.Text(_("音频编码"), size=12, weight=ft.FontWeight.W_500),
            ft.Row([vf["audio_codec"], vf["audio_bitrate"]], spacing=8, wrap=True),
            ft.Divider(height=4),
            ft.Text(_("视频封面"), size=12, weight=ft.FontWeight.W_500),
            ft.Row([
                ft.OutlinedButton(
                    _("选择封面图片"), icon=ft.Icons.IMAGE_OUTLINED, height=32,
                    on_click=lambda _: self._pick_perfile_cover(),
                ),
                vf["cover_label"],
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            vf["cover_as_content"],
            vf["cover_fit"],
        ], visible=is_video, spacing=6)

        imgf = self._build_image_advanced_fields("perfile")
        imgf["resize_mode"].value = settings.get("img_resize_mode", "original")
        imgf["max_width"].value = settings.get("img_max_width", "")
        imgf["max_height"].value = settings.get("img_max_height", "")
        imgf["scale_pct"].value = settings.get("img_scale_pct", "100")
        imgf["keep_aspect"].value = settings.get("img_keep_aspect", True)
        imgf["color_mode"].value = settings.get("img_color_mode", "original")

        def _on_img_resize_mode_change(e):
            mode = imgf["resize_mode"].value
            imgf["max_width"].visible = (mode == "dimensions")
            imgf["max_height"].visible = (mode == "dimensions")
            imgf["scale_pct"].visible = (mode == "scale")
            self.page.update()
        imgf["resize_mode"].on_change = _on_img_resize_mode_change
        init_mode = imgf["resize_mode"].value
        imgf["max_width"].visible = (init_mode == "dimensions")
        imgf["max_height"].visible = (init_mode == "dimensions")
        imgf["scale_pct"].visible = (init_mode == "scale")

        is_image = file_type == "image"
        image_section = ft.Column([
            ft.Divider(height=8),
            ft.Text(_("图片设置"), size=12, weight=ft.FontWeight.W_500),
            imgf["resize_mode"],
            ft.Row([imgf["max_width"], imgf["max_height"]], spacing=8, wrap=True),
            imgf["scale_pct"],
            imgf["keep_aspect"],
            ft.Divider(height=4),
            imgf["color_mode"],
        ], visible=is_image, spacing=6)

        def on_save(e):
            self.file_settings[fp]["quality"] = quality_dd.value
            self.file_settings[fp]["bitrate"] = bitrate_field.value
            if is_video:
                self.file_settings[fp]["video_codec"] = vf["video_codec"].value
                self.file_settings[fp]["resolution"] = vf["resolution"].value
                self.file_settings[fp]["frame_rate"] = vf["frame_rate"].value
                self.file_settings[fp]["audio_codec"] = vf["audio_codec"].value
                self.file_settings[fp]["audio_bitrate"] = vf["audio_bitrate"].value
                self.file_settings[fp]["cover_path"] = pf_cover_path_box[0]
                self.file_settings[fp]["cover_as_content"] = vf["cover_as_content"].value
                self.file_settings[fp]["cover_fit_mode"] = vf["cover_fit"].value
            if is_image:
                self.file_settings[fp]["img_resize_mode"] = imgf["resize_mode"].value
                self.file_settings[fp]["img_max_width"] = imgf["max_width"].value
                self.file_settings[fp]["img_max_height"] = imgf["max_height"].value
                self.file_settings[fp]["img_scale_pct"] = imgf["scale_pct"].value
                self.file_settings[fp]["img_keep_aspect"] = imgf["keep_aspect"].value
                self.file_settings[fp]["img_color_mode"] = imgf["color_mode"].value
            self.page.close(dlg)
            self.add_log(_("{name} 高级选项已更新", name=os.path.basename(fp)))
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text(f"{_('高级选项')} - {os.path.basename(fp)}"),
            content=ft.Column([
                quality_dd, bitrate_field, video_section, image_section,
            ], tight=True, width=360, spacing=10, scroll=ft.ScrollMode.AUTO, height=460),
            actions=[
                ft.TextButton(_("取消"), on_click=lambda _: self.page.close(dlg)),
                ft.FilledButton(_("保存"), on_click=on_save),
            ],
        )
        self.page.open(dlg)

    # ===================== Advanced Fields Builders =====================
    def _build_image_advanced_fields(self, settings_source="global"):
        if settings_source == "global":
            rm_val, mw_val, mh_val = self.global_img_resize_mode, self.global_img_max_width, self.global_img_max_height
            sp_val, ka_val, cm_val = self.global_img_scale_pct, self.global_img_keep_aspect, self.global_img_color_mode
        else:
            rm_val, mw_val, mh_val, sp_val, ka_val, cm_val = "original", "", "", "100", True, "original"

        resize_mode_dd = ft.Dropdown(
            label=_("尺寸调整"), value=rm_val, width=155,
            options=[
                ft.dropdown.Option("original", _("原始尺寸")),
                ft.dropdown.Option("dimensions", _("按宽高")),
                ft.dropdown.Option("scale", _("按比例")),
            ],
        )
        max_width = ft.TextField(label=_("最大宽度 (px)"), value=mw_val, width=155,
                                 hint_text=_("留空 = 不限"), text_size=13)
        max_height = ft.TextField(label=_("最大高度 (px)"), value=mh_val, width=155,
                                  hint_text=_("留空 = 不限"), text_size=13)
        scale_pct = ft.TextField(label=_("缩放比例 (%)"), value=sp_val, width=155,
                                 hint_text=_("100 = 不变"), text_size=13)
        keep_aspect = ft.Checkbox(label=_("保持宽高比"), value=ka_val)
        color_mode_dd = ft.Dropdown(
            label=_("颜色模式"), value=cm_val, width=155,
            options=[
                ft.dropdown.Option("original", _("原始")),
                ft.dropdown.Option("rgb", "RGB"),
                ft.dropdown.Option("rgba", "RGBA"),
                ft.dropdown.Option("grayscale", _("灰度")),
            ],
        )
        return {
            "resize_mode": resize_mode_dd, "max_width": max_width,
            "max_height": max_height, "scale_pct": scale_pct,
            "keep_aspect": keep_aspect, "color_mode": color_mode_dd,
        }

    def _build_video_advanced_fields(self, settings_source="global"):
        if settings_source == "global":
            vc_val = self.global_video_codec
            res_val = self.global_resolution
            fr_val = self.global_frame_rate
            ac_val = self.global_audio_codec
            ab_val = self.global_audio_bitrate
            cov_path = self.global_cover_path
            cov_as = self.global_cover_as_content
            cov_fit = self.global_cover_fit_mode
        else:
            vc_val, res_val, fr_val = "h264", "original", "original"
            ac_val, ab_val, cov_path, cov_as, cov_fit = "aac", "", "", False, "blur"

        video_codec_dd = ft.Dropdown(
            label=_("视频编码"), value=vc_val, width=155,
            options=[
                ft.dropdown.Option("h264", "H.264"),
                ft.dropdown.Option("h265", "H.265 / HEVC"),
                ft.dropdown.Option("vp9", "VP9"),
                ft.dropdown.Option("av1", "AV1"),
                ft.dropdown.Option("copy", _("原始 (Copy)")),
            ],
        )
        resolution_dd = ft.Dropdown(
            label=_("分辨率"), value=res_val, width=155,
            options=[
                ft.dropdown.Option("original", _("原始")),
                ft.dropdown.Option("2160p", _("4K (2160p)")),
                ft.dropdown.Option("1080p", "1080p"),
                ft.dropdown.Option("720p", "720p"),
                ft.dropdown.Option("480p", "480p"),
            ],
        )
        frame_rate_dd = ft.Dropdown(
            label=_("帧率"), value=fr_val, width=155,
            options=[
                ft.dropdown.Option("original", _("原始")),
                ft.dropdown.Option("60", _("60 fps")),
                ft.dropdown.Option("30", _("30 fps")),
                ft.dropdown.Option("24", _("24 fps")),
                ft.dropdown.Option("15", _("15 fps")),
            ],
        )
        audio_codec_dd = ft.Dropdown(
            label=_("音频编码"), value=ac_val, width=155,
            options=[
                ft.dropdown.Option("aac", "AAC"),
                ft.dropdown.Option("mp3", "MP3"),
                ft.dropdown.Option("opus", "Opus"),
                ft.dropdown.Option("copy", _("原始 (Copy)")),
            ],
        )
        audio_bitrate = ft.TextField(
            label=_("音频码率 (kbps)"), value=ab_val, width=155,
            hint_text=_("留空 = 自动"), text_size=13,
        )
        cover_label = ft.Text(
            os.path.basename(cov_path) if cov_path else _("未选择"), size=11,
            color=ft.Colors.GREY_600, max_lines=1,
        )
        cover_as_content = ft.Checkbox(label=_("以封面作为视频内容"), value=cov_as)
        cover_fit_dd = ft.Dropdown(
            label=_("封面适配方式"), value=cov_fit, width=155,
            options=[
                ft.dropdown.Option("blur", _("模糊填充 (无黑边)")),
                ft.dropdown.Option("video_size", _("视频尺寸 (居中留黑边)")),
                ft.dropdown.Option("image_size", _("图片尺寸为准")),
            ],
        )

        return {
            "video_codec": video_codec_dd, "resolution": resolution_dd,
            "frame_rate": frame_rate_dd, "audio_codec": audio_codec_dd,
            "audio_bitrate": audio_bitrate, "cover_label": cover_label,
            "cover_as_content": cover_as_content, "cover_fit": cover_fit_dd,
        }

    def _build_global_advanced_panel(self):
        self.adv_quality = ft.Dropdown(
            label=_("输出质量"), value="high", width=160,
            options=[
                ft.dropdown.Option("low", _("低")),
                ft.dropdown.Option("medium", _("中")),
                ft.dropdown.Option("high", _("高")),
                ft.dropdown.Option("lossless", _("无损")),
            ],
        )
        self.adv_bitrate = ft.TextField(
            label=_("总码率 (kbps)"), value="", width=160,
            hint_text=_("留空 = 自动"), text_size=13,
        )

        vf = self._build_video_advanced_fields("global")
        self.global_adv_video_codec = vf["video_codec"]
        self.global_adv_resolution = vf["resolution"]
        self.global_adv_frame_rate = vf["frame_rate"]
        self.global_adv_audio_codec = vf["audio_codec"]
        self.global_adv_audio_bitrate = vf["audio_bitrate"]
        self.global_adv_cover_label = vf["cover_label"]
        self.global_adv_cover_as_content = vf["cover_as_content"]
        self.global_adv_cover_fit = vf["cover_fit"]

        def _on_global_vc_change(e): self.global_video_codec = self.global_adv_video_codec.value
        def _on_global_res_change(e): self.global_resolution = self.global_adv_resolution.value
        def _on_global_fr_change(e): self.global_frame_rate = self.global_adv_frame_rate.value
        def _on_global_ac_change(e): self.global_audio_codec = self.global_adv_audio_codec.value
        def _on_global_ab_change(e): self.global_audio_bitrate = self.global_adv_audio_bitrate.value
        def _on_global_cov_change(e): self.global_cover_as_content = self.global_adv_cover_as_content.value
        def _on_global_cov_fit_change(e): self.global_cover_fit_mode = self.global_adv_cover_fit.value

        self.global_adv_video_codec.on_change = _on_global_vc_change
        self.global_adv_resolution.on_change = _on_global_res_change
        self.global_adv_frame_rate.on_change = _on_global_fr_change
        self.global_adv_audio_codec.on_change = _on_global_ac_change
        self.global_adv_audio_bitrate.on_change = _on_global_ab_change
        self.global_adv_cover_as_content.on_change = _on_global_cov_change
        self.global_adv_cover_fit.on_change = _on_global_cov_fit_change

        imgf = self._build_image_advanced_fields("global")
        self.global_adv_img_resize_mode = imgf["resize_mode"]
        self.global_adv_img_max_width = imgf["max_width"]
        self.global_adv_img_max_height = imgf["max_height"]
        self.global_adv_img_scale_pct = imgf["scale_pct"]
        self.global_adv_img_keep_aspect = imgf["keep_aspect"]
        self.global_adv_img_color_mode = imgf["color_mode"]

        def _on_global_img_rm_change(e):
            self.global_img_resize_mode = self.global_adv_img_resize_mode.value
            m = self.global_img_resize_mode
            self.global_adv_img_max_width.visible = (m == "dimensions")
            self.global_adv_img_max_height.visible = (m == "dimensions")
            self.global_adv_img_scale_pct.visible = (m == "scale")
            self.page.update()
        def _on_global_img_mw_change(e): self.global_img_max_width = self.global_adv_img_max_width.value
        def _on_global_img_mh_change(e): self.global_img_max_height = self.global_adv_img_max_height.value
        def _on_global_img_sp_change(e): self.global_img_scale_pct = self.global_adv_img_scale_pct.value
        def _on_global_img_ka_change(e): self.global_img_keep_aspect = self.global_adv_img_keep_aspect.value
        def _on_global_img_cm_change(e): self.global_img_color_mode = self.global_adv_img_color_mode.value

        self.global_adv_img_resize_mode.on_change = _on_global_img_rm_change
        self.global_adv_img_max_width.on_change = _on_global_img_mw_change
        self.global_adv_img_max_height.on_change = _on_global_img_mh_change
        self.global_adv_img_scale_pct.on_change = _on_global_img_sp_change
        self.global_adv_img_keep_aspect.on_change = _on_global_img_ka_change
        self.global_adv_img_color_mode.on_change = _on_global_img_cm_change
        rm0 = self.global_img_resize_mode
        self.global_adv_img_max_width.visible = (rm0 == "dimensions")
        self.global_adv_img_max_height.visible = (rm0 == "dimensions")
        self.global_adv_img_scale_pct.visible = (rm0 == "scale")

        self.adv_panel = ft.Container(
            visible=False,
            content=ft.Column([
                ft.Divider(height=8),
                ft.Text(_("高级选项"), size=13, weight=ft.FontWeight.W_500),
                ft.Row([self.adv_quality, self.adv_bitrate], spacing=12, wrap=True),
                ft.Divider(height=8),
                ft.Text(_("视频编码"), size=12, weight=ft.FontWeight.W_500),
                ft.Row([self.global_adv_video_codec, self.global_adv_resolution,
                        self.global_adv_frame_rate], spacing=8, wrap=True),
                ft.Divider(height=4),
                ft.Text(_("音频编码"), size=12, weight=ft.FontWeight.W_500),
                ft.Row([self.global_adv_audio_codec, self.global_adv_audio_bitrate],
                       spacing=8, wrap=True),
                ft.Divider(height=4),
                ft.Text(_("视频封面"), size=12, weight=ft.FontWeight.W_500),
                ft.Row([
                    ft.OutlinedButton(
                        _("选择封面图片"), icon=ft.Icons.IMAGE_OUTLINED, height=32,
                        on_click=lambda _: self._pick_global_cover(),
                    ),
                    self.global_adv_cover_label,
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.global_adv_cover_as_content,
                self.global_adv_cover_fit,
                ft.Divider(height=8),
                ft.Text(_("图片设置"), size=12, weight=ft.FontWeight.W_500),
                self.global_adv_img_resize_mode,
                ft.Row([self.global_adv_img_max_width, self.global_adv_img_max_height],
                       spacing=8, wrap=True),
                self.global_adv_img_scale_pct,
                self.global_adv_img_keep_aspect,
                ft.Divider(height=4),
                self.global_adv_img_color_mode,
            ], spacing=6, scroll=ft.ScrollMode.AUTO, expand=True),
            padding=ft.padding.only(top=4),
        )
        return self.adv_panel

    # ===================== Convert =====================
    @staticmethod
    def _build_output_path(input_path, output_dir, output_format):
        """Build output path ensuring no overwrites."""
        base = os.path.splitext(os.path.basename(input_path))[0]
        ext = f".{output_format.lower()}"
        out = os.path.join(output_dir, f"{base}_converted{ext}")
        counter = 1
        while os.path.exists(out):
            out = os.path.join(output_dir, f"{base}_converted_{counter}{ext}")
            counter += 1
        return out

    def _set_file_progress(self, fpath, percent, label=""):
        """Update progress bar and label for a file."""
        bar = self._progress_bars.get(fpath)
        lbl = self._progress_labels.get(fpath)
        if bar:
            bar.visible = True
            bar.value = min(1.0, max(0.0, percent / 100.0))
        if lbl:
            lbl.visible = True
            lbl.value = label
        try:
            self.page.update()
        except Exception:
            pass

    def _reset_progress(self, fpath):
        bar = self._progress_bars.get(fpath)
        lbl = self._progress_labels.get(fpath)
        if bar:
            bar.visible = False
            bar.value = 0.0
        if lbl:
            lbl.visible = False
            lbl.value = ""

    def _do_convert(self):
        if self._converting:
            self.show_snack(_("转换正在进行中，请等待"), is_error=True)
            return
        if not self.files:
            self.show_snack(_("请先添加文件"), is_error=True)
            return

        # Check ffmpeg for video files
        has_video = any(_detect_type(f) == "video" for f in self.files)
        if has_video and not video_convert.is_available():
            self.show_snack(
                _("未找到 ffmpeg，无法转换视频文件。请安装 ffmpeg 并加入 PATH。"),
                is_error=True,
            )
            self.add_log(_("❌ 未找到 ffmpeg"))
            return

        self._converting = True
        self.btn_convert.disabled = True
        self.btn_clear.disabled = True
        self.page.run_task(self._run_conversion_tasks)

    async def _run_conversion_tasks(self):
        """Run all conversions sequentially in background."""
        import asyncio
        os.makedirs(self.output_dir, exist_ok=True)
        success_count = 0
        fail_count = 0

        try:
            for fpath in list(self.files):
                t = _detect_type(fpath)
                if self.use_global:
                    settings = {
                        "quality": self.global_quality,
                        "bitrate": self.global_bitrate,
                        "video_codec": self.global_video_codec,
                        "resolution": self.global_resolution,
                        "frame_rate": self.global_frame_rate,
                        "audio_codec": self.global_audio_codec,
                        "audio_bitrate": self.global_audio_bitrate,
                        "cover_path": self.global_cover_path,
                        "cover_as_content": self.global_cover_as_content,
                        "cover_fit_mode": self.global_cover_fit_mode,
                        "img_resize_mode": self.global_img_resize_mode,
                        "img_max_width": self.global_img_max_width,
                        "img_max_height": self.global_img_max_height,
                        "img_scale_pct": self.global_img_scale_pct,
                        "img_keep_aspect": self.global_img_keep_aspect,
                        "img_color_mode": self.global_img_color_mode,
                    }
                    out_fmt = self.global_output
                else:
                    s = self.file_settings.get(fpath, {})
                    settings = {
                        "quality": s.get("quality", "high"),
                        "bitrate": s.get("bitrate", ""),
                        "video_codec": s.get("video_codec", "h264"),
                        "resolution": s.get("resolution", "original"),
                        "frame_rate": s.get("frame_rate", "original"),
                        "audio_codec": s.get("audio_codec", "aac"),
                        "audio_bitrate": s.get("audio_bitrate", ""),
                        "cover_path": s.get("cover_path", ""),
                        "cover_as_content": s.get("cover_as_content", False),
                        "cover_fit_mode": s.get("cover_fit_mode", "blur"),
                        "img_resize_mode": s.get("img_resize_mode", "original"),
                        "img_max_width": s.get("img_max_width", ""),
                        "img_max_height": s.get("img_max_height", ""),
                        "img_scale_pct": s.get("img_scale_pct", "100"),
                        "img_keep_aspect": s.get("img_keep_aspect", True),
                        "img_color_mode": s.get("img_color_mode", "original"),
                    }
                    out_fmt = s.get("output", "")

                if not out_fmt:
                    self.add_log(f"⚠ {os.path.basename(fpath)}: {_('未设置输出格式')}")
                    fail_count += 1
                    continue

                out_path = self._build_output_path(fpath, self.output_dir, out_fmt)
                name = os.path.basename(fpath)

                self.add_log(_("开始转换: {name} → {fmt}", name=name, fmt=out_fmt))

                def progress_cb(pct, status):
                    self._set_file_progress(fpath, pct, status)

                success = False
                error = None

                if t == "video":
                    # Run cpu-bound ffmpeg in thread to not block the event loop
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: video_convert.convert_video(
                            fpath, out_path, settings, progress_cb,
                        ),
                    )
                    success, error = result
                elif t == "image":
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: image_convert.convert_image(
                            fpath, out_path, settings, progress_cb,
                        ),
                    )
                    success, error = result
                elif t == "audio":
                    # Audio not yet implemented; copy unsupported types
                    self.add_log(f"⚠ {name}: {_('音频转换尚未支持')}")
                    fail_count += 1
                    continue
                elif t == "document":
                    self.add_log(f"⚠ {name}: {_('文档转换尚未支持')}")
                    fail_count += 1
                    continue
                else:
                    self.add_log(f"⚠ {name}: {_('不支持的文件类型')}")
                    fail_count += 1
                    continue

                if success:
                    self._set_file_progress(fpath, 100.0, _("完成"))
                    self.add_log(_("✅ 转换完成: {path}", path=out_path))
                    success_count += 1
                else:
                    self._set_file_progress(fpath, 0.0, _("失败"))
                    self.add_log(_("❌ 转换失败: {name} - {error}", name=name, error=error or _("未知错误")))
                    fail_count += 1

                await asyncio.sleep(0.3)

        except Exception as ex:
            self.add_log(f"❌ {_('转换异常')}: {ex}")
        finally:
            self._converting = False
            self.btn_convert.disabled = False
            self.btn_clear.disabled = False
            self.show_snack(
                _("转换完成：成功 {ok}，失败 {fail}", ok=success_count, fail=fail_count)
                if fail_count > 0
                else _("全部转换完成！{n} 个文件", n=success_count)
            )
            self.page.update()

    # ===================== Settings =====================
    def _show_settings(self, _e):
        def on_close():
            self.page.update()
        rebuild = getattr(self.page, '_on_rebuild_ui', None)
        build_settings_dialog(self.page, on_close=on_close, show_startup=False,
                              on_language_changed=rebuild)

    # ===================== Drag & Drop =====================
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
            self.add_log(_("📥 拖放导入 {n} 个文件", n=added))

    # ===================== Directory =====================
    def _on_dir_pick(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.output_dir = e.path
            self.dir_text.value = self.output_dir
            save_app_settings(output_dir=self.output_dir)
            self.add_log(_("输出目录已更改为: {dir}", dir=self.output_dir))

    # ===================== Build =====================
    def build(self):
        page = self.page

        dir_picker = ft.FilePicker(on_result=self._on_dir_pick)
        file_picker = ft.FilePicker(on_result=self._on_files_pick)

        def _on_pf_cover_result(e: ft.FilePickerResultEvent):
            if e.files and self._pf_cover_path_box is not None:
                self._pf_cover_path_box[0] = e.files[0].path
                if self._pf_cover_label_ref:
                    self._pf_cover_label_ref.value = os.path.basename(e.files[0].path)
                self.page.update()

        def _on_global_cover_result(e: ft.FilePickerResultEvent):
            if e.files:
                self.global_cover_path = e.files[0].path
                if self.global_adv_cover_label:
                    self.global_adv_cover_label.value = os.path.basename(e.files[0].path)
                self.page.update()

        self._pf_cover_picker = ft.FilePicker(on_result=_on_pf_cover_result)
        self._global_cover_picker = ft.FilePicker(on_result=_on_global_cover_result)
        page.overlay.extend([dir_picker, file_picker, self._pf_cover_picker, self._global_cover_picker])

        self.log_list = ft.ListView(expand=True, auto_scroll=True, spacing=2)

        self.dir_text = ft.Text(
            self.output_dir, color=ft.Colors.BLUE_700, size=13, italic=True,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
        )
        top_bar = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.FOLDER_OPEN, color=ft.Colors.BLUE_600),
                ft.Text(_("保存至:"), weight=ft.FontWeight.W_500),
                ft.TextButton(
                    _("更改目录"),
                    icon=ft.Icons.EDIT_LOCATION_OUTLINED,
                    on_click=lambda _: dir_picker.get_directory_path(dialog_title=_("选择文件保存目录")),
                ),
                self.dir_text,
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS, icon_size=20,
                    tooltip=_("设置"), icon_color=ft.Colors.GREY_600,
                    on_click=self._show_settings,
                ),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            bgcolor=ft.Colors.GREY_100,
            border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )

        self.file_count = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.file_list = ft.ListView(expand=True, spacing=2)

        self.mode_toggle = ft.RadioGroup(
            value="global",
            content=ft.Row([
                ft.Radio(value="global", label=_("全局")),
                ft.Radio(value="perfile", label=_("单独")),
            ], spacing=8),
            on_change=self._on_mode_changed,
        )

        self.mixed_type_hint = ft.Text(
            _("文件类型不一致，已自动切换为单独设置模式"),
            size=11, color=ft.Colors.ORANGE_600, visible=False,
        )

        self.output_dd = ft.Dropdown(
            label="Output", width=140, visible=False, options=[],
            on_change=self._on_global_output_change,
        )
        self.gear_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS, icon_size=20,
            tooltip=_("高级选项"), icon_color=ft.Colors.GREY_600,
            visible=False, on_click=self._toggle_advanced,
        )

        self.btn_clear = ft.IconButton(
            icon=ft.Icons.CLEAR_ALL, tooltip=_("清空列表"), disabled=True,
            on_click=lambda _: self._clear_files(),
        )
        self.btn_convert = ft.FilledButton(
            _("转换"), icon=ft.Icons.SWAP_HORIZ, disabled=True,
            on_click=lambda _: self._do_convert(),
        )

        content = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(_("待转换列表"), size=15, weight=ft.FontWeight.W_500),
                            self.file_count,
                        ]),
                        ft.Divider(height=4),
                        self.file_list,
                    ], expand=True),
                    expand=True, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                    bgcolor=ft.Colors.WHITE, padding=12,
                ),
                ft.Container(
                    content=ft.Column([
                        ft.IconButton(
                            icon=ft.Icons.ADD, tooltip=_("添加文件"),
                            icon_color=ft.Colors.BLUE_600,
                            on_click=lambda _: self._add_files_via_picker(file_picker),
                        ),
                        ft.Divider(height=8),
                        ft.Text(_("设置模式:"), size=12, weight=ft.FontWeight.W_500),
                        self.mode_toggle,
                        self.mixed_type_hint,
                        ft.Divider(height=8),
                        ft.Text(_("Output:"), size=13, weight=ft.FontWeight.W_500),
                        ft.Row([self.output_dd, self.gear_btn], spacing=4,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self._build_global_advanced_panel(),
                        ft.Divider(height=12),
                        self.btn_clear,
                        ft.Divider(height=8),
                        self.btn_convert,
                    ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                       scroll=ft.ScrollMode.AUTO, expand=True),
                    padding=ft.padding.symmetric(horizontal=12, vertical=12),
                    width=220,
                ),
            ], spacing=12, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.padding.all(24), expand=True,
        )

        log_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.TERMINAL, size=16, color=ft.Colors.GREY_600),
                    ft.Text(_("运行日志"), weight=ft.FontWeight.W_500, size=13),
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
