"""
Image conversion using PIL/Pillow.
Supports resize, color mode, format conversion, and quality settings.
"""
import os
from PIL import Image
from modules.i18n import _


def _build_output_path(input_path, output_dir, output_format):
    base = os.path.splitext(os.path.basename(input_path))[0]
    ext = f".{output_format.lower()}"
    out = os.path.join(output_dir, f"{base}_converted{ext}")
    counter = 1
    while os.path.exists(out):
        out = os.path.join(output_dir, f"{base}_converted_{counter}{ext}")
        counter += 1
    return out


def convert_image(input_path, output_path, settings, progress_callback=None):
    """Convert an image file using PIL.

    Args:
        input_path: Source image path
        output_path: Destination path
        settings: dict with keys:
            img_resize_mode, img_max_width, img_max_height, img_scale_pct,
            img_keep_aspect, img_color_mode, quality
        progress_callback: callable(percent, status_label)

    Returns:
        (success: bool, error_message: str or None)
    """
    try:
        if progress_callback:
            progress_callback(10.0, _("读取中"))

        img = Image.open(input_path)

        if progress_callback:
            progress_callback(25.0, _("调整尺寸"))

        # --- Resize ---
        resize_mode = settings.get("img_resize_mode", "original")
        keep_aspect = settings.get("img_keep_aspect", True)
        orig_w, orig_h = img.size

        new_w, new_h = orig_w, orig_h

        if resize_mode == "dimensions":
            mw = settings.get("img_max_width", "")
            mh = settings.get("img_max_height", "")
            target_w = int(mw) if mw and mw.strip().isdigit() else None
            target_h = int(mh) if mh and mh.strip().isdigit() else None

            if target_w and target_h:
                if keep_aspect:
                    ratio = min(target_w / orig_w, target_h / orig_h)
                    new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
                else:
                    new_w, new_h = target_w, target_h
            elif target_w:
                new_w = target_w
                new_h = int(orig_h * (target_w / orig_w)) if keep_aspect else orig_h
            elif target_h:
                new_h = target_h
                new_w = int(orig_w * (target_h / orig_h)) if keep_aspect else orig_w

        elif resize_mode == "scale":
            sp = settings.get("img_scale_pct", "100")
            pct = float(sp) if sp and sp.strip() else 100.0
            if pct != 100.0:
                new_w, new_h = int(orig_w * pct / 100), int(orig_h * pct / 100)

        if (new_w, new_h) != (orig_w, orig_h) and new_w > 0 and new_h > 0:
            resample = Image.LANCZOS
            img = img.resize((new_w, new_h), resample)

        if progress_callback:
            progress_callback(50.0, _("转换色彩"))

        # --- Color mode ---
        color_mode = settings.get("img_color_mode", "original")
        output_format = os.path.splitext(output_path)[1].lower().lstrip('.')

        if color_mode == "grayscale":
            if img.mode not in ("L",):
                img = img.convert("L")
        elif color_mode == "rgb":
            if img.mode not in ("RGB",):
                img = img.convert("RGB")
        elif color_mode == "rgba":
            if img.mode not in ("RGBA",):
                img = img.convert("RGBA")
        # "original": keep as-is

        # Ensure compatible mode for output format
        if output_format in ("jpg", "jpeg"):
            if img.mode in ("RGBA", "P", "L"):
                img = img.convert("RGB")
        elif output_format == "bmp":
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

        if progress_callback:
            progress_callback(75.0, _("保存中"))

        # --- Quality ---
        quality = settings.get("quality", "high")
        quality_map = {"low": 60, "medium": 80, "high": 95, "lossless": 100}
        save_kwargs = {}
        if output_format in ("jpg", "jpeg"):
            save_kwargs["quality"] = quality_map.get(quality, 95)
            save_kwargs["optimize"] = True
        elif output_format == "png":
            if quality == "lossless":
                save_kwargs["compress_level"] = 0
            else:
                save_kwargs["compress_level"] = {"low": 9, "medium": 6, "high": 3}.get(quality, 3)
        elif output_format == "webp":
            save_kwargs["quality"] = quality_map.get(quality, 95)

        # PDF output: save all pages (single image → single PDF page)
        if output_format == "pdf":
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(output_path, "PDF", resolution=100.0)
        else:
            img.save(output_path, **save_kwargs)

        if progress_callback:
            progress_callback(100.0, _("完成"))

        return True, None

    except Exception as ex:
        return False, str(ex)


def convert_heic_to_jpg(input_path, output_path, settings=None, progress_callback=None):
    """Convert HEIC to JPG. Requires pillow-heif."""
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        return False, "pillow-heif not installed. Run: pip install pillow-heif"

    try:
        img = Image.open(input_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(output_path, "JPEG", quality=95)
        if progress_callback:
            progress_callback(100.0, _("完成"))
        return True, None
    except Exception as ex:
        return False, str(ex)
