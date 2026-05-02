import zipfile
import io
from PIL import Image
from .config import VALID_EXT


def extract_images(zip_path, password=None):
    """从 ZIP 文件中提取图片，返回 PIL Image 列表。密码错误时抛出 RuntimeError。"""
    pwd = password.encode('utf-8') if password else None
    images = []
    with zipfile.ZipFile(zip_path, 'r') as z:
        for name in sorted(z.namelist()):
            if name.lower().endswith(VALID_EXT):
                with z.open(name, pwd=pwd) as f:
                    img = Image.open(io.BytesIO(f.read()))
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    images.append(img)
    return images


def convert_zip_to_pdf(zip_path, output_path, password=None):
    """将 ZIP 中的图片转换为 PDF，返回 (image_count, pdf_path)。无图片返回 (-1, None)。"""
    images = extract_images(zip_path, password)
    if not images:
        return -1, None
    images[0].save(output_path, "PDF", resolution=100.0, save_all=True, append_images=images[1:])
    return len(images), output_path
