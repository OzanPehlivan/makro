"""Ayar dosyası: varsayılanlar, doğrulama, yükleme ve kaydetme."""
import json
import os
import uuid

APP_NAME = "MakroStudio"
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

ACTION_TYPES = ("click", "spam", "text", "seq", "remap", "launch", "disable")
MODES = {
    "click": ("hold", "toggle"),
    "spam": ("hold", "toggle"),
    "text": ("press",),
    "seq": ("press", "hold", "toggle"),
    "remap": ("hold",),
    "launch": ("press",),
    "disable": ("hold",),
}
BUTTONS = ("left", "right", "middle", "x1", "x2")
MODS = ("ctrl", "shift", "alt", "win")
MAX_RATE = 1000
MAX_TEXT = 20000
MAX_STEPS = 5000
MAX_WAIT_MS = 600000
MAX_BINDINGS = 300
MAX_PROFILES = 50


class ConfigError(ValueError):
    pass


def new_id():
    return uuid.uuid4().hex[:12]


def default_config():
    profile_id = new_id()
    return {
        "version": 1,
        "enabled": True,
        "auto_switch": True,
        "toggle_hotkey": {"vk": 0x13, "mods": []},  # Pause
        "active_profile": profile_id,
        "profiles": [{
            "id": profile_id,
            "name": "Genel",
            "apps": [],
            "bindings": [{
                "id": new_id(),
                "name": "Otomatik tıklama",
                "enabled": True,
                "trigger": {"vk": 0x52, "mods": []},  # R
                "block": False,
                "mode": "hold",
                "action": {"type": "click", "button": "left", "cps": 100},
            }],
        }],
    }


# --- Doğrulama ---

def _int(v, lo, hi, name):
    if type(v) is not int or not lo <= v <= hi:
        raise ConfigError(f"{name}: {lo}-{hi} arası tam sayı olmalı")
    return v


def _str(v, max_len, name):
    if not isinstance(v, str) or len(v) > max_len:
        raise ConfigError(f"{name}: en fazla {max_len} karakterlik metin olmalı")
    return v


def _bool(v, name):
    if type(v) is not bool:
        raise ConfigError(f"{name}: true/false olmalı")
    return v


def _choice(v, options, name):
    if v not in options:
        raise ConfigError(f"{name}: geçersiz değer")
    return v


def _mods(v, name):
    if not isinstance(v, list) or any(m not in MODS for m in v):
        raise ConfigError(f"{name}: geçersiz değiştirici")
    return [m for m in MODS if m in v]


def _key(v, name, allow_mouse=True):
    if not isinstance(v, dict):
        raise ConfigError(f"{name}: tuş eksik")
    vk = _int(v.get("vk"), 1, 254, f"{name}.vk")
    if not allow_mouse and vk in (1, 2):
        raise ConfigError(f"{name}: sol/sağ tık tetik olamaz")
    return {"vk": vk, "mods": _mods(v.get("mods", []), f"{name}.mods")}


def _step(s, i):
    name = f"adım {i + 1}"
    if not isinstance(s, dict):
        raise ConfigError(f"{name}: geçersiz")
    t = s.get("t")
    if t == "key":
        return {"t": "key", "vk": _int(s.get("vk"), 1, 254, name),
                "mods": _mods(s.get("mods", []), name),
                "do": _choice(s.get("do", "tap"), ("tap", "down", "up"), name)}
    if t == "mouse":
        return {"t": "mouse", "btn": _choice(s.get("btn"), BUTTONS, name),
                "do": _choice(s.get("do", "click"), ("click", "down", "up"), name)}
    if t == "text":
        return {"t": "text", "text": _str(s.get("text", ""), MAX_TEXT, name)}
    if t == "wait":
        return {"t": "wait", "ms": _int(s.get("ms"), 0, MAX_WAIT_MS, name)}
    if t == "scroll":
        return {"t": "scroll", "amount": _int(s.get("amount"), -100, 100, name)}
    raise ConfigError(f"{name}: bilinmeyen adım türü")


def _action(a):
    if not isinstance(a, dict):
        raise ConfigError("aksiyon eksik")
    t = _choice(a.get("type"), ACTION_TYPES, "aksiyon türü")
    if t == "click":
        return {"type": t, "button": _choice(a.get("button"), BUTTONS, "düğme"),
                "cps": _int(a.get("cps"), 1, MAX_RATE, "CPS")}
    if t == "spam":
        return {"type": t, "key": _key(a.get("key"), "tekrarlanacak tuş"),
                "rate": _int(a.get("rate"), 1, MAX_RATE, "hız")}
    if t == "text":
        return {"type": t, "text": _str(a.get("text", ""), MAX_TEXT, "metin"),
                "method": _choice(a.get("method", "unicode"), ("unicode", "keys"), "yazma yöntemi"),
                "delay": _int(a.get("delay", 0), 0, 5000, "karakter gecikmesi"),
                "enter": _bool(a.get("enter", False), "enter")}
    if t == "seq":
        steps = a.get("steps")
        if not isinstance(steps, list) or len(steps) > MAX_STEPS:
            raise ConfigError(f"adımlar: en fazla {MAX_STEPS} adım")
        return {"type": t, "steps": [_step(s, i) for i, s in enumerate(steps)],
                "repeat": _int(a.get("repeat", 1), 1, 100000, "tekrar sayısı")}
    if t == "remap":
        return {"type": t, "target": _key(a.get("target"), "hedef tuş")}
    if t == "launch":
        target = _str(a.get("target", ""), 2000, "hedef").strip()
        if not target:
            raise ConfigError("açılacak program veya bağlantı boş olamaz")
        return {"type": t, "target": target, "args": _str(a.get("args", ""), 2000, "argümanlar")}
    return {"type": "disable"}


def _binding(b):
    if not isinstance(b, dict):
        raise ConfigError("atama geçersiz")
    action = _action(b.get("action"))
    t = action["type"]
    mode = b.get("mode", MODES[t][0])
    if mode not in MODES[t]:
        mode = MODES[t][0]
    return {
        "id": _str(b.get("id") or new_id(), 40, "id"),
        "name": _str(b.get("name", ""), 80, "ad"),
        "enabled": _bool(b.get("enabled", True), "etkin"),
        "trigger": _key(b.get("trigger"), "tetik", allow_mouse=False),
        # Tuş atama ve devre dışı bırakma orijinal tuşu her zaman engeller
        "block": True if t in ("remap", "disable") else _bool(b.get("block", True), "engelle"),
        "mode": mode,
        "action": action,
    }


def _profile(p):
    if not isinstance(p, dict):
        raise ConfigError("profil geçersiz")
    name = _str(p.get("name", ""), 60, "profil adı").strip() or "Profil"
    apps = p.get("apps", [])
    if not isinstance(apps, list) or len(apps) > 50:
        raise ConfigError("uygulama listesi geçersiz")
    apps = sorted({_str(x, 260, "uygulama").strip().lower() for x in apps} - {""})
    bindings = p.get("bindings", [])
    if not isinstance(bindings, list) or len(bindings) > MAX_BINDINGS:
        raise ConfigError(f"bir profilde en fazla {MAX_BINDINGS} atama olabilir")
    bindings = [_binding(b) for b in bindings]
    seen = set()
    for b in bindings:
        if not b["enabled"]:
            continue
        key = (b["trigger"]["vk"], tuple(b["trigger"]["mods"]))
        if key in seen:
            raise ConfigError(f"'{name}' profilinde aynı tetik iki kez kullanılmış")
        seen.add(key)
    return {"id": _str(p.get("id") or new_id(), 40, "profil id"), "name": name,
            "apps": apps, "bindings": bindings}


def validate(cfg):
    """Ayarı doğrular ve temizlenmiş bir kopyasını döndürür. Hatada ConfigError."""
    if not isinstance(cfg, dict):
        raise ConfigError("ayar geçersiz")
    profiles = cfg.get("profiles")
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= MAX_PROFILES:
        raise ConfigError(f"1-{MAX_PROFILES} arası profil olmalı")
    profiles = [_profile(p) for p in profiles]
    ids = [p["id"] for p in profiles]
    if len(set(ids)) != len(ids):
        raise ConfigError("profil kimlikleri benzersiz olmalı")
    active = cfg.get("active_profile")
    if active not in ids:
        active = ids[0]
    hotkey = _key(cfg.get("toggle_hotkey"), "aç/kapat kısayolu", allow_mouse=False)
    for p in profiles:
        for b in p["bindings"]:
            if b["enabled"] and b["trigger"] == hotkey:
                raise ConfigError(f"'{b['name'] or 'atama'}' aç/kapat kısayolu ile çakışıyor")
    return {
        "version": 1,
        "enabled": _bool(cfg.get("enabled", True), "etkin"),
        "auto_switch": _bool(cfg.get("auto_switch", True), "otomatik profil"),
        "toggle_hotkey": hotkey,
        "active_profile": active,
        "profiles": profiles,
    }


def load():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return validate(json.load(f))
    except FileNotFoundError:
        return default_config()
    except (OSError, ValueError):
        # Bozuk dosyayı silmek yerine yedekle, varsayılanla devam et
        try:
            os.replace(CONFIG_PATH, CONFIG_PATH + ".bozuk")
        except OSError:
            pass
        return default_config()


def save(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)  # Yarım yazılmış dosya kalmasın
