import os
import json
import struct

# ===================== 常量 =====================
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_FILE = os.path.join(_ROOT, "config.json")
VALID_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp', '.gif', '.jfif')

WATERMARK_PRESETS_FILE = os.path.join(_ROOT, "watermark_presets.json")

FONT_DIR = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")

# ===================== 常用字体 (显示名, OS字体族名, 文件名关键词) =====================
POPULAR_FONT_SPECS = [
    ("宋体",       "SimSun",             "simsun"),
    ("黑体",       "SimHei",             "simhei"),
    ("楷体",       "KaiTi",              "simkai"),
    ("仿宋",       "FangSong",           "simfang"),
    ("微软雅黑",   "Microsoft YaHei",    "msyh"),
    ("华文楷体",   "STKaiti",            "stkaiti"),
    ("华文宋体",   "STSong",             "stsong"),
    ("华文仿宋",   "STFangsong",         "stfangsong"),
    ("华文细黑",   "STXihei",            "stxihei"),
    ("华文隶书",   "STLiti",             "stliti"),
    ("幼圆",       "YouYuan",            "youyuan"),
    ("新宋体",     "NSimSun",            "nsimsun"),
    ("Arial",      "Arial",              "arial"),
    ("Times New Roman", "Times New Roman", "times"),
    ("Calibri",    "Calibri",            "calibri"),
    ("Cambria",    "Cambria",            "cambria"),
    ("Courier New", "Courier New",       "cour"),
    ("Georgia",    "Georgia",            "georgia"),
    ("Verdana",    "Verdana",            "verdana"),
    ("Segoe UI",   "Segoe UI",           "segoeui"),
    ("Consolas",   "Consolas",           "consola"),
    ("Comic Sans MS", "Comic Sans MS",   "comic"),
    ("Impact",     "Impact",             "impact"),
    ("Tahoma",     "Tahoma",             "tahoma"),
    ("Trebuchet MS", "Trebuchet MS",     "trebuc"),
    ("Lucida Console", "Lucida Console", "lucon"),
    ("Palatino Linotype", "Palatino Linotype", "pala"),
    ("Book Antiqua", "Book Antiqua",     "bookantiqua"),
]


def _parse_ttf_family(font_path):
    """解析 TTF/OTF/TTC 文件获取字体系列名。"""
    try:
        with open(font_path, 'rb') as f:
            header = f.read(4)
            # TTC 集合
            if header == b'ttcf':
                f.seek(8)
                num_fonts = struct.unpack('>I', f.read(4))[0]
                if num_fonts == 0:
                    return None
                f.seek(struct.unpack('>I', f.read(4))[0])
            else:
                f.seek(0)

            sf_version = f.read(4)
            num_tables = struct.unpack('>H', f.read(2))[0]
            f.read(6)

            name_off = None
            for _ in range(num_tables):
                tag = f.read(4)
                f.read(4)
                off = struct.unpack('>I', f.read(4))[0]
                length = struct.unpack('>I', f.read(4))[0]
                if tag == b'name':
                    name_off = off
                    break

            if name_off is None:
                return None

            f.seek(name_off)
            nd = f.read(1024 * 64)  # name table is small
            fmt = struct.unpack('>H', nd[0:2])[0]
            count = struct.unpack('>H', nd[2:4])[0]
            str_off = struct.unpack('>H', nd[4:6])[0]

            best = None
            for i in range(count):
                base = 6 + i * 12
                if base + 12 > len(nd):
                    break
                pid = struct.unpack('>H', nd[base:base+2])[0]
                eid = struct.unpack('>H', nd[base+2:base+4])[0]
                nid = struct.unpack('>H', nd[base+6:base+8])[0]
                ln = struct.unpack('>H', nd[base+8:base+10])[0]
                off = struct.unpack('>H', nd[base+10:base+12])[0]
                if nid == 1:
                    s = str_off + off
                    data = nd[s:s+ln]
                    if pid == 3 and eid == 1:  # Windows UTF-16BE
                        try:
                            return data.decode('utf-16-be', errors='replace').strip('\x00')
                        except Exception:
                            pass
                    elif best is None and pid == 1 and eid == 0:  # Mac Roman
                        try:
                            best = data.decode('mac_roman', errors='replace')
                        except Exception:
                            pass
            return best
    except Exception:
        return None


def get_font_family(font_path):
    """获取字体文件的 OS 字体系列名。先查内置映射，再解析文件，最后回退到文件名。"""
    fname_lower = os.path.basename(font_path).lower()
    # 查内置映射
    for display, family, keyword in POPULAR_FONT_SPECS:
        if keyword in fname_lower:
            return family
    # 尝试解析
    parsed = _parse_ttf_family(font_path)
    if parsed:
        return parsed
    # 回退：取无扩展名的文件名
    return os.path.splitext(os.path.basename(font_path))[0]


def get_system_fonts():
    """扫描系统字体目录，返回 (显示名, 路径, OS族名) 列表。常用字体排在前面。"""
    popular = []   # (display, path, family)
    others = []    # (display, path, family)
    seen_paths = set()

    if not os.path.isdir(FONT_DIR):
        return popular + others

    all_files = {f.lower(): f for f in os.listdir(FONT_DIR)
                 if f.lower().endswith(('.ttf', '.ttc', '.otf'))}

    # 先匹配常用字体
    for display, family, keyword in POPULAR_FONT_SPECS:
        for fname_lower, fname_actual in all_files.items():
            if keyword in fname_lower and fname_lower not in seen_paths:
                path = os.path.join(FONT_DIR, fname_actual)
                seen_paths.add(fname_lower)
                popular.append((display, path, family))
                break

    # 其余字体
    for fname_lower, fname_actual in sorted(all_files.items()):
        if fname_lower in seen_paths:
            continue
        seen_paths.add(fname_lower)
        path = os.path.join(FONT_DIR, fname_actual)
        family = get_font_family(path)
        display = os.path.splitext(fname_actual)[0]
        others.append((display, path, family))

    # others 按显示名排序
    others.sort(key=lambda x: x[0].lower())
    return popular + others


# ===================== 颜色 =====================

COLOR_MAP = {
    "Black": (0, 0, 0),
    "DarkRed": (139, 0, 0),
    "DarkBlue": (0, 0, 139),
    "DarkGreen": (0, 100, 0),
    "Grey": (128, 128, 128),
    "Red": (255, 0, 0),
    "Blue": (0, 0, 255),
    "Green": (0, 128, 0),
}

# 调色板：(颜色名, hex, rgb)
COLOR_PALETTE = [
    ("黑色",   "#000000", (0, 0, 0)),
    ("深灰",   "#404040", (64, 64, 64)),
    ("灰色",   "#808080", (128, 128, 128)),
    ("银色",   "#C0C0C0", (192, 192, 192)),
    ("白色",   "#FFFFFF", (255, 255, 255)),

    ("深红",   "#800000", (128, 0, 0)),
    ("红色",   "#FF0000", (255, 0, 0)),
    ("橙红",   "#FF4500", (255, 69, 0)),
    ("橙色",   "#FFA500", (255, 165, 0)),
    ("金色",   "#FFD700", (255, 215, 0)),
    ("黄色",   "#FFFF00", (255, 255, 0)),
    ("棕色",   "#8B4513", (139, 69, 19)),
    ("褐色",   "#A0522D", (160, 82, 45)),
    ("珊瑚",   "#FF7F50", (255, 127, 80)),
    ("粉色",   "#FFC0CB", (255, 192, 203)),

    ("深绿",   "#006400", (0, 100, 0)),
    ("绿色",   "#008000", (0, 128, 0)),
    ("亮绿",   "#32CD32", (50, 205, 50)),
    ("春绿",   "#00FF7F", (0, 255, 127)),
    ("草绿",   "#7CFC00", (124, 252, 0)),
    ("橄榄",   "#808000", (128, 128, 0)),
    ("深青",   "#008B8B", (0, 139, 139)),
    ("青色",   "#008080", (0, 128, 128)),
    ("蓝绿",   "#00CED1", (0, 206, 209)),
    ("浅绿",   "#98FB98", (152, 251, 152)),

    ("深蓝",   "#000080", (0, 0, 128)),
    ("蓝色",   "#0000FF", (0, 0, 255)),
    ("宝蓝",   "#4169E1", (65, 105, 225)),
    ("天蓝",   "#87CEEB", (135, 206, 235)),
    ("钢蓝",   "#4682B4", (70, 130, 180)),
    ("靛蓝",   "#4B0082", (75, 0, 130)),
    ("皇室蓝", "#1E3A8A", (30, 58, 138)),
    ("午夜蓝", "#191970", (25, 25, 112)),
    ("道奇蓝", "#1E90FF", (30, 144, 255)),
    ("深天蓝", "#00BFFF", (0, 191, 255)),

    ("深紫",   "#800080", (128, 0, 128)),
    ("紫色",   "#8B00FF", (139, 0, 255)),
    ("洋红",   "#FF00FF", (255, 0, 255)),
    ("深洋红", "#C71585", (199, 21, 133)),
    ("玫红",   "#FF1493", (255, 20, 147)),
    ("紫罗兰", "#EE82EE", (238, 130, 238)),
    ("兰花紫", "#DA70D6", (218, 112, 214)),
    ("梅红",   "#DDA0DD", (221, 160, 221)),
    ("淡紫",   "#E6E6FA", (230, 230, 250)),
    ("蓟色",   "#D8BFD8", (216, 191, 216)),

    ("米色",   "#F5F5DC", (245, 245, 220)),
    ("象牙",   "#FFFFF0", (255, 255, 240)),
    ("小麦",   "#F5DEB3", (245, 222, 179)),
    ("杏仁白", "#FFEBCD", (255, 235, 205)),
    ("烟白",   "#F5F5F5", (245, 245, 245)),
]


def parse_color(value):
    """将颜色值解析为 (r, g, b) 元组。支持: 元组/列表、hex字符串、COLOR_MAP名称、调色板名称。"""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(c) for c in value)
    if isinstance(value, str):
        if value in COLOR_MAP:
            return COLOR_MAP[value]
        if value.startswith('#'):
            h = value.lstrip('#')
            try:
                return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            except Exception:
                pass
        for name, hex_, rgb in COLOR_PALETTE:
            if name == value or hex_.upper() == value.upper():
                return rgb
    return (0, 0, 0)


# ===================== 配置读写 =====================
def get_desktop_path():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                saved_dir = config.get("output_dir", "")
                if os.path.isdir(saved_dir):
                    return saved_dir
        except Exception:
            pass
    return get_desktop_path()


def save_config(output_dir):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"output_dir": output_dir}, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


# ===================== 字体 =====================
def get_font(size, font_path=None):
    """加载指定路径的字体，失败则回退到默认字体。"""
    from PIL import ImageFont
    if font_path and os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ===================== 预设管理 =====================
def load_presets():
    if os.path.exists(WATERMARK_PRESETS_FILE):
        try:
            with open(WATERMARK_PRESETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_presets(presets):
    try:
        with open(WATERMARK_PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


# ===================== 通用工具 =====================
def parse_page_range(raw, total):
    """解析页码范围字符串，返回 set。失败返回 None。"""
    pages = set()
    if not raw.strip():
        return None
    for part in raw.split(','):
        part = part.strip()
        if '-' in part:
            try:
                s, e = map(int, part.split('-'))
                pages.update(range(s, e + 1))
            except ValueError:
                return None
        elif part.isdigit():
            pages.add(int(part))
        else:
            return None
    invalid = [p for p in pages if p < 1 or p > total]
    if invalid:
        return None
    return pages
