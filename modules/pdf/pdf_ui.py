import os
import asyncio
from datetime import datetime

import flet as ft
from PyPDF2 import PdfReader, PdfWriter

from modules.pdf.config import (
    COLOR_PALETTE,
    load_config, save_config, load_presets, save_presets, parse_page_range,
    get_system_fonts, parse_color,
)
from modules.pdf.zip_to_pdf import extract_images
from modules.pdf.pdf_merge import merge_pdfs
from modules.pdf.pdf_split import split_all_pages, extract_pages_range, extract_pages_to_images
from modules.pdf.pdf_sign import sign_pdf
from modules.pdf.pdf_protect import encrypt_pdf, decrypt_pdf, is_encrypted
from modules.pdf.pdf_rotate import rotate_pdf
from modules.pdf.pdf_crop import crop_pdf
from modules.pdf.pdf_watermark import (
    create_watermark_stamp, parse_wm_pages, apply_watermark_to_pdf, preview_watermark,
)
from modules.pdf.dragdrop import enable as enable_dragdrop, get_dropped_files as get_drop


class PDFConverterUI:
    """PDF 转换器 UI —— 可在任意 Page 中嵌入使用。"""

    def __init__(self, page: ft.Page, output_dir: str = None):
        self.page = page
        self.output_dir = output_dir or load_config()

        # --- 状态变量 ---
        self.merge_files = []
        self.selected_indices = set()
        self.split_pdf_path = ""
        self.sign_pdf_path = ""
        self.sign_img_path = ""
        self.rotate_files = []
        self.crop_files = []
        self.watermark_files = []
        self.watermark_presets = load_presets()
        self.watermark_img_path = ""
        self.wm_color_hex = "#FF0000"

        # 字体
        self.system_fonts = get_system_fonts()
        self.system_font_names = [item[0] for item in self.system_fonts]
        self.system_font_paths = {item[0]: item[1] for item in self.system_fonts}
        self.system_font_families = {item[0]: item[2] for item in self.system_fonts}

        # ZIP 上下文
        self.zip_ctx = {"zip_path": None, "base_name": None, "dlg": None, "pwd_field": None}

        # 加密 / 解密路径
        self.protect_pdf_path = ""
        self.unlock_pdf_path = ""

        # 脚本目录
        self._script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.STARTUP_VBS = os.path.join(
            os.environ["APPDATA"],
            r"Microsoft\Windows\Start Menu\Programs\Startup",
            "工具箱.vbs",
        )

        # --- UI 控件引用 (在 build 中赋值) ---
        self.log_list = None
        self.dir_text = None

    # ===================== 工具方法 =====================
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

    # ===================== FilePicker 回调 =====================
    def _on_dir_pick(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.output_dir = e.path
            self.dir_text.value = self.output_dir
            save_config(self.output_dir)
            self.add_log(f"输出目录已更改为: {self.output_dir}")

    def _on_zip_pick(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        zip_path = e.files[0].path
        base = os.path.splitext(os.path.basename(zip_path))[0]
        self.zip_ctx["zip_path"] = zip_path
        self.zip_ctx["base_name"] = base
        self._do_zip_convert(zip_path, base)

    def _on_multi_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.merge_files.extend(f.path for f in e.files)
            self._rebuild_merge_list()

    def _on_single_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.split_pdf_path = e.files[0].path
            self.split_label.value = os.path.basename(self.split_pdf_path)
            self.add_log(f"已选择: {self.split_pdf_path}")
            self.page.update()

    def _on_sign_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.sign_pdf_path = e.files[0].path
            self.sign_pdf_label.value = os.path.basename(self.sign_pdf_path)
            self.add_log(f"已选择签名目标: {self.sign_pdf_path}")
            self.page.update()

    def _on_sign_img_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.sign_img_path = e.files[0].path
            self.sign_img_label.value = os.path.basename(self.sign_img_path)
            self.add_log(f"已选择签名图片: {self.sign_img_path}")
            self.page.update()

    def _on_protect_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.protect_pdf_label.value = os.path.basename(e.files[0].path)
            self.protect_pdf_path = e.files[0].path
            self.add_log(f"已选择: {e.files[0].path}")
            self.page.update()

    def _on_unlock_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            path = e.files[0].path
            self.unlock_pdf_label.value = os.path.basename(path)
            self.unlock_pdf_path = path
            self.add_log(f"已选择: {path}")
            try:
                enc, reader = is_encrypted(path)
                if enc:
                    self.unlock_status.value = "🔒 已加密"
                    self.unlock_status.color = ft.Colors.RED_600
                    self.unlock_pwd_field.visible = True
                    self.unlock_btn.disabled = False
                else:
                    self.unlock_status.value = "🔓 未加密"
                    self.unlock_status.color = ft.Colors.GREEN_700
                    self.unlock_pwd_field.visible = False
                    self.unlock_btn.disabled = False
            except Exception:
                self.unlock_status.value = "⚠ 无法读取"
                self.unlock_status.color = ft.Colors.RED_600
            self.page.update()

    def _on_rotate_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.rotate_files.extend(f.path for f in e.files)
            self._rebuild_rotate_list()

    def _on_crop_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.crop_files.extend(f.path for f in e.files)
            self._rebuild_crop_list()

    def _on_watermark_pdf_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.watermark_files.extend(f.path for f in e.files)
            self._rebuild_watermark_list()

    def _on_watermark_img_pick(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.watermark_img_path = e.files[0].path
            self.watermark_img_label.value = os.path.basename(self.watermark_img_path)
            self.page.update()

    # ===================== ZIP 转 PDF =====================
    def _do_zip_convert(self, zip_path, base_name, password=None):
        try:
            images = extract_images(zip_path, password)
        except RuntimeError as ex:
            if 'password' in str(ex).lower():
                self._show_password_dialog(zip_path, base_name)
                return
            self.add_log(f"❌ 错误: {ex}")
            self.show_snack(str(ex), is_error=True)
            self.zip_progress.visible = False
            self.page.update()
            return
        except Exception as ex:
            self.add_log(f"❌ 错误: {ex}")
            self.show_snack(str(ex), is_error=True)
            self.zip_progress.visible = False
            self.page.update()
            return

        if images:
            pdf_path = os.path.join(self.output_dir, f"{base_name}.pdf")
            images[0].save(pdf_path, "PDF", resolution=100.0, save_all=True, append_images=images[1:])
            self.add_log(f"✅ 成功! 保存至: {pdf_path}  ({len(images)} 张图片)")
            self.show_snack("PDF 生成完毕！")
        else:
            self.add_log("⚠️ ZIP 中未找到图片文件")
            self.show_snack("ZIP 中未找到图片文件", is_error=True)
        self.zip_progress.visible = False
        self.page.update()

    def _show_password_dialog(self, zip_path, base_name):
        pwd_field = ft.TextField(label="密码", password=True, can_reveal_password=True, autofocus=True)
        error_text = ft.Text("", color=ft.Colors.RED_600, size=12)
        self.zip_ctx["pwd_field"] = pwd_field

        def on_unlock(e):
            pwd = pwd_field.value
            if not pwd:
                error_text.value = "请输入密码"
                self.page.update()
                return
            try:
                images = extract_images(zip_path, pwd)
            except RuntimeError as ex:
                if 'password' in str(ex).lower():
                    error_text.value = "密码错误，请重试"
                    pwd_field.value = ""
                    self.page.update()
                    return
                error_text.value = str(ex)
                self.page.update()
                return
            except Exception as ex:
                error_text.value = str(ex)
                self.page.update()
                return
            self.page.close(self.zip_ctx["dlg"])
            self.zip_progress.visible = True
            self.page.update()
            if images:
                pdf_path = os.path.join(self.output_dir, f"{base_name}.pdf")
                images[0].save(pdf_path, "PDF", resolution=100.0, save_all=True, append_images=images[1:])
                self.add_log(f"✅ 成功! 保存至: {pdf_path}  ({len(images)} 张图片)")
                self.show_snack("PDF 生成完毕！")
            else:
                self.add_log("⚠️ ZIP 中未找到图片文件")
                self.show_snack("ZIP 中未找到图片文件", is_error=True)
            self.zip_progress.visible = False
            self.page.update()

        def on_cancel(e):
            self.page.close(self.zip_ctx["dlg"])
            self.add_log("已取消密码输入")
            self.zip_progress.visible = False
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("需要密码"),
            content=ft.Column([
                ft.Text("ZIP 文件需要密码才能解压:"),
                ft.Text(base_name, weight=ft.FontWeight.BOLD),
                pwd_field,
                error_text,
            ], tight=True, spacing=10, width=300),
            actions=[
                ft.TextButton("取消", on_click=on_cancel),
                ft.FilledButton("解锁并转换", on_click=on_unlock),
            ],
        )
        self.zip_ctx["dlg"] = dlg
        self.page.open(dlg)
        self.zip_progress.visible = False
        self.page.update()

    # ===================== 合并列表管理 =====================
    def _rebuild_merge_list(self):
        self.merge_list.controls.clear()
        for i, fpath in enumerate(self.merge_files):
            is_sel = i in self.selected_indices
            self.merge_list.controls.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_400),
                        title=ft.Text(os.path.basename(fpath), size=13, max_lines=1),
                        subtitle=ft.Text(fpath, size=11, color=ft.Colors.GREY_500, max_lines=1),
                        trailing=ft.PopupMenuButton(
                            icon=ft.Icons.MORE_VERT,
                            items=[
                                ft.PopupMenuItem(text="移除", icon=ft.Icons.DELETE_OUTLINE,
                                                 on_click=lambda _, idx=i: self._remove_one(idx)),
                            ],
                        ),
                        on_click=lambda _, idx=i: self._toggle_select(idx),
                        bgcolor=ft.Colors.BLUE_50 if is_sel else None,
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                    border_radius=8,
                )
            )
        self._update_merge_buttons()
        self.page.update()

    def _toggle_select(self, idx):
        if idx in self.selected_indices:
            self.selected_indices.discard(idx)
        else:
            self.selected_indices.add(idx)
        self._rebuild_merge_list()

    def _remove_one(self, idx):
        if 0 <= idx < len(self.merge_files):
            self.merge_files.pop(idx)
        self.selected_indices.discard(idx)
        self.selected_indices.clear()
        self._rebuild_merge_list()

    def _remove_selected(self):
        if not self.selected_indices:
            return
        self.merge_files = [f for i, f in enumerate(self.merge_files) if i not in self.selected_indices]
        self.selected_indices.clear()
        self._rebuild_merge_list()

    def _move_up(self):
        if not self.selected_indices:
            return
        idx = min(self.selected_indices)
        if idx > 0:
            self.merge_files[idx], self.merge_files[idx - 1] = self.merge_files[idx - 1], self.merge_files[idx]
            new_sel = {idx - 1 if i == idx else i for i in self.selected_indices}
            self.selected_indices.clear()
            self.selected_indices.update(new_sel)
        self._rebuild_merge_list()

    def _move_down(self):
        if not self.selected_indices:
            return
        idx = max(self.selected_indices)
        if idx < len(self.merge_files) - 1:
            self.merge_files[idx], self.merge_files[idx + 1] = self.merge_files[idx + 1], self.merge_files[idx]
            new_sel = {idx + 1 if i == idx else i for i in self.selected_indices}
            self.selected_indices.clear()
            self.selected_indices.update(new_sel)
        self._rebuild_merge_list()

    def _update_merge_buttons(self):
        has_files = len(self.merge_files) > 0
        has_sel = len(self.selected_indices) > 0
        self.btn_remove.disabled = not has_sel
        self.btn_up.disabled = not has_sel or (has_sel and min(self.selected_indices) == 0)
        self.btn_down.disabled = not has_sel or (has_sel and max(self.selected_indices) == len(self.merge_files) - 1)
        self.btn_merge.disabled = not has_files
        self.merge_count.value = f" ({len(self.merge_files)} 个文件)" if has_files else ""

    def _do_merge(self):
        if not self.merge_files:
            return
        name_field = ft.TextField(label="文件名", value="Merged", autofocus=True)

        def on_ok(e):
            name = name_field.value.strip()
            if not name:
                return
            self.page.close(self._merge_dlg)
            out = os.path.join(self.output_dir, name)
            try:
                result = merge_pdfs(self.merge_files, out)
                self.add_log(f"✅ 合并完成: {result}  ({len(self.merge_files)} 个文件)")
                self.show_snack("合并完成！")
            except Exception as ex:
                self.add_log(f"❌ 合并错误: {ex}")
                self.show_snack(str(ex), is_error=True)

        self._merge_dlg = ft.AlertDialog(
            title=ft.Text("保存合并文件"),
            content=ft.Column([
                ft.Text("请输入合并后的文件名:"),
                name_field,
            ], tight=True, width=300),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self.page.close(self._merge_dlg)),
                ft.FilledButton("合并", on_click=on_ok),
            ],
        )
        self.page.open(self._merge_dlg)

    # ===================== 拆分 =====================
    def _do_split(self):
        if not self.split_pdf_path:
            self.show_snack("请先选择一个 PDF 文件", is_error=True)
            return
        try:
            base = os.path.splitext(os.path.basename(self.split_pdf_path))[0]
            mode_val = self.split_mode.value
            if mode_val == "all":
                d, count = split_all_pages(self.split_pdf_path, self.output_dir)
                self.add_log(f"✅ 拆分完成: {d}  ({count} 页)")
                self.show_snack(f"已拆分为 {count} 个单页 PDF")
            elif mode_val == "png":
                raw = self.split_page_entry.value.strip() or None
                dpi_val = int(self.split_dpi_dd.value or 144)
                scale = dpi_val / 72.0
                d, count = extract_pages_to_images(self.split_pdf_path, self.output_dir, raw, scale)
                self.add_log(f"✅ 导出完成: {d}  ({count} 张 PNG, {dpi_val} DPI)")
                self.show_snack(f"已导出 {count} 张图片到 {os.path.basename(d)}")
                os.startfile(d)
            else:
                raw = self.split_page_entry.value.strip()
                if not raw:
                    self.show_snack("请输入页码范围", is_error=True)
                    return
                out = os.path.join(self.output_dir, base + "_Extracted.pdf")
                result, count = extract_pages_range(self.split_pdf_path, out, raw)
                self.add_log(f"✅ 提取完成: {result}  ({count} 页)")
                self.show_snack(f"已提取 {count} 页")
        except ValueError as ex:
            self.add_log(f"❌ 拆分错误: {ex}")
            self.show_snack(str(ex), is_error=True)
        except RuntimeError as ex:
            self.add_log(f"❌ 缺少依赖: {ex}")
            self.show_snack(str(ex), is_error=True)
        except Exception as ex:
            self.add_log(f"❌ 拆分错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    # ===================== 签名 =====================
    def _do_sign(self):
        if not self.sign_pdf_path:
            self.show_snack("请先选择一个 PDF 文件", is_error=True)
            return
        if not self.sign_img_path:
            self.show_snack("请先选择一个签名图片", is_error=True)
            return
        try:
            base = os.path.splitext(os.path.basename(self.sign_pdf_path))[0]
            reader = PdfReader(self.sign_pdf_path)
            total_pages = len(reader.pages)
            if self.sign_page_mode.value == "all":
                target_pages = set(range(1, total_pages + 1))
            else:
                try:
                    pn = int(self.sign_page_num.value)
                    if pn < 1 or pn > total_pages:
                        self.show_snack(f"页码超出范围 (1-{total_pages})", is_error=True)
                        return
                    target_pages = {pn}
                except ValueError:
                    self.show_snack("请输入有效页码", is_error=True)
                    return
            pos = self.sign_position.value
            scale = self.sign_scale_slider.value / 100.0
            out = os.path.join(self.output_dir, f"{base}_Signed.pdf")
            result, count = sign_pdf(self.sign_pdf_path, self.sign_img_path, out, pos, scale, target_pages)
            self.add_log(f"✅ 签名完成: {result}  ({count} 页)")
            self.show_snack(f"签名完成！已签署 {count} 页")
        except Exception as ex:
            self.add_log(f"❌ 签名错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    # ===================== 加密 =====================
    def _do_protect(self):
        path = self.protect_pdf_path
        if not path:
            self.show_snack("请先选择一个 PDF 文件", is_error=True)
            return
        pwd = self.protect_pwd_field.value
        if not pwd:
            self.show_snack("请输入密码", is_error=True)
            return
        try:
            base = os.path.splitext(os.path.basename(path))[0]
            out = os.path.join(self.output_dir, f"{base}_Protected.pdf")
            owner_pwd = self.protect_owner_pwd_field.value or None
            result = encrypt_pdf(path, out, pwd, owner_pwd)
            self.add_log(f"✅ 加密完成: {result}")
            self.show_snack("PDF 加密完成！")
        except Exception as ex:
            self.add_log(f"❌ 加密错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    # ===================== 解密 =====================
    def _do_unlock(self):
        path = self.unlock_pdf_path
        if not path:
            self.show_snack("请先选择一个 PDF 文件", is_error=True)
            return
        try:
            enc, reader = is_encrypted(path)
            pwd = self.unlock_pwd_field.value if enc else None
            if enc and not pwd:
                self.show_snack("请输入密码", is_error=True)
                return
            base = os.path.splitext(os.path.basename(path))[0]
            out = os.path.join(self.output_dir, f"{base}_Unlocked.pdf")
            result = decrypt_pdf(path, out, pwd)
            if result is None:
                self.show_snack("密码错误", is_error=True)
                return
            self.add_log(f"✅ 解密完成: {result}")
            self.show_snack("PDF 解密完成！")
        except ValueError as ex:
            self.show_snack(str(ex), is_error=True)
        except Exception as ex:
            self.add_log(f"❌ 解密错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    # ===================== 旋转 =====================
    def _rebuild_rotate_list(self):
        self.rotate_list.controls.clear()
        for i, fpath in enumerate(self.rotate_files):
            self.rotate_list.controls.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_400),
                        title=ft.Text(os.path.basename(fpath), size=13, max_lines=1),
                        subtitle=ft.Text(fpath, size=11, color=ft.Colors.GREY_500, max_lines=1),
                        trailing=ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18,
                                               on_click=lambda _, idx=i: self._remove_rotate(idx)),
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                    border_radius=8,
                )
            )
        self._update_rotate_ui()
        self.page.update()

    def _remove_rotate(self, idx):
        if 0 <= idx < len(self.rotate_files):
            self.rotate_files.pop(idx)
        self._rebuild_rotate_list()

    def _update_rotate_ui(self):
        n = len(self.rotate_files)
        self.rotate_count.value = f" ({n} 个文件)" if n else ""
        self.rotate_page_mode.visible = (n == 1)
        self.rotate_page_entry.visible = (n == 1 and self.rotate_page_mode.value == "range")
        self.rotate_btn.disabled = (n == 0)

    def _on_rotate_page_mode_changed(self, e):
        self.rotate_page_entry.visible = (len(self.rotate_files) == 1 and self.rotate_page_mode.value == "range")
        self.page.update()

    def _do_rotate(self):
        if not self.rotate_files:
            self.show_snack("请先添加 PDF 文件", is_error=True)
            return
        angle_map = {"90cw": 90, "90ccw": -90, "180": 180}
        angle = angle_map.get(self.rotate_angle_dd.value, 90)
        angle_label = self.rotate_angle_dd.value.replace("90cw", "90CW").replace("90ccw", "90CCW")
        try:
            for fpath in self.rotate_files:
                reader = PdfReader(fpath)
                base = os.path.splitext(os.path.basename(fpath))[0]
                total = len(reader.pages)
                if len(self.rotate_files) == 1 and self.rotate_page_mode.value == "range":
                    pages = parse_page_range(self.rotate_page_entry.value, total)
                    if pages is None:
                        self.show_snack("无效的页码范围", is_error=True)
                        return
                else:
                    pages = set(range(1, total + 1))
                out = os.path.join(self.output_dir, f"{base}_Rotated_{angle_label}.pdf")
                result, count = rotate_pdf(fpath, out, angle, pages)
                self.add_log(f"✅ 旋转完成: {result}  ({count} 页)")
            self.show_snack(f"旋转完成！{len(self.rotate_files)} 个文件")
        except Exception as ex:
            self.add_log(f"❌ 旋转错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    # ===================== 裁剪 =====================
    def _rebuild_crop_list(self):
        self.crop_list.controls.clear()
        for i, fpath in enumerate(self.crop_files):
            self.crop_list.controls.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_400),
                        title=ft.Text(os.path.basename(fpath), size=13, max_lines=1),
                        subtitle=ft.Text(fpath, size=11, color=ft.Colors.GREY_500, max_lines=1),
                        trailing=ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18,
                                               on_click=lambda _, idx=i: self._remove_crop(idx)),
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                    border_radius=8,
                )
            )
        self._update_crop_ui()
        self.page.update()

    def _remove_crop(self, idx):
        if 0 <= idx < len(self.crop_files):
            self.crop_files.pop(idx)
        self._rebuild_crop_list()

    def _update_crop_ui(self):
        n = len(self.crop_files)
        self.crop_count.value = f" ({n} 个文件)" if n else ""
        self.crop_page_mode.visible = (n == 1)
        self.crop_page_entry.visible = (n == 1 and self.crop_page_mode.value == "range")
        self.crop_btn.disabled = (n == 0)

    def _on_crop_page_mode_changed(self, e):
        self.crop_page_entry.visible = (len(self.crop_files) == 1 and self.crop_page_mode.value == "range")
        self.page.update()

    def _do_crop(self):
        if not self.crop_files:
            self.show_snack("请先添加 PDF 文件", is_error=True)
            return
        try:
            mt = float(self.crop_top.value or 0)
            mb = float(self.crop_bottom.value or 0)
            ml = float(self.crop_left.value or 0)
            mr = float(self.crop_right.value or 0)
        except ValueError:
            self.show_snack("边距必须为数字", is_error=True)
            return
        try:
            for fpath in self.crop_files:
                reader = PdfReader(fpath)
                base = os.path.splitext(os.path.basename(fpath))[0]
                total = len(reader.pages)
                if len(self.crop_files) == 1 and self.crop_page_mode.value == "range":
                    pages = parse_page_range(self.crop_page_entry.value, total)
                    if pages is None:
                        self.show_snack("无效的页码范围", is_error=True)
                        return
                else:
                    pages = set(range(1, total + 1))
                out = os.path.join(self.output_dir, f"{base}_Cropped.pdf")
                result, count = crop_pdf(fpath, out, (mt, mb, ml, mr), pages)
                self.add_log(f"✅ 裁剪完成: {result}  ({count} 页)")
            self.show_snack(f"裁剪完成！{len(self.crop_files)} 个文件")
        except ValueError as ex:
            self.add_log(f"❌ 裁剪错误: {ex}")
            self.show_snack(str(ex), is_error=True)
        except Exception as ex:
            self.add_log(f"❌ 裁剪错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    # ===================== 水印 =====================
    def _rebuild_watermark_list(self):
        self.watermark_list.controls.clear()
        for i, fpath in enumerate(self.watermark_files):
            self.watermark_list.controls.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_400),
                        title=ft.Text(os.path.basename(fpath), size=13, max_lines=1),
                        subtitle=ft.Text(fpath, size=11, color=ft.Colors.GREY_500, max_lines=1),
                        trailing=ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18,
                                               on_click=lambda _, idx=i: self._remove_watermark(idx)),
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                    border_radius=8,
                )
            )
        self.page.update()

    def _remove_watermark(self, idx):
        if 0 <= idx < len(self.watermark_files):
            self.watermark_files.pop(idx)
        self._rebuild_watermark_list()

    def _collect_wm_settings(self):
        font_name = (self.wm_font_display.value or "").strip()
        if not font_name or font_name == "(无字体)":
            font_name = self.system_font_names[0] if self.system_font_names else ""
        return {
            "type": self.wm_type.value,
            "text": self.wm_text.value,
            "font_name": font_name,
            "font_path": self.system_font_paths.get(font_name, ""),
            "font_size": int(self.wm_font_size.value) if self.wm_font_size.value else 48,
            "color": self.wm_color_hex,
            "opacity": int(self.wm_opacity.value),
            "rotation": int(self.wm_rotation.value) if self.wm_rotation.value else 0,
            "img_scale": int(self.wm_img_scale.value) if self.wm_img_scale.value else 50,
            "img_path": self.watermark_img_path,
            "vert": self.wm_vert.value,
            "horiz": self.wm_horiz.value,
            "offset_x": int(self.wm_offset_x.value or 0),
            "offset_y": int(self.wm_offset_y.value or 0),
            "layer": self.wm_layer_mode.value,
            "page_mode": self.wm_page_mode.value,
            "page_entry": self.wm_page_entry.value,
        }

    def _apply_wm_settings(self, s):
        self.wm_type.value = s.get("type", "text")
        self.wm_text.value = s.get("text", "")
        font_name = s.get("font_name", "") or s.get("font", "")
        if font_name and font_name in self.system_font_paths:
            self._select_font(font_name)
        elif self.system_font_names:
            self._select_font(self.system_font_names[0])
        self.wm_font_size.value = str(s.get("font_size", 48))
        color_val = s.get("color", "#000000")
        rgb = parse_color(color_val)
        self.wm_color_hex = "#{:02X}{:02X}{:02X}".format(*rgb)
        self.wm_color_swatch.bgcolor = self.wm_color_hex
        self.wm_color_hex_field.value = self.wm_color_hex
        self.wm_opacity.value = s.get("opacity", 30)
        self.wm_rotation.value = str(s.get("rotation", 0))
        self.wm_img_scale.value = s.get("img_scale", 50)
        self.wm_vert.value = s.get("vert", "center")
        self.wm_horiz.value = s.get("horiz", "center")
        self.wm_offset_x.value = str(s.get("offset_x", "0"))
        self.wm_offset_y.value = str(s.get("offset_y", "0"))
        self.wm_layer_mode.value = s.get("layer", "front")
        self.wm_page_mode.value = s.get("page_mode", "all")
        self.wm_page_entry.value = s.get("page_entry", "")
        self._update_wm_visibility()
        self.page.update()

    def _save_current_preset(self):
        name = self.wm_preset_name.value.strip()
        if not name:
            self.show_snack("请输入预设名称", is_error=True)
            return
        self.watermark_presets[name] = self._collect_wm_settings()
        save_presets(self.watermark_presets)
        self._rebuild_preset_dropdown()
        self.add_log(f"预设已保存: {name}")
        self.show_snack(f"预设「{name}」已保存")

    def _load_selected_preset(self):
        name = self.wm_preset_dd.value
        if not name or name not in self.watermark_presets:
            return
        self._apply_wm_settings(self.watermark_presets[name])
        self.add_log(f"预设已加载: {name}")
        self.show_snack(f"预设「{name}」已加载")

    def _delete_selected_preset(self):
        name = self.wm_preset_dd.value
        if not name or name not in self.watermark_presets:
            return
        del self.watermark_presets[name]
        save_presets(self.watermark_presets)
        self._rebuild_preset_dropdown()
        self.add_log(f"预设已删除: {name}")
        self.show_snack(f"预设「{name}」已删除")

    def _rebuild_preset_dropdown(self):
        self.wm_preset_dd.options = [ft.dropdown.Option(k, k) for k in sorted(self.watermark_presets.keys())]
        self.wm_preset_dd.value = None
        self.page.update()

    def _update_wm_visibility(self):
        is_text = self.wm_type.value == "text"
        self.wm_text.visible = is_text
        self.wm_font_display.visible = is_text
        self.wm_font_btn.visible = is_text
        self.wm_font_size.visible = is_text
        self.wm_color_swatch.visible = is_text
        self.wm_color_hex_field.visible = is_text
        self.wm_img_scale.visible = not is_text
        self.wm_img_btn.visible = not is_text
        self.watermark_img_label.visible = not is_text
        self.wm_page_entry.visible = self.wm_page_mode.value == "range"

    def _do_watermark_preview(self):
        if not self.watermark_files:
            self.show_snack("请先添加 PDF 文件", is_error=True)
            return
        try:
            preview_path = os.path.join(self.output_dir, "_watermark_preview.pdf")
            preview_watermark(self.watermark_files[0], preview_path, self._collect_wm_settings())
            self.add_log(f"预览已生成: {preview_path}")
            self.show_snack("正在打开预览...")
            os.startfile(preview_path)
        except ValueError as ex:
            self.show_snack(str(ex), is_error=True)
        except Exception as ex:
            self.add_log(f"❌ 预览错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    def _do_watermark_apply(self):
        if not self.watermark_files:
            self.show_snack("请先添加 PDF 文件", is_error=True)
            return
        params = self._collect_wm_settings()
        if params["type"] == "text" and not params["text"]:
            self.show_snack("请输入水印文本", is_error=True)
            return
        if params["type"] != "text" and not params["img_path"]:
            self.show_snack("请选择水印图片", is_error=True)
            return
        try:
            for fpath in self.watermark_files:
                base = os.path.splitext(os.path.basename(fpath))[0]
                out = os.path.join(self.output_dir, f"{base}_Watermarked.pdf")
                result, count = apply_watermark_to_pdf(fpath, out, params)
                self.add_log(f"✅ 水印完成: {result}  ({count} 页)")
            self.show_snack(f"水印添加完成！{len(self.watermark_files)} 个文件")
        except ValueError as ex:
            self.show_snack(str(ex), is_error=True)
        except Exception as ex:
            self.add_log(f"❌ 水印错误: {ex}")
            self.show_snack(str(ex), is_error=True)

    # ===================== 设置 =====================
    def _is_startup_enabled(self):
        return os.path.exists(self.STARTUP_VBS)

    def _set_startup(self, enabled):
        if enabled:
            vbs = (f'Set ws = CreateObject("WScript.Shell")\n'
                   f'ws.Run "pythonw ""{self._script_dir}\\\\main.py""", 0, False\n')
            try:
                with open(self.STARTUP_VBS, 'w') as f:
                    f.write(vbs)
                return True
            except Exception:
                return False
        else:
            try:
                if os.path.exists(self.STARTUP_VBS):
                    os.remove(self.STARTUP_VBS)
                return True
            except Exception:
                return False

    def _show_settings(self, _):
        top_switch = ft.Switch(value=self.page.window.always_on_top)
        startup_switch = ft.Switch(value=self._is_startup_enabled())

        def on_top_change(e):
            self.page.window.always_on_top = top_switch.value
            self.page.update()

        def on_startup_change(e):
            ok = self._set_startup(startup_switch.value)
            if not ok:
                startup_switch.value = self._is_startup_enabled()
                self.show_snack("开机自启设置失败，请检查权限", is_error=True)
            self.page.update()

        top_switch.on_change = on_top_change
        startup_switch.on_change = on_startup_change

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
                            ft.Text("开机自启动", weight=ft.FontWeight.W_500, size=14),
                            ft.Text("系统启动时自动运行本程序", size=12, color=ft.Colors.GREY_600),
                        ], expand=True),
                        startup_switch,
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(vertical=8),
                ),
                ft.Divider(height=1),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("拖放导入", weight=ft.FontWeight.W_500, size=14),
                            ft.Text("将 PDF / ZIP 文件直接拖入窗口即可导入", size=12,
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
    def _handle_dropped_files(self, files):
        if not files:
            return
        pdfs = [f for f in files if f.lower().endswith('.pdf')]
        zips = [f for f in files if f.lower().endswith('.zip')]
        imgs = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp', '.gif'))]
        others = [f for f in files if f not in pdfs and f not in zips and f not in imgs]

        if len(files) == 1 and zips:
            zip_path = zips[0]
            base = os.path.splitext(os.path.basename(zip_path))[0]
            self.zip_ctx["zip_path"] = zip_path
            self.zip_ctx["base_name"] = base
            self.zip_progress.visible = True
            self.page.update()
            self._do_zip_convert(zip_path, base)
            self.tabs.selected_index = 0
            self.add_log(f"📥 拖放导入 ZIP: {os.path.basename(zip_path)}")
        elif pdfs:
            tab_idx = self.tabs.selected_index
            if tab_idx == 1:
                self.merge_files.extend(pdfs)
                self._rebuild_merge_list()
            elif tab_idx == 7:
                self.rotate_files.extend(pdfs)
                self._rebuild_rotate_list()
            elif tab_idx == 8:
                self.crop_files.extend(pdfs)
                self._rebuild_crop_list()
            elif tab_idx == 9:
                self.watermark_files.extend(pdfs)
                self._rebuild_watermark_list()
            elif tab_idx == 3:
                self.sign_pdf_path = pdfs[0]
                self.sign_pdf_label.value = os.path.basename(pdfs[0])
            elif tab_idx == 4:
                self.protect_pdf_path = pdfs[0]
                self.protect_pdf_label.value = os.path.basename(pdfs[0])
            elif tab_idx == 5:
                path = pdfs[0]
                self.unlock_pdf_path = path
                self.unlock_pdf_label.value = os.path.basename(path)
                try:
                    enc, _ = is_encrypted(path)
                    self.unlock_status.value = "🔒 已加密" if enc else "🔓 未加密"
                    self.unlock_status.color = ft.Colors.RED_600 if enc else ft.Colors.GREEN_700
                    self.unlock_pwd_field.visible = enc
                    self.unlock_btn.disabled = False
                except Exception:
                    pass
            self.add_log(f"📥 拖放导入 {len(pdfs)} 个 PDF 文件")
            self.show_snack(f"已导入 {len(pdfs)} 个 PDF 文件")
        elif imgs:
            self.add_log(f"📥 拖放导入 {len(imgs)} 张图片（请先打包为 ZIP 再转换）")
            self.show_snack("图片文件请打包为 ZIP 后再拖入", is_error=True)
        if others:
            self.add_log(f"⚠ 忽略 {len(others)} 个不支持的文件类型")
        self.page.update()

    async def _poll_drops(self):
        while True:
            files = get_drop(timeout=0.01)
            if files:
                self._handle_dropped_files(files)
            await asyncio.sleep(0.3)

    # ===================== 字体选择 =====================
    def _select_font(self, name):
        self.wm_font_display.value = name
        self.page.update()

    def _show_font_picker(self, _):
        search = ft.TextField(label="搜索字体", autofocus=True, width=360)
        font_list = ft.ListView(expand=True, spacing=0)

        def _rebuild_font_list():
            font_list.controls.clear()
            q = search.value.lower()
            filtered = [n for n in self.system_font_names if q in n.lower()]
            for name in filtered:
                family = self.system_font_families.get(name, name)
                font_list.controls.append(
                    ft.Container(
                        content=ft.TextButton(
                            content=ft.Text(name, font_family=family, size=15),
                            on_click=lambda _, n=name: _on_font_picked(n),
                            style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=8, vertical=4)),
                        ),
                        padding=ft.padding.only(left=4),
                    )
                )
            self.page.update()

        search.on_change = lambda _: _rebuild_font_list()

        def _on_font_picked(name):
            self._select_font(name)
            self.page.close(font_dlg)
            self.page.update()

        _rebuild_font_list()
        font_dlg = ft.AlertDialog(
            title=ft.Text("选择字体"),
            content=ft.Column([search, ft.Divider(height=4), font_list],
                              height=520, width=380, spacing=4),
            actions=[ft.TextButton("取消", on_click=lambda _: self.page.close(font_dlg))],
        )
        self.page.open(font_dlg)

    # ===================== 颜色选择 =====================
    def _on_hex_change(self, val):
        val = val.strip()
        if val.startswith('#'):
            try:
                rgb = tuple(int(val.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                if all(0 <= c <= 255 for c in rgb) and len(val.lstrip('#')) == 6:
                    self.wm_color_hex = val.upper()
                    self.wm_color_swatch.bgcolor = self.wm_color_hex
            except Exception:
                pass
        self.page.update()

    def _show_color_picker(self):
        grid_items = []
        for name, hex_, _rgb in COLOR_PALETTE:
            grid_items.append(
                ft.Container(
                    width=32, height=32,
                    bgcolor=hex_,
                    border_radius=4,
                    tooltip=name,
                    on_click=lambda _, h=hex_: _on_color_picked(h),
                    border=ft.border.all(2, ft.Colors.WHITE) if hex_ == self.wm_color_hex else None,
                    shadow=ft.BoxShadow(blur_radius=1, color=ft.Colors.GREY_400) if hex_ == self.wm_color_hex else None,
                )
            )

        def _on_color_picked(hex_):
            self.wm_color_hex = hex_
            self.wm_color_swatch.bgcolor = hex_
            self.wm_color_hex_field.value = hex_
            self.page.close(color_dlg)
            self.page.update()

        cols = 10
        color_rows = []
        for i in range(0, len(grid_items), cols):
            color_rows.append(ft.Row(grid_items[i:i+cols], spacing=4))

        color_dlg = ft.AlertDialog(
            title=ft.Text("选择颜色"),
            content=ft.Column([
                ft.Row([
                    ft.Text("当前:", size=13),
                    ft.Container(width=24, height=24, bgcolor=self.wm_color_hex, border_radius=4,
                                 border=ft.border.all(1, ft.Colors.OUTLINE)),
                    ft.Text(self.wm_color_hex, size=13, weight=ft.FontWeight.W_500),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=8),
                ft.Column(color_rows, spacing=4, scroll=ft.ScrollMode.AUTO, height=280),
            ], spacing=8, width=420),
            actions=[ft.TextButton("取消", on_click=lambda _: self.page.close(color_dlg))],
        )
        self.page.open(color_dlg)

    # ===================== UI 构建 =====================
    def build(self):
        """构建完整的 PDF 工具箱 UI，返回 (top_bar, tabs, log_panel) 三元组。"""
        page = self.page

        # --- FilePicker 实例 ---
        dir_picker = ft.FilePicker(on_result=self._on_dir_pick)
        zip_picker = ft.FilePicker(on_result=self._on_zip_pick)
        multi_picker = ft.FilePicker(on_result=self._on_multi_pdf_pick)
        single_picker = ft.FilePicker(on_result=self._on_single_pdf_pick)
        sign_pdf_picker = ft.FilePicker(on_result=self._on_sign_pdf_pick)
        sign_img_picker = ft.FilePicker(on_result=self._on_sign_img_pick)
        protect_pdf_picker = ft.FilePicker(on_result=self._on_protect_pdf_pick)
        unlock_pdf_picker = ft.FilePicker(on_result=self._on_unlock_pdf_pick)
        rotate_picker = ft.FilePicker(on_result=self._on_rotate_pdf_pick)
        crop_picker = ft.FilePicker(on_result=self._on_crop_pdf_pick)
        watermark_pdf_picker = ft.FilePicker(on_result=self._on_watermark_pdf_pick)
        watermark_img_picker = ft.FilePicker(on_result=self._on_watermark_img_pick)

        page.overlay.extend([dir_picker, zip_picker, multi_picker, single_picker,
                             sign_pdf_picker, sign_img_picker, protect_pdf_picker, unlock_pdf_picker,
                             rotate_picker, crop_picker, watermark_pdf_picker, watermark_img_picker])

        # --- 日志 ---
        self.log_list = ft.ListView(expand=True, auto_scroll=True, spacing=2)

        # --- 顶部栏 ---
        self.dir_text = ft.Text(self.output_dir, color=ft.Colors.BLUE_700, size=13, italic=True,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

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
                    icon=ft.Icons.SETTINGS,
                    icon_size=20,
                    tooltip="设置",
                    icon_color=ft.Colors.GREY_600,
                    on_click=self._show_settings,
                ),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            bgcolor=ft.Colors.GREY_100,
            border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )

        # ========== 子标签页构建 ==========
        # --- 标签页 1: ZIP 转 PDF ---
        self.zip_progress = ft.ProgressRing(visible=False, width=32, height=32)
        zip_tab_content = ft.Container(
            content=ft.Column([
                ft.Text("将 ZIP 压缩包中的图片转换为 PDF", size=15, weight=ft.FontWeight.W_500),
                ft.Text("支持格式: PNG, JPG, JPEG, BMP, TIFF, WebP, GIF, JFIF", size=12, color=ft.Colors.GREY_600),
                ft.Divider(height=20),
                ft.Container(
                    content=ft.Column([
                        ft.FilledButton(
                            "选择 ZIP 并转换",
                            icon=ft.Icons.ARCHIVE_OUTLINED,
                            on_click=lambda _: zip_picker.pick_files(
                                dialog_title="选择 ZIP 文件",
                                allowed_extensions=["zip"],
                                allow_multiple=False,
                                file_type=ft.FilePickerFileType.CUSTOM,
                            ),
                            style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=40, vertical=16)),
                        ),
                        self.zip_progress,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
                    padding=40, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                    bgcolor=ft.Colors.WHITE,
                ),
            ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 2: 合并 PDF ---
        self.merge_count = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.merge_list = ft.ListView(expand=True, spacing=2)

        self.btn_remove = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="移除选中", disabled=True,
                                        on_click=lambda _: self._remove_selected())
        self.btn_up = ft.IconButton(icon=ft.Icons.ARROW_UPWARD, tooltip="上移", disabled=True,
                                    on_click=lambda _: self._move_up())
        self.btn_down = ft.IconButton(icon=ft.Icons.ARROW_DOWNWARD, tooltip="下移", disabled=True,
                                      on_click=lambda _: self._move_down())
        self.btn_merge = ft.FilledButton("合并", icon=ft.Icons.MERGE_TYPE, disabled=True,
                                         on_click=lambda _: self._do_merge())

        merge_tab_content = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Text("待合并列表", size=15, weight=ft.FontWeight.W_500), self.merge_count]),
                        ft.Divider(height=4), self.merge_list,
                    ], expand=True),
                    expand=True, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                    bgcolor=ft.Colors.WHITE, padding=12,
                ),
                ft.Container(
                    content=ft.Column([
                        ft.IconButton(icon=ft.Icons.ADD, tooltip="添加 PDF 文件", icon_color=ft.Colors.BLUE_600,
                                      on_click=lambda _: multi_picker.pick_files(
                                          dialog_title="选择要合并的 PDF 文件", allowed_extensions=["pdf"],
                                          allow_multiple=True, file_type=ft.FilePickerFileType.CUSTOM)),
                        ft.Divider(height=4),
                        self.btn_up, self.btn_down, ft.Divider(height=4),
                        self.btn_remove, ft.Divider(height=16),
                        self.btn_merge,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                    padding=ft.padding.symmetric(horizontal=8, vertical=12),
                ),
            ], spacing=12, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 3: 拆分/提取 PDF ---
        self.split_mode = ft.RadioGroup(
            value="all",
            content=ft.Column([
                ft.Radio(value="all", label="拆分为单页 PDF"),
                ft.Radio(value="range", label="提取指定页码为 PDF"),
                ft.Radio(value="png", label="导出页面为 PNG 图片"),
            ], spacing=8),
        )
        self.split_label = ft.Text("未选择文件", size=12, color=ft.Colors.GREY_600)
        self.split_page_entry = ft.TextField(label="页码范围", hint_text="例如: 1,3,5-10", visible=False, width=260)
        self.split_dpi_dd = ft.Dropdown(
            label="分辨率", value="144", width=120, visible=False,
            options=[
                ft.dropdown.Option("72", "72 DPI"), ft.dropdown.Option("96", "96 DPI"),
                ft.dropdown.Option("144", "144 DPI"), ft.dropdown.Option("200", "200 DPI"),
                ft.dropdown.Option("300", "300 DPI"),
            ],
        )
        split_exec_btn = ft.FilledButton("执行拆分", icon=ft.Icons.CALL_SPLIT, on_click=lambda _: self._do_split())

        def on_split_mode_changed(e):
            mode = self.split_mode.value
            self.split_page_entry.visible = mode in ("range", "png")
            self.split_dpi_dd.visible = (mode == "png")
            split_exec_btn.text = "导出 PNG" if mode == "png" else "执行拆分"
            split_exec_btn.icon = ft.Icons.IMAGE_OUTLINED if mode == "png" else ft.Icons.CALL_SPLIT
            page.update()
        self.split_mode.on_change = on_split_mode_changed

        split_tab_content = ft.Container(
            content=ft.Column([
                ft.Text("拆分或提取 PDF 页面", size=15, weight=ft.FontWeight.W_500),
                ft.Divider(height=12),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.OutlinedButton("浏览 PDF", icon=ft.Icons.FILE_OPEN,
                                on_click=lambda _: single_picker.pick_files(
                                    dialog_title="选择 PDF 文件", allowed_extensions=["pdf"],
                                    allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM)),
                            self.split_label,
                        ], spacing=12),
                        ft.Divider(height=8),
                        self.split_mode,
                        ft.Row([self.split_page_entry, self.split_dpi_dd], spacing=12,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Divider(height=8),
                        split_exec_btn,
                    ], spacing=12),
                    padding=24, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), bgcolor=ft.Colors.WHITE,
                ),
            ], spacing=8),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 4: 签名 PDF ---
        self.sign_pdf_label = ft.Text("未选择文件", size=12, color=ft.Colors.GREY_600)
        self.sign_img_label = ft.Text("未选择图片", size=12, color=ft.Colors.GREY_600)
        self.sign_page_mode = ft.RadioGroup(
            value="all",
            content=ft.Row([ft.Radio(value="all", label="所有页"), ft.Radio(value="single", label="指定页")], spacing=16),
        )
        self.sign_page_num = ft.TextField(label="页码", value="1", width=80, visible=False)

        def on_sign_page_mode_changed(e):
            self.sign_page_num.visible = self.sign_page_mode.value == "single"
            page.update()
        self.sign_page_mode.on_change = on_sign_page_mode_changed

        self.sign_position = ft.Dropdown(
            label="签名位置", value="bottom-right", width=200,
            options=[
                ft.dropdown.Option("bottom-right", "右下角"), ft.dropdown.Option("bottom-left", "左下角"),
                ft.dropdown.Option("top-right", "右上角"), ft.dropdown.Option("top-left", "左上角"),
                ft.dropdown.Option("center", "居中"),
            ],
        )
        self.sign_scale_slider = ft.Slider(min=10, max=100, value=30, divisions=9, label="{value}%", width=220)
        sign_scale_text = ft.Text("30%", size=12)

        def on_scale_changed(e):
            sign_scale_text.value = f"{int(self.sign_scale_slider.value)}%"
            page.update()
        self.sign_scale_slider.on_change = on_scale_changed

        sign_tab_content = ft.Container(
            content=ft.Column([
                ft.Text("为 PDF 添加签名图片", size=15, weight=ft.FontWeight.W_500),
                ft.Divider(height=12),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.OutlinedButton("选择 PDF", icon=ft.Icons.FILE_OPEN,
                                on_click=lambda _: sign_pdf_picker.pick_files(
                                    dialog_title="选择要签名的 PDF", allowed_extensions=["pdf"],
                                    allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM)),
                            self.sign_pdf_label,
                        ], spacing=12),
                        ft.Row([
                            ft.OutlinedButton("选择签名图片", icon=ft.Icons.IMAGE_OUTLINED,
                                on_click=lambda _: sign_img_picker.pick_files(
                                    dialog_title="选择签名图片", allowed_extensions=["png", "jpg", "jpeg"],
                                    allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM)),
                            self.sign_img_label,
                        ], spacing=12),
                        ft.Divider(height=8),
                        ft.Text("签名页面:", weight=ft.FontWeight.W_500, size=13),
                        ft.Row([self.sign_page_mode, self.sign_page_num], spacing=12,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Divider(height=8),
                        ft.Row([
                            self.sign_position,
                            ft.Column([
                                ft.Text("缩放比例:", size=12),
                                ft.Row([self.sign_scale_slider, sign_scale_text], spacing=4),
                            ], spacing=2),
                        ], spacing=20, vertical_alignment=ft.CrossAxisAlignment.START),
                        ft.Divider(height=8),
                        ft.FilledButton("添加签名", icon=ft.Icons.DRAW_OUTLINED, on_click=lambda _: self._do_sign()),
                    ], spacing=12),
                    padding=24, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), bgcolor=ft.Colors.WHITE,
                ),
            ], spacing=8),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 5: 加密 PDF ---
        self.protect_pdf_label = ft.Text("未选择文件", size=12, color=ft.Colors.GREY_600)
        self.protect_pwd_field = ft.TextField(label="用户密码", password=True, can_reveal_password=True, width=280)
        self.protect_owner_pwd_field = ft.TextField(label="所有者密码 (可选)", password=True, can_reveal_password=True, width=280)

        protect_tab_content = ft.Container(
            content=ft.Column([
                ft.Text("为 PDF 添加密码保护", size=15, weight=ft.FontWeight.W_500),
                ft.Divider(height=12),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.OutlinedButton("选择 PDF", icon=ft.Icons.FILE_OPEN,
                                on_click=lambda _: protect_pdf_picker.pick_files(
                                    dialog_title="选择要加密的 PDF", allowed_extensions=["pdf"],
                                    allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM)),
                            self.protect_pdf_label,
                        ], spacing=12),
                        ft.Divider(height=8),
                        self.protect_pwd_field, self.protect_owner_pwd_field, ft.Divider(height=8),
                        ft.FilledButton("加密 PDF", icon=ft.Icons.LOCK_OUTLINED, on_click=lambda _: self._do_protect()),
                    ], spacing=12),
                    padding=24, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), bgcolor=ft.Colors.WHITE,
                ),
            ], spacing=8),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 6: 解密 PDF ---
        self.unlock_pdf_label = ft.Text("未选择文件", size=12, color=ft.Colors.GREY_600)
        self.unlock_status = ft.Text("", size=13, weight=ft.FontWeight.W_500)
        self.unlock_pwd_field = ft.TextField(label="密码", password=True, can_reveal_password=True, visible=False, width=280)
        self.unlock_btn = ft.FilledButton("解密 PDF", icon=ft.Icons.LOCK_OPEN_OUTLINED, disabled=True,
                                          on_click=lambda _: self._do_unlock())

        unlock_tab_content = ft.Container(
            content=ft.Column([
                ft.Text("移除 PDF 的密码保护", size=15, weight=ft.FontWeight.W_500),
                ft.Divider(height=12),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.OutlinedButton("选择 PDF", icon=ft.Icons.FILE_OPEN,
                                on_click=lambda _: unlock_pdf_picker.pick_files(
                                    dialog_title="选择要解密的 PDF", allowed_extensions=["pdf"],
                                    allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM)),
                            self.unlock_pdf_label,
                        ], spacing=12),
                        ft.Divider(height=8),
                        self.unlock_status, self.unlock_pwd_field, ft.Divider(height=8),
                        self.unlock_btn,
                    ], spacing=12),
                    padding=24, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), bgcolor=ft.Colors.WHITE,
                ),
            ], spacing=8),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 7: 旋转 PDF ---
        self.rotate_list = ft.ListView(expand=True, spacing=2)
        self.rotate_count = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.rotate_page_mode = ft.RadioGroup(
            value="all",
            content=ft.Row([
                ft.Radio(value="all", label="所有页"),
                ft.Radio(value="range", label="指定页码 (如: 1,3,5-10)"),
            ], spacing=16),
            visible=False, on_change=self._on_rotate_page_mode_changed,
        )
        self.rotate_page_entry = ft.TextField(label="页码范围", hint_text="1,3,5-10", width=200, visible=False)
        self.rotate_angle_dd = ft.Dropdown(
            label="旋转角度", value="90cw", width=180,
            options=[
                ft.dropdown.Option("90cw", "顺时针 90°"),
                ft.dropdown.Option("90ccw", "逆时针 90°"),
                ft.dropdown.Option("180", "180°"),
            ],
        )
        self.rotate_btn = ft.FilledButton("旋转", icon=ft.Icons.ROTATE_90_DEGREES_CW, disabled=True,
                                          on_click=lambda _: self._do_rotate())

        rotate_tab_content = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Text("待旋转列表", size=15, weight=ft.FontWeight.W_500), self.rotate_count]),
                        ft.Divider(height=4), self.rotate_list,
                    ], expand=True),
                    expand=True, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), bgcolor=ft.Colors.WHITE, padding=12,
                ),
                ft.Container(
                    content=ft.Column([
                        ft.IconButton(icon=ft.Icons.ADD, tooltip="添加 PDF", icon_color=ft.Colors.BLUE_600,
                            on_click=lambda _: rotate_picker.pick_files(
                                dialog_title="选择要旋转的 PDF", allowed_extensions=["pdf"],
                                allow_multiple=True, file_type=ft.FilePickerFileType.CUSTOM)),
                        ft.Divider(height=12),
                        self.rotate_page_mode, self.rotate_page_entry, ft.Divider(height=12),
                        self.rotate_angle_dd, ft.Divider(height=16), self.rotate_btn,
                    ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(horizontal=12, vertical=12),
                ),
            ], spacing=12, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 8: 裁剪 PDF ---
        self.crop_list = ft.ListView(expand=True, spacing=2)
        self.crop_count = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.crop_page_mode = ft.RadioGroup(
            value="all",
            content=ft.Row([
                ft.Radio(value="all", label="所有页"),
                ft.Radio(value="range", label="指定页码 (如: 1,3,5-10)"),
            ], spacing=16),
            visible=False, on_change=self._on_crop_page_mode_changed,
        )
        self.crop_page_entry = ft.TextField(label="页码范围", hint_text="1,3,5-10", width=200, visible=False)
        self.crop_top = ft.TextField(label="上 (pt)", value="0", width=90, text_size=13)
        self.crop_bottom = ft.TextField(label="下 (pt)", value="0", width=90, text_size=13)
        self.crop_left = ft.TextField(label="左 (pt)", value="0", width=90, text_size=13)
        self.crop_right = ft.TextField(label="右 (pt)", value="0", width=90, text_size=13)
        self.crop_btn = ft.FilledButton("裁剪", icon=ft.Icons.CROP, disabled=True, on_click=lambda _: self._do_crop())

        crop_tab_content = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Text("待裁剪列表", size=15, weight=ft.FontWeight.W_500), self.crop_count]),
                        ft.Divider(height=4), self.crop_list,
                    ], expand=True),
                    expand=True, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), bgcolor=ft.Colors.WHITE, padding=12,
                ),
                ft.Container(
                    content=ft.Column([
                        ft.IconButton(icon=ft.Icons.ADD, tooltip="添加 PDF", icon_color=ft.Colors.BLUE_600,
                            on_click=lambda _: crop_picker.pick_files(
                                dialog_title="选择要裁剪的 PDF", allowed_extensions=["pdf"],
                                allow_multiple=True, file_type=ft.FilePickerFileType.CUSTOM)),
                        ft.Divider(height=12),
                        self.crop_page_mode, self.crop_page_entry, ft.Divider(height=12),
                        ft.Text("裁剪边距 (1pt ≈ 0.353mm):", size=12, weight=ft.FontWeight.W_500),
                        ft.Row([self.crop_top, self.crop_bottom], spacing=8),
                        ft.Row([self.crop_left, self.crop_right], spacing=8),
                        ft.Divider(height=16), self.crop_btn,
                    ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(horizontal=12, vertical=12),
                ),
            ], spacing=12, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 标签页 9: 水印 PDF ---
        self.watermark_list = ft.ListView(expand=True, spacing=2)

        self.wm_type = ft.RadioGroup(
            value="text",
            content=ft.Row([
                ft.Radio(value="text", label="文字水印"),
                ft.Radio(value="image", label="图片水印"),
            ], spacing=16),
        )
        self.wm_type.on_change = lambda _: self._update_wm_visibility() or page.update()

        self.wm_font_display = ft.TextField(
            label="字体",
            value=self.system_font_names[0] if self.system_font_names else "(无字体)",
            width=160, read_only=True, dense=True,
        )
        self.wm_font_btn = ft.IconButton(icon=ft.Icons.FONT_DOWNLOAD, tooltip="选择字体", icon_size=18,
                                         on_click=self._show_font_picker)
        self.wm_text = ft.TextField(label="水印文本", value="机密", width=200)
        _FONT_SIZES = ["8", "9", "10", "11", "12", "14", "16", "18", "20", "22", "24", "26", "28", "36", "48", "72", "96", "120"]
        self.wm_font_size = ft.Dropdown(label="字号", value="48", width=90,
                                        options=[ft.dropdown.Option(sz, sz) for sz in _FONT_SIZES])

        self.wm_color_swatch = ft.Container(
            width=28, height=28, bgcolor=self.wm_color_hex, border_radius=4,
            border=ft.border.all(1, ft.Colors.OUTLINE),
            on_click=lambda _: self._show_color_picker(),
        )
        self.wm_color_hex_field = ft.TextField(
            value=self.wm_color_hex, width=85, text_size=12, dense=True,
            on_change=lambda e: self._on_hex_change(e.control.value),
        )

        self.wm_img_scale = ft.Slider(min=10, max=200, value=50, divisions=19, label="{value}%", width=220, visible=False)
        self.wm_img_btn = ft.OutlinedButton("选择水印图片", icon=ft.Icons.IMAGE_OUTLINED, visible=False,
                                            on_click=lambda _: watermark_img_picker.pick_files(
                                                dialog_title="选择水印图片", allowed_extensions=["png", "jpg", "jpeg"],
                                                allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM))
        self.watermark_img_label = ft.Text("未选择", size=12, color=ft.Colors.GREY_600, visible=False)

        self.wm_opacity = ft.Slider(min=5, max=100, value=30, divisions=19, label="{value}%", width=220)
        _ROTATION_ANGLES = [("0", "0° 水平"), ("45", "45° 对角线"), ("-45", "-45° 对角线"), ("90", "90°"), ("-90", "-90°")]
        self.wm_rotation = ft.Dropdown(label="旋转角度", value="0", width=140,
                                       options=[ft.dropdown.Option(k, v) for k, v in _ROTATION_ANGLES])
        self.wm_layer_mode = ft.RadioGroup(
            value="front",
            content=ft.Row([ft.Radio(value="front", label="在内容之前"), ft.Radio(value="behind", label="在内容之后")], spacing=16),
        )
        self.wm_vert = ft.Dropdown(label="垂直位置", value="center", width=140,
                                   options=[ft.dropdown.Option("top", "顶部"), ft.dropdown.Option("center", "居中"), ft.dropdown.Option("bottom", "底部")])
        self.wm_horiz = ft.Dropdown(label="水平位置", value="center", width=140,
                                    options=[ft.dropdown.Option("left", "左"), ft.dropdown.Option("center", "居中"), ft.dropdown.Option("right", "右")])
        self.wm_offset_x = ft.TextField(label="X 偏移 (pt)", value="0", width=110, text_size=13)
        self.wm_offset_y = ft.TextField(label="Y 偏移 (pt)", value="0", width=110, text_size=13)

        self.wm_page_mode = ft.RadioGroup(
            value="all",
            content=ft.Row([
                ft.Radio(value="all", label="所有页"), ft.Radio(value="range", label="页码范围"),
                ft.Radio(value="even", label="仅偶数页"), ft.Radio(value="odd", label="仅奇数页"),
            ], spacing=8, wrap=True),
        )
        self.wm_page_mode.on_change = lambda _: self._update_wm_visibility() or page.update()
        self.wm_page_entry = ft.TextField(label="页码 (如 1,3,5-10)", hint_text="1,3,5-10", width=200, visible=False)

        self.wm_preset_dd = ft.Dropdown(label="已存预设", width=180,
                                        options=[ft.dropdown.Option(k, k) for k in sorted(self.watermark_presets.keys())])
        self.wm_preset_name = ft.TextField(label="预设名称", width=150, text_size=13)
        wm_preview_btn = ft.FilledButton("预览", icon=ft.Icons.VISIBILITY_OUTLINED, on_click=lambda _: self._do_watermark_preview())
        wm_apply_btn = ft.FilledButton("应用水印", icon=ft.Icons.BRANDING_WATERMARK, on_click=lambda _: self._do_watermark_apply())

        settings_col = ft.Column([
            ft.Text("水印类型", weight=ft.FontWeight.W_500, size=13), self.wm_type, ft.Divider(height=4),
            ft.Text("文字设置", weight=ft.FontWeight.W_500, size=13), self.wm_text,
            ft.Row([self.wm_font_display, self.wm_font_btn, self.wm_font_size], spacing=4,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([self.wm_color_swatch, self.wm_color_hex_field, self.wm_rotation,
                    ft.Text("不透明度", size=12), self.wm_opacity],
                   spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.wm_img_scale, self.wm_img_btn, self.watermark_img_label, ft.Divider(height=4),
            ft.Text("图层", weight=ft.FontWeight.W_500, size=13), self.wm_layer_mode, ft.Divider(height=4),
            ft.Text("位置", weight=ft.FontWeight.W_500, size=13),
            ft.Row([self.wm_vert, self.wm_horiz], spacing=8),
            ft.Row([self.wm_offset_x, self.wm_offset_y], spacing=8), ft.Divider(height=4),
            ft.Text("页面范围", weight=ft.FontWeight.W_500, size=13), self.wm_page_mode, self.wm_page_entry, ft.Divider(height=4),
            ft.Text("预设", weight=ft.FontWeight.W_500, size=13),
            ft.Row([self.wm_preset_name, ft.FilledButton("保存", icon=ft.Icons.SAVE, on_click=lambda _: self._save_current_preset())], spacing=8),
            ft.Row([self.wm_preset_dd, ft.IconButton(icon=ft.Icons.DOWNLOAD, tooltip="加载", on_click=lambda _: self._load_selected_preset()),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="删除", on_click=lambda _: self._delete_selected_preset())], spacing=4),
            ft.Divider(height=8),
            ft.Row([wm_preview_btn, wm_apply_btn], spacing=12, alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

        watermark_tab_content = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Text("待添加水印列表", size=15, weight=ft.FontWeight.W_500)]),
                        ft.Divider(height=4), self.watermark_list,
                    ], expand=True),
                    expand=True, border_radius=12,
                    border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), bgcolor=ft.Colors.WHITE, padding=12,
                ),
                ft.Container(
                    content=ft.Column([
                        ft.IconButton(icon=ft.Icons.ADD, tooltip="添加 PDF", icon_color=ft.Colors.BLUE_600,
                            on_click=lambda _: watermark_pdf_picker.pick_files(
                                dialog_title="选择要加水印的 PDF", allowed_extensions=["pdf"],
                                allow_multiple=True, file_type=ft.FilePickerFileType.CUSTOM)),
                        ft.Divider(height=4), settings_col,
                    ], spacing=0, expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(horizontal=12, vertical=12), width=330,
                ),
            ], spacing=12, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.padding.all(24), expand=True,
        )

        # --- 子选项卡 ---
        self.tabs = ft.Tabs(
            selected_index=0,
            scrollable=True,
            tabs=[
                ft.Tab(text="ZIP 转 PDF", icon=ft.Icons.ARCHIVE_OUTLINED, content=zip_tab_content),
                ft.Tab(text="合并 PDF", icon=ft.Icons.MERGE_TYPE, content=merge_tab_content),
                ft.Tab(text="拆分/提取 PDF", icon=ft.Icons.CALL_SPLIT, content=split_tab_content),
                ft.Tab(text="签名 PDF", icon=ft.Icons.DRAW_OUTLINED, content=sign_tab_content),
                ft.Tab(text="加密 PDF", icon=ft.Icons.LOCK_OUTLINED, content=protect_tab_content),
                ft.Tab(text="解密 PDF", icon=ft.Icons.LOCK_OPEN_OUTLINED, content=unlock_tab_content),
                ft.Tab(text="旋转 PDF", icon=ft.Icons.ROTATE_90_DEGREES_CW, content=rotate_tab_content),
                ft.Tab(text="裁剪 PDF", icon=ft.Icons.CROP, content=crop_tab_content),
                ft.Tab(text="水印 PDF", icon=ft.Icons.BRANDING_WATERMARK, content=watermark_tab_content),
            ],
            expand=True,
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

        # --- 初始选中第一个字体 ---
        if self.system_font_names:
            self._select_font(self.system_font_names[0])

        return top_bar, self.tabs, log_panel

    async def setup(self):
        """启用拖放并启动轮询（build 之后调用）。"""
        await asyncio.sleep(0.3)
        enable_dragdrop("全能 PDF 工具箱")
        self.page.run_task(self._poll_drops)
