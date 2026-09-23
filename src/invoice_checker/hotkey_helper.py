"""Hidden mode of the main application that receives Explorer shortcut presses."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from .hotkey import HOTKEY_ID, parse_hotkey


WM_HOTKEY = 0x0312
ERROR_ALREADY_EXISTS = 183
CF_HDROP = 15
DRAG_QUERY_ALL_FILES = 0xFFFFFFFF


def existing_pdf_paths(paths: Iterable[str]) -> list[str]:
    return [str(path) for path in paths if str(path).lower().endswith(".pdf") and Path(path).is_file()]


def pdf_paths_from_shell_output(output: str) -> list[str]:
    if not output.strip():
        return []
    values = json.loads(output)
    if isinstance(values, str):
        values = [values]
    return existing_pdf_paths(str(path) for path in values)


def clipboard_pdf_paths() -> list[str]:
    """Read PDF paths copied from Explorer with Ctrl+C."""
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
    user32.OpenClipboard.restype = ctypes.wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = ctypes.wintypes.BOOL
    user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.wintypes.HANDLE
    user32.CloseClipboard.restype = ctypes.wintypes.BOOL
    shell32.DragQueryFileW.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.UINT,
        ctypes.wintypes.LPWSTR,
        ctypes.wintypes.UINT,
    ]
    shell32.DragQueryFileW.restype = ctypes.wintypes.UINT
    if not user32.OpenClipboard(None):
        return []
    try:
        if not user32.IsClipboardFormatAvailable(CF_HDROP):
            return []
        handle = user32.GetClipboardData(CF_HDROP)
        if not handle:
            return []
        count = shell32.DragQueryFileW(handle, DRAG_QUERY_ALL_FILES, None, 0)
        paths: list[str] = []
        for index in range(count):
            length = shell32.DragQueryFileW(handle, index, None, 0)
            if length <= 0:
                continue
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(handle, index, buffer, length + 1)
            paths.append(buffer.value)
        return existing_pdf_paths(paths)
    finally:
        user32.CloseClipboard()


def selected_pdf_paths() -> list[str]:
    """Read the foreground Explorer tab first, with a short retry for selection timing."""
    script = (
        "Add-Type @'\nusing System; using System.Runtime.InteropServices; "
        "public static class HotkeyWindow { [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); }\n'@;"
        "$foreground=[HotkeyWindow]::GetForegroundWindow().ToInt64();"
        "$shell=New-Object -ComObject Shell.Application;"
        "$windows=@($shell.Windows());"
        "$active=@($windows|Where-Object{[int64]$_.HWND -eq $foreground});"
        "$scope=if($active.Count){$active}else{$windows};"
        "$items=@($scope|ForEach-Object{$_.Document.SelectedItems()}|ForEach-Object{$_.Path});"
        "$items|ConvertTo-Json -Compress"
    )
    for _ in range(4):
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if not result.returncode:
            paths = pdf_paths_from_shell_output(result.stdout)
            if paths:
                return paths
        time.sleep(0.15)
    return []


def selected_or_clipboard_pdf_paths(
    selected_reader: Callable[[], list[str]] | None = None,
    clipboard_reader: Callable[[], list[str]] | None = None,
) -> list[str]:
    selected = (selected_reader or selected_pdf_paths)()
    if selected:
        return selected
    return (clipboard_reader or clipboard_pdf_paths)()


def database_path() -> Path:
    return Path.home() / "AppData" / "Local" / "InvoiceChecker" / "invoices.sqlite3"


def append_hotkey_log(message: str, log_path: Path | None = None) -> None:
    """Keep a short local trace so an otherwise invisible helper is diagnosable."""
    target = log_path or database_path().with_name("hotkey.log")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as log:
        log.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")


def set_hotkey_status(value: str) -> None:
    try:
        db = database_path()
        db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO settings(key,value) VALUES ('hotkey_status', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (value,)
            )
    except sqlite3.Error:
        pass


def hotkey_ready_message(spec) -> str:  # type: ignore[no-untyped-def]
    return f"已启用 {spec.display}；推荐在资源管理器多选 PDF 后按 Ctrl+C，再按 {spec.display} 从剪贴板导入。"


def configured_hotkey():  # type: ignore[no-untyped-def]
    value = "Alt+R"
    try:
        with sqlite3.connect(database_path()) as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='hotkey'").fetchone()
            if row:
                value = row[0]
    except sqlite3.Error:
        pass
    try:
        return parse_hotkey(value)
    except ValueError:
        return parse_hotkey("Alt+R")


def launch_checker(paths: list[str]) -> None:
    if paths:
        append_hotkey_log("启动导入：" + " | ".join(paths))
        subprocess.Popen([sys.executable, *paths], close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        append_hotkey_log("未找到资源管理器中选定的 PDF。")


def hotkey_pdf_paths_with_source() -> tuple[list[str], str]:
    selected = selected_pdf_paths()
    if selected:
        return selected, "资源管理器选中项"
    clipboard = clipboard_pdf_paths()
    if clipboard:
        return clipboard, "剪贴板文件列表"
    return [], "无"


def main() -> int:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Local\\InvoiceCheckerHotkey")
    if not mutex or kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        append_hotkey_log("助手已在运行，当前进程退出。")
        set_hotkey_status("后台快捷键助手已在运行。")
        return 0
    spec = configured_hotkey()
    if not user32.RegisterHotKey(None, HOTKEY_ID, spec.modifiers, spec.virtual_key):
        append_hotkey_log(f"快捷键注册失败：{spec.display}")
        set_hotkey_status(f"快捷键冲突：{spec.display} 已被其他程序占用。")
        kernel32.CloseHandle(mutex)
        return 1
    set_hotkey_status(hotkey_ready_message(spec))
    append_hotkey_log(f"已启用 {spec.display}")
    message = ctypes.wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0):
            if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                paths, source = hotkey_pdf_paths_with_source()
                append_hotkey_log(f"收到快捷键；来源：{source}；文件：" + (" | ".join(paths) if paths else "无"))
                launch_checker(paths)
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        kernel32.CloseHandle(mutex)
    return 0
