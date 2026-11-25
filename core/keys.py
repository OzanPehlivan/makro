"""Tuş adları, değiştirici tuşlar ve SendInput dizisi üreticileri."""
import ctypes

from .winapi import (
    INJECT_TAG, INPUT, INPUT_KEYBOARD, INPUT_MOUSE, KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, MAPVK_VK_TO_VSC_EX, MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP, MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP,
    MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_WHEEL,
    MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, user32,
)

VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_PAUSE = 0x13

# Fare tuşlarının sanal tuş kodları
MOUSE_VK = {"left": 0x01, "right": 0x02, "middle": 0x04, "x1": 0x05, "x2": 0x06}
VK_MOUSE = {vk: name for name, vk in MOUSE_VK.items()}
TRIGGER_MOUSE_VKS = (0x04, 0x05, 0x06)  # Sol/sağ tık tetik olamaz

MOD_ORDER = ("ctrl", "shift", "alt", "win")
MOD_OF_VK = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "win", 0x5C: "win",
}
VK_OF_MOD = {"ctrl": 0xA2, "shift": 0xA0, "alt": 0xA4, "win": 0x5B}

MOUSE_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, 0),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, 0),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, 0),
    "x1": (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, 1),
    "x2": (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, 2),
}

# GetKeyNameTextW'nin adlandırmadığı veya yanlış adlandırdığı tuşlar
SPECIAL_NAMES = {
    0x01: "Sol tık", 0x02: "Sağ tık", 0x04: "Orta tık", 0x05: "Fare 4", 0x06: "Fare 5",
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "Caps Lock",
    0x1B: "Esc", 0x20: "Boşluk", 0x21: "Page Up", 0x22: "Page Down", 0x23: "End",
    0x24: "Home", 0x25: "Sol ok", 0x26: "Yukarı ok", 0x27: "Sağ ok", 0x28: "Aşağı ok",
    0x2C: "Print Screen", 0x2D: "Insert", 0x2E: "Delete", 0x5B: "Sol Win", 0x5C: "Sağ Win",
    0x5D: "Menü", 0x60: "Num 0", 0x61: "Num 1", 0x62: "Num 2", 0x63: "Num 3", 0x64: "Num 4",
    0x65: "Num 5", 0x66: "Num 6", 0x67: "Num 7", 0x68: "Num 8", 0x69: "Num 9",
    0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -", 0x6E: "Num ,", 0x6F: "Num /",
    0x90: "Num Lock", 0x91: "Scroll Lock", 0xA0: "Sol Shift", 0xA1: "Sağ Shift",
    0xA2: "Sol Ctrl", 0xA3: "Sağ Ctrl", 0xA4: "Sol Alt", 0xA5: "Sağ Alt (AltGr)",
    0xA6: "Tarayıcı geri", 0xA7: "Tarayıcı ileri", 0xAD: "Sesi kapat", 0xAE: "Ses -",
    0xAF: "Ses +", 0xB0: "Sonraki parça", 0xB1: "Önceki parça", 0xB2: "Durdur",
    0xB3: "Oynat/Duraklat", 0x10: "Shift", 0x11: "Ctrl", 0x12: "Alt",
}
_TURKISH_UPPER = {"i": "İ", "ı": "I"}


def key_name(vk):
    if vk in SPECIAL_NAMES:
        return SPECIAL_NAMES[vk]
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    # Harf, rakam ve OEM tuşlarında klavye düzeninin ürettiği karakteri göster
    ch = user32.MapVirtualKeyW(vk, 2) & 0x7FFF  # MAPVK_VK_TO_CHAR (ölü tuş bitini at)
    if ch > 32:
        c = chr(ch)
        return _TURKISH_UPPER.get(c, c.upper())
    sc = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
    if sc:
        lparam = (sc & 0xFF) << 16 | (1 << 24 if sc & 0xFF00 else 0)
        buf = ctypes.create_unicode_buffer(64)
        if user32.GetKeyNameTextW(lparam, buf, 64):
            return buf.value
    return None


def key_table():
    """Arayüz için {vk: ad} tablosu (mevcut klavye düzenine göre)."""
    table = {}
    for vk in range(1, 255):
        name = key_name(vk)
        if name:
            table[vk] = name
    return table


# Klavye düzenine göre yeri değişen tuşların tarama kodları (harf, rakam, noktalama)
LAYOUT_SCANCODES = (
    [0x29] + list(range(0x02, 0x0E)) + list(range(0x10, 0x1C)) + list(range(0x1E, 0x29))
    + [0x2B, 0x56] + list(range(0x2C, 0x36))
)


def scan_map():
    """Arayüzdeki klavye çizimi için {tarama kodu: vk} (mevcut düzene göre)."""
    return {sc: user32.MapVirtualKeyW(sc, 1) for sc in LAYOUT_SCANCODES}  # MAPVK_VSC_TO_VK


def mods_of(down_keys, exclude=None):
    """Basılı tuşlardan genel değiştirici kümesini çıkarır."""
    mods = set()
    for vk in down_keys:
        if vk != exclude and vk in MOD_OF_VK:
            mods.add(MOD_OF_VK[vk])
    return frozenset(mods)


# --- SendInput dizileri ---

def _set_key(inp, vk, up):
    inp.type = INPUT_KEYBOARD
    sc = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
    flags = KEYEVENTF_KEYUP if up else 0
    # VK + tarama kodu birlikte: Windows uygulamaları VK'yi, oyunlar tarama kodunu okur
    if sc and vk != VK_PAUSE:
        if sc & 0xFF00:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp.ki.wScan = sc & 0xFF
    inp.ki.wVk = vk
    inp.ki.dwFlags = flags
    inp.ki.dwExtraInfo = INJECT_TAG


def _set_mouse(inp, flags, data=0):
    inp.type = INPUT_MOUSE
    inp.mi.dwFlags = flags
    inp.mi.mouseData = data & 0xFFFFFFFF
    inp.mi.dwExtraInfo = INJECT_TAG


def build(events):
    """events: ("key", vk, up) | ("mouse", flags, data) | ("uni", code, up) listesi."""
    arr = (INPUT * len(events))()
    for inp, ev in zip(arr, events):
        kind = ev[0]
        if kind == "key":
            _set_key(inp, ev[1], ev[2])
        elif kind == "mouse":
            _set_mouse(inp, ev[1], ev[2])
        else:
            inp.type = INPUT_KEYBOARD
            inp.ki.wScan = ev[1]
            inp.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if ev[2] else 0)
            inp.ki.dwExtraInfo = INJECT_TAG
    return arr


def key_events(vk, mods=(), action="tap"):
    """Bir tuş (isteğe bağlı değiştiricilerle) için olay listesi."""
    mod_vks = [VK_OF_MOD[m] for m in MOD_ORDER if m in mods]
    if vk in VK_MOUSE:
        down, up, data = MOUSE_FLAGS[VK_MOUSE[vk]]
        main = {"tap": [("mouse", down, data), ("mouse", up, data)],
                "down": [("mouse", down, data)], "up": [("mouse", up, data)]}[action]
    else:
        main = {"tap": [("key", vk, False), ("key", vk, True)],
                "down": [("key", vk, False)], "up": [("key", vk, True)]}[action]
    if action == "up":
        return main + [("key", m, True) for m in reversed(mod_vks)]
    pre = [("key", m, False) for m in mod_vks]
    post = [("key", m, True) for m in reversed(mod_vks)] if action == "tap" else []
    return pre + main + post


def mouse_events(button, action="click"):
    down, up, data = MOUSE_FLAGS[button]
    return {"click": [("mouse", down, data), ("mouse", up, data)],
            "down": [("mouse", down, data)], "up": [("mouse", up, data)]}[action]


def scroll_events(amount):
    return [("mouse", MOUSEEVENTF_WHEEL, int(amount) * 120)]


def char_events(ch, method="unicode"):
    """Tek karakter için olaylar. 'keys' yöntemi klavye düzenindeki tuşlara basar."""
    if ch == "\n":
        return key_events(VK_RETURN)
    if ch == "\t":
        return key_events(VK_TAB)
    if ch == "\r":
        return []
    if method == "keys" and len(ch) == 1 and ord(ch) <= 0xFFFF:
        res = user32.VkKeyScanW(ch)
        if res != -1:
            vk, shift = res & 0xFF, (res >> 8) & 0xFF
            mods = []
            if shift & 2:
                mods.append("ctrl")
            if shift & 4:
                mods.append("alt")
            if shift & 1:
                mods.append("shift")
            return key_events(vk, mods)
    units = ch.encode("utf-16-le")
    out = []
    for i in range(0, len(units), 2):
        code = units[i] | units[i + 1] << 8
        out += [("uni", code, False), ("uni", code, True)]
    return out
