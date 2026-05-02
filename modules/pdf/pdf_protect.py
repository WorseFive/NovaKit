import os
from PyPDF2 import PdfReader, PdfWriter


def encrypt_pdf(input_path, output_path, user_password, owner_password=None):
    """加密 PDF 文件。"""
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password, owner_password)
    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out


def decrypt_pdf(input_path, output_path, password=None):
    """解密 PDF 文件。返回解密后的路径，密码错误返回 None。"""
    reader = PdfReader(input_path)
    if reader.is_encrypted:
        if not password:
            raise ValueError("需要密码")
        result = reader.decrypt(password)
        if result == 0:
            return None
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    out = output_path if output_path.endswith(".pdf") else output_path + ".pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out


def is_encrypted(input_path):
    """检查 PDF 是否已加密。返回 (is_encrypted_bool, reader)。"""
    reader = PdfReader(input_path)
    return reader.is_encrypted, reader
