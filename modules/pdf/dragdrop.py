"""
Windows 原生文件拖放支持。
通过子类化窗口过程拦截 WM_DROPFILES 消息，实现将文件直接拖入 Flet 窗口。
"""
import ctypes
from ctypes import wintypes
import time
import queue

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4

_drop_queue = queue.Queue()
_original_wndproc = None
_wndproc_cb = None
_hwnd = None
_enabled = False

WNDPROC_TYPE = ctypes.WINFUNCTYPE(
    ctypes.c_longlong,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


def _process_drop(hdrop):
    count = shell32.DragQueryFileW(hdrop, -1, None, 0)
    files = []
    for i in range(count):
        size = shell32.DragQueryFileW(hdrop, i, None, 0) + 1
        buf = ctypes.create_unicode_buffer(size)
        shell32.DragQueryFileW(hdrop, i, buf, size)
        files.append(buf.value)
    shell32.DragFinish(hdrop)
    if files:
        _drop_queue.put(files)


def _new_wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_DROPFILES:
        _process_drop(wparam)
        return 0
    return user32.CallWindowProcW(_original_wndproc, hwnd, msg, wparam, lparam)


def _find_window(title, retries=30, delay=0.1):
    """通过窗口标题查找 Flet 窗口，带重试机制。"""
    for i in range(retries):
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            return hwnd
        # 也尝试部分匹配（Flet 有时会在标题后附加内容）
        hwnd = _find_window_contains(title)
        if hwnd:
            return hwnd
        time.sleep(delay)
    return None


def _find_window_contains(substring):
    """枚举所有顶层窗口，查找标题包含 substring 的窗口。"""
    result = []

    def enum_callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        if substring.lower() in buf.value.lower():
            result.append(hwnd)
            return False  # 停止枚举
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    return result[0] if result else None


def enable(window_title):
    """启用拖放支持。会自动重试查找窗口。返回 (是否成功, 错误信息)"""
    global _hwnd, _original_wndproc, _wndproc_cb, _enabled

    if _enabled:
        return True, "已启用"

    _hwnd = _find_window(window_title, retries=30, delay=0.1)
    if not _hwnd:
        return False, f"未找到窗口: \"{window_title}\""

    shell32.DragAcceptFiles(_hwnd, True)

    # 枚举所有子窗口也启用拖放
    def enum_child(hwnd, _):
        shell32.DragAcceptFiles(hwnd, True)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(_hwnd, WNDENUMPROC(enum_child), 0)

    _wndproc_cb = WNDPROC_TYPE(_new_wndproc)
    _original_wndproc = user32.SetWindowLongPtrW(
        _hwnd, GWLP_WNDPROC, _wndproc_cb
    )
    _enabled = True
    return True, "拖放已启用"


def disable():
    """恢复原始窗口过程。"""
    global _hwnd, _original_wndproc, _enabled
    if _hwnd and _original_wndproc:
        user32.SetWindowLongPtrW(_hwnd, GWLP_WNDPROC, _original_wndproc)
    _hwnd = None
    _original_wndproc = None
    _enabled = False


def is_enabled():
    return _enabled


def get_dropped_files(timeout=0):
    """非阻塞获取拖放的文件列表。无文件时返回 None。"""
    try:
        return _drop_queue.get(timeout=timeout)
    except queue.Empty:
        return None
