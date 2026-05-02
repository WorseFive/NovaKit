import os
from PyPDF2 import PdfReader, PdfWriter
from .config import parse_page_range


def rotate_pdf(input_path, output_path, angle=90, pages=None):
    """旋转 PDF 页面。

    Args:
        input_path: 输入 PDF 路径
        output_path: 输出 PDF 路径
        angle: 旋转角度 (90, -90, 180)
        pages: 目标页码集合 (1-based)，None 表示所有页
    """
    reader = PdfReader(input_path)
    total = len(reader.pages)
    pages_set = pages or set(range(1, total + 1))

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if (i + 1) in pages_set:
            page.rotate(angle)
        writer.add_page(page)
    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out, len(pages_set)


def rotate_pdfs_batch(file_list, output_dir, angle=90, pages=None):
    """批量旋转多个 PDF 文件。返回处理结果列表 [(input_path, output_path, page_count)]。"""
    results = []
    for fpath in file_list:
        base = os.path.splitext(os.path.basename(fpath))[0]
        angle_label = {90: "90CW", -90: "90CCW", 180: "180"}.get(angle, str(angle))
        out = os.path.join(output_dir, f"{base}_Rotated_{angle_label}.pdf")
        output, count = rotate_pdf(fpath, out, angle, pages)
        results.append((fpath, output, count))
    return results
