"""Shared parsing and probing helpers for the Explorer import shortcut."""
from __future__ import annotations

from dataclasses import dataclass
import re


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
HOTKEY_ID = 101


@dataclass(frozen=True)
class HotkeySpec:
    modifiers: int
    virtual_key: int
    display: str


def parse_hotkey(value: str) -> HotkeySpec:
    """Turn a human-entered combination into the Win32 registration values."""
    raw_parts = [part.strip().upper() for part in value.split("+") if part.strip()]
    aliases = {"CONTROL": "CTRL", "CTL": "CTRL", "OPTION": "ALT"}
    parts = [aliases.get(part, part) for part in raw_parts]
    if len(parts) < 2 or len(parts) != len(set(parts)):
        raise ValueError("快捷键格式应为 Alt+R、Ctrl+Alt+R 或 Alt+F8。")

    modifiers = 0
    display_modifiers: list[str] = []
    for name, flag, display in (("CTRL", MOD_CONTROL, "Ctrl"), ("ALT", MOD_ALT, "Alt"), ("SHIFT", MOD_SHIFT, "Shift")):
        if name in parts:
            modifiers |= flag
            display_modifiers.append(display)
    keys = [part for part in parts if part not in {"CTRL", "ALT", "SHIFT"}]
    if not modifiers or len(keys) != 1:
        raise ValueError("快捷键必须包含 Ctrl、Alt 或 Shift，并且只指定一个主按键。")

    key = keys[0]
    if re.fullmatch(r"[A-Z0-9]", key):
        virtual_key = ord(key)
    elif re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        virtual_key = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("快捷键主按键仅支持字母、数字或 F1 至 F24。")
    return HotkeySpec(modifiers, virtual_key, "+".join([*display_modifiers, key]))


def is_hotkey_available(spec: HotkeySpec) -> bool:
    """Probe Windows without retaining the shortcut registration."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, HOTKEY_ID, spec.modifiers, spec.virtual_key):
            return False
        user32.UnregisterHotKey(None, HOTKEY_ID)
        return True
    except (AttributeError, OSError):
        # Non-Windows test environments cannot reserve a Windows shortcut.
        return True
