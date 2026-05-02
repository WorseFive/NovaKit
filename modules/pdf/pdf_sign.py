import io
import os
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter


def sign_pdf(pdf_path, sig_img_path, output_path, position="bottom-right", scale=0.3, target_pages=None):
    """为 PDF 添加签名图片。

    Args:
        pdf_path: 输入 PDF 路径
        sig_img_path: 签名图片路径
        output_path: 输出 PDF 路径
        position: 签名位置 (bottom-right, bottom-left, top-right, top-left, center)
        scale: 缩放比例 (0.01-1.0)
        target_pages: 目标页码集合 (1-based)，None 表示所有页
    """
    reader = PdfReader(pdf_path)
    sig_img = Image.open(sig_img_path).convert("RGBA")
    total_pages = len(reader.pages)
    pages_set = target_pages or set(range(1, total_pages + 1))

    sign_w, sign_h = sig_img.size
    new_w, new_h = int(sign_w * scale), int(sign_h * scale)
    if new_w > 0 and new_h > 0:
        sig_img = sig_img.resize((new_w, new_h), Image.LANCZOS)
    else:
        sig_img = sig_img.resize((1, 1), Image.LANCZOS)

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        page_num = i + 1
        if page_num in pages_set:
            mb = page.mediabox
            pw, ph = float(mb.width), float(mb.height)

            stamp_img = Image.new("RGBA", (int(pw), int(ph)), (255, 255, 255, 0))
            margin = 40
            sw, sh = sig_img.size
            pos_map = {
                "bottom-right": (int(pw) - sw - margin, int(ph) - sh - margin),
                "bottom-left": (margin, int(ph) - sh - margin),
                "top-right": (int(pw) - sw - margin, margin),
                "top-left": (margin, margin),
                "center": ((int(pw) - sw) // 2, (int(ph) - sh) // 2),
            }
            px, py = pos_map.get(position, pos_map["bottom-right"])
            stamp_img.paste(sig_img, (px, py), sig_img if sig_img.mode == "RGBA" else None)

            stamp_rgb = stamp_img.convert("RGB")
            stamp_bytes = io.BytesIO()
            stamp_rgb.save(stamp_bytes, format="PDF", resolution=100.0)
            stamp_bytes.seek(0)
            stamp_reader = PdfReader(stamp_bytes)
            page.merge_page(stamp_reader.pages[0])

        writer.add_page(page)

    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out, len(pages_set)
