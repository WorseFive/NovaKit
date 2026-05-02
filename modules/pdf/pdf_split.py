import os
from PyPDF2 import PdfReader, PdfWriter
from .config import parse_page_range


def split_all_pages(pdf_path, output_dir):
    """将 PDF 拆分为单页文件，保存到 output_dir。"""
    reader = PdfReader(pdf_path)
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    d = os.path.join(output_dir, base + "_Split")
    os.makedirs(d, exist_ok=True)
    for i, page in enumerate(reader.pages):
        w = PdfWriter()
        w.add_page(page)
        with open(os.path.join(d, f"page_{i + 1}.pdf"), "wb") as f:
            w.write(f)
    return d, len(reader.pages)


def extract_pages_range(pdf_path, output_path, raw_pages):
    """提取指定页码范围到单个 PDF 文件。返回提取的页数。raw_pages 为 None 表示全部分页。"""
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    pages = parse_page_range(raw_pages, total)
    if pages is None:
        raise ValueError(f"无效的页码范围: {raw_pages}")

    w = PdfWriter()
    for i in sorted(pages):
        if 1 <= i <= total:
            w.add_page(reader.pages[i - 1])
    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        w.write(f)
    return out, len(pages)


# ===================== PDF 页面导出为 PNG =====================

def _get_pdf_renderer():
    """尝试加载可用的 PDF 渲染后端。返回后端名字符串或抛出 RuntimeError。"""
    backends = []

    try:
        import pypdfium2
        backends.append("pypdfium2")
    except ImportError:
        pass

    try:
        import fitz
        backends.append("fitz")
    except ImportError:
        pass

    try:
        from pdf2image import convert_from_path
        backends.append("pdf2image")
    except ImportError:
        pass

    if not backends:
        raise RuntimeError(
            "未找到 PDF 渲染引擎。请安装以下任一库：\n"
            "  pip install pypdfium2\n"
            "  pip install PyMuPDF\n"
            "  pip install pdf2image (需要 poppler)"
        )
    return backends[0]


def extract_pages_to_images(pdf_path, output_dir, raw_pages=None, scale=2.0):
    """将 PDF 页面导出为 PNG 图片。自动检测可用的渲染后端。

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录（会自动创建子文件夹）
        raw_pages: 页码范围字符串，None 表示所有页
        scale: 渲染缩放倍数 (1.0=72DPI, 2.0≈144DPI)

    Returns:
        (output_folder, page_count) 元组
    """
    backend = _get_pdf_renderer()

    if backend == "pypdfium2":
        return _render_with_pypdfium2(pdf_path, output_dir, raw_pages, scale)
    elif backend == "fitz":
        return _render_with_fitz(pdf_path, output_dir, raw_pages, scale)
    elif backend == "pdf2image":
        return _render_with_pdf2image(pdf_path, output_dir, raw_pages, scale)


def _resolve_pages(pdf_path, raw_pages):
    """解析页码范围。后端无关。返回 (total, pages_set)。"""
    from PyPDF2 import PdfReader
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    if raw_pages:
        pages = parse_page_range(raw_pages, total)
        if pages is None:
            raise ValueError(f"无效的页码范围: {raw_pages}")
    else:
        pages = set(range(1, total + 1))
    return total, pages


def _render_with_pypdfium2(pdf_path, output_dir, raw_pages, scale):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_path)
    total = len(doc)
    _, pages = _resolve_pages(pdf_path, raw_pages)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    d = os.path.join(output_dir, base + "_Images")
    os.makedirs(d, exist_ok=True)

    count = 0
    for page_num in sorted(pages):
        idx = page_num - 1
        if 0 <= idx < total:
            bitmap = doc[idx].render(scale=scale)
            pil_img = bitmap.to_pil()
            pil_img.save(os.path.join(d, f"page_{page_num}.png"), "PNG")
            count += 1
    doc.close()
    return d, count


def _render_with_fitz(pdf_path, output_dir, raw_pages, scale):
    import fitz

    doc = fitz.open(pdf_path)
    _, pages = _resolve_pages(pdf_path, raw_pages)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    d = os.path.join(output_dir, base + "_Images")
    os.makedirs(d, exist_ok=True)

    mat = fitz.Matrix(scale, scale)
    count = 0
    for page_num in sorted(pages):
        idx = page_num - 1
        if 0 <= idx < len(doc):
            pix = doc[idx].get_pixmap(matrix=mat)
            pix.save(os.path.join(d, f"page_{page_num}.png"))
            count += 1
    doc.close()
    return d, count


def _render_with_pdf2image(pdf_path, output_dir, raw_pages, scale):
    from pdf2image import convert_from_path

    _, pages = _resolve_pages(pdf_path, raw_pages)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    d = os.path.join(output_dir, base + "_Images")
    os.makedirs(d, exist_ok=True)

    dpi = int(72 * scale)
    first = min(pages) - 1 if pages else 0
    last = max(pages) - 1 if pages else 0

    images = convert_from_path(pdf_path, dpi=dpi, first_page=first + 1, last_page=last + 1)
    count = 0
    for i, img in enumerate(images):
        page_num = sorted(pages)[i]
        img.save(os.path.join(d, f"page_{page_num}.png"), "PNG")
        count += 1
    return d, count
