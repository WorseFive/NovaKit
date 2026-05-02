import os
from PyPDF2 import PdfReader, PdfWriter


def merge_pdfs(file_list, output_path):
    """合并多个 PDF 文件为一个。输出文件自动确保 .pdf 后缀。"""
    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    writer = PdfWriter()
    for f in file_list:
        reader = PdfReader(f)
        for page in reader.pages:
            writer.add_page(page)
    with open(out, "wb") as f:
        writer.write(f)
    return out
