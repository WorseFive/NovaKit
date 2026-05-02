import os
from PyPDF2 import PdfReader, PdfWriter
from .config import parse_page_range


def crop_pdf(input_path, output_path, margins=(0, 0, 0, 0), pages=None):
    """裁剪 PDF 页面。

    Args:
        input_path: 输入 PDF 路径
        output_path: 输出 PDF 路径
        margins: (top, bottom, left, right) 边距，单位 points
        pages: 目标页码集合 (1-based)，None 表示所有页
    """
    mt, mb, ml, mr = margins
    reader = PdfReader(input_path)
    total = len(reader.pages)
    pages_set = pages or set(range(1, total + 1))

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if (i + 1) in pages_set:
            old_box = page.mediabox
            new_left = float(old_box.left) + ml
            new_bottom = float(old_box.bottom) + mb
            new_right = float(old_box.right) - mr
            new_top = float(old_box.top) - mt
            if new_left >= new_right or new_bottom >= new_top:
                raise ValueError(f"裁剪边距过大，页面 {i + 1} 会变为空")
            page.mediabox.left = new_left
            page.mediabox.bottom = new_bottom
            page.mediabox.right = new_right
            page.mediabox.top = new_top
        writer.add_page(page)
    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out, len(pages_set)


def crop_pdfs_batch(file_list, output_dir, margins=(0, 0, 0, 0), pages=None):
    """批量裁剪多个 PDF 文件。"""
    results = []
    for fpath in file_list:
        base = os.path.splitext(os.path.basename(fpath))[0]
        out = os.path.join(output_dir, f"{base}_Cropped.pdf")
        output, count = crop_pdf(fpath, out, margins, pages)
        results.append((fpath, output, count))
    return results
