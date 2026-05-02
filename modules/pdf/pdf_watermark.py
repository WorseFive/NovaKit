import io
import math
import zlib
import os
from PIL import Image, ImageDraw
from PyPDF2 import PdfReader, PdfWriter
from .config import (
    parse_color, get_font, parse_page_range,
)


def rgba_to_pdf_bytes(rgba_img):
    """将 RGBA PIL Image 编码为带透明通道的 PDF 字节 (使用 SMask)。"""
    w, h = rgba_img.size
    r, g, b, a = rgba_img.split()
    rgb_data = Image.merge("RGB", (r, g, b)).tobytes("raw", "RGB")
    alpha_data = a.tobytes("raw", "L")
    rgb_compressed = zlib.compress(rgb_data)
    alpha_compressed = zlib.compress(alpha_data)
    content = f"q {w} 0 0 {h} 0 0 cm /Im0 Do Q".encode()
    content_len = len(content)

    obj_order = [1, 2, 3, 4, 5, 6]
    obj_bodies = {
        1: f"<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}]"
           f" /Contents 4 0 R /Resources << /XObject << /Im0 5 0 R >> >> >>",
        4: (f"<< /Length {content_len} >>\nstream\n", content, b"\nendstream"),
        5: (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h}"
            f" /ColorSpace /DeviceRGB /BitsPerComponent 8"
            f" /SMask 6 0 R /Filter /FlateDecode /Length {len(rgb_compressed)} >>\nstream\n",
            rgb_compressed, b"\nendstream"),
        6: (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h}"
            f" /ColorSpace /DeviceGray /BitsPerComponent 8"
            f" /Filter /FlateDecode /Length {len(alpha_compressed)} >>\nstream\n",
            alpha_compressed, b"\nendstream"),
    }

    pdf = b"%PDF-1.4\n"
    xref_offsets = {}
    for num in obj_order:
        xref_offsets[num] = len(pdf)
        body = obj_bodies[num]
        if isinstance(body, tuple):
            pdf += f"{num} 0 obj\n".encode()
            pdf += body[0].encode()
            pdf += body[1]
            pdf += body[2]
            pdf += b"endobj\n"
        else:
            pdf += f"{num} 0 obj\n{body}\nendobj\n".encode()

    xref_start = len(pdf)
    pdf += b"xref\n0 7\n0000000000 65535 f \n"
    for num in obj_order:
        pdf += f"{xref_offsets[num]:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode()
    return pdf


def calc_position(pw, ph, w, h, offset_x=0, offset_y=0, vert="center", horiz="center"):
    """计算水印在页面上的粘贴位置。"""
    if vert == "top":
        py = 0 + offset_y
    elif vert == "bottom":
        py = int(ph - h) - offset_y
    else:
        py = int((ph - h) / 2) + offset_y

    if horiz == "left":
        px = 0 + offset_x
    elif horiz == "right":
        px = int(pw - w) - offset_x
    else:
        px = int((pw - w) / 2) + offset_x
    return (px, py)


def create_watermark_stamp(pw, ph, params):
    """创建水印印章 PIL Image (RGBA)。

    params 字典需要包含:
        type: 'text' 或 'image'
        文字模式: text, font_name, font_size, color, opacity, rotation
        图片模式: img_path, img_scale, opacity, rotation, opacity
        位置: offset_x, offset_y, vert, horiz
    """
    stamp = Image.new("RGBA", (int(pw), int(ph)), (255, 255, 255, 0))
    opacity = params.get("opacity", 100) / 100.0
    rotation = params.get("rotation", 0)

    if params.get("type") == "text":
        text = params.get("text", "")
        if not text:
            return None
        font_size = params.get("font_size", 48)
        font_path = params.get("font_path", None)
        font = get_font(font_size, font_path)
        color_rgb = parse_color(params.get("color", "#000000"))
        color_rgba = color_rgb + (int(255 * opacity),)

        txt_img = Image.new("RGBA", (int(pw), int(ph)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (pw - tw) / 2
        ty = (ph - th) / 2
        draw.text((tx, ty), text, fill=color_rgba, font=font)

        if rotation != 0:
            txt_img = txt_img.rotate(rotation, expand=True, resample=Image.BICUBIC,
                                      center=(pw / 2, ph / 2))
            rw, rh = txt_img.size
            centered = Image.new("RGBA", (int(pw), int(ph)), (255, 255, 255, 0))
            centered.paste(txt_img, (int((pw - rw) / 2), int((ph - rh) / 2)), txt_img)
            txt_img = centered

        offset_x = params.get("offset_x", 0)
        offset_y = params.get("offset_y", 0)
        pos = calc_position(pw, ph, txt_img.size[0], txt_img.size[1],
                           offset_x, offset_y, params.get("vert", "center"), params.get("horiz", "center"))
        stamp.paste(txt_img, pos, txt_img)
    else:
        img_path = params.get("img_path", "")
        if not img_path or not os.path.exists(img_path):
            return None
        wm_img = Image.open(img_path).convert("RGBA")
        scale = params.get("img_scale", 50) / 100.0
        nw, nh = int(wm_img.width * scale), int(wm_img.height * scale)
        if nw > 0 and nh > 0:
            wm_img = wm_img.resize((nw, nh), Image.LANCZOS)

        if opacity < 1.0:
            r, g, b, a = wm_img.split()
            a = a.point(lambda x: int(x * opacity))
            wm_img = Image.merge("RGBA", (r, g, b, a))

        if rotation != 0:
            wm_img = wm_img.rotate(rotation, expand=True, resample=Image.BICUBIC)

        offset_x = params.get("offset_x", 0)
        offset_y = params.get("offset_y", 0)
        pos = calc_position(pw, ph, wm_img.size[0], wm_img.size[1],
                           offset_x, offset_y, params.get("vert", "center"), params.get("horiz", "center"))
        stamp.paste(wm_img, pos, wm_img)

    return stamp


def parse_wm_pages(total, page_mode="all", page_entry=""):
    """根据水印页面设置返回要处理的页码集合。"""
    if page_mode == "all":
        return set(range(1, total + 1))
    elif page_mode == "range":
        return parse_page_range(page_entry, total) or set()
    elif page_mode == "even":
        return {i for i in range(1, total + 1) if i % 2 == 0}
    elif page_mode == "odd":
        return {i for i in range(1, total + 1) if i % 2 == 1}
    return set()


def apply_watermark_to_pdf(input_path, output_path, stamp_params):
    """将水印应用到单个 PDF 文件。

    Args:
        input_path: 输入 PDF 路径
        output_path: 输出 PDF 路径
        stamp_params: 水印参数字典 (传递给 create_watermark_stamp)
    """
    reader = PdfReader(input_path)
    total = len(reader.pages)
    pages = parse_wm_pages(total, stamp_params.get("page_mode", "all"),
                           stamp_params.get("page_entry", ""))
    if not pages:
        raise ValueError("没有匹配的页面")

    behind = stamp_params.get("layer", "front") == "behind"
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        if (i + 1) in pages:
            mb = page.mediabox
            pw, ph = float(mb.width), float(mb.height)
            stamp = create_watermark_stamp(pw, ph, stamp_params)
            if stamp is None:
                writer.add_page(page)
                continue
            stamp_pdf = rgba_to_pdf_bytes(stamp)
            stamp_reader = PdfReader(io.BytesIO(stamp_pdf))
            if behind:
                stamp_reader.pages[0].merge_page(page)
                writer.add_page(stamp_reader.pages[0])
            else:
                page.merge_page(stamp_reader.pages[0])
                writer.add_page(page)
        else:
            writer.add_page(page)

    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out, len(pages)


def preview_watermark(input_path, output_path, stamp_params):
    """生成单页水印预览。"""
    reader = PdfReader(input_path)
    mb = reader.pages[0].mediabox
    pw, ph = float(mb.width), float(mb.height)

    stamp = create_watermark_stamp(pw, ph, stamp_params)
    if stamp is None:
        raise ValueError("水印内容为空")

    stamp_pdf = rgba_to_pdf_bytes(stamp)
    stamp_reader = PdfReader(io.BytesIO(stamp_pdf))
    behind = stamp_params.get("layer", "front") == "behind"

    if behind:
        stamp_reader.pages[0].merge_page(reader.pages[0])
        result_page = stamp_reader.pages[0]
    else:
        reader.pages[0].merge_page(stamp_reader.pages[0])
        result_page = reader.pages[0]

    writer = PdfWriter()
    writer.add_page(result_page)
    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out


def apply_watermark_batch(file_list, output_dir, stamp_params):
    """批量应用水印到多个 PDF 文件。"""
    results = []
    for fpath in file_list:
        base = os.path.splitext(os.path.basename(fpath))[0]
        out = os.path.join(output_dir, f"{base}_Watermarked.pdf")
        output, count = apply_watermark_to_pdf(fpath, out, stamp_params)
        results.append((fpath, output, count))
    return results
