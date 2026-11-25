"""Ana süreç: motoru başlatır/izler, arayüzü sunar ve tepsi ikonunu yönetir."""
import ctypes
import hmac
import json
import logging
import logging.handlers
import multiprocessing
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
import winreg
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import config, engine, keys
from .tray import Tray
from .winapi import kernel32, user32

VERSION = "1.0.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")
ICON_PATH = os.path.join(ROOT, "assets", "icon.ico")
LOCAL_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or config.DATA_DIR, config.APP_NAME)
INSTANCE_PATH = os.path.join(LOCAL_DIR, "instance.json")
WINDOW_TITLE = "Makro Studio"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}

log = logging.getLogger("makro")

user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)


def setup_logging():
    os.makedirs(LOCAL_DIR, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOCAL_DIR, "makro.log"), maxBytes=512 * 1024, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


# --- Windows yardımcıları ---

def find_browser():
    candidates = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
            candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    return next((c for c in candidates if os.path.exists(c)), None)


def focus_existing_window():
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


def open_window(url):
    if focus_existing_window():
        return
    browser = find_browser()
    if browser:
        # Ayrı profil: kullanıcının tarayıcı oturumlarından bağımsız, adres çubuksuz uygulama penceresi
        subprocess.Popen([
            browser, f"--app={url}", f"--user-data-dir={os.path.join(LOCAL_DIR, 'ui')}",
            "--window-size=1320,860", "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--disable-extensions",
        ], close_fds=True)
    else:
        import webbrowser
        webbrowser.open(url)


def autostart_command():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return f'"{pyw}" "{os.path.join(ROOT, "MakroStudio.pyw")}" --tray'


def get_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, config.APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, config.APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, config.APP_NAME)
            except FileNotFoundError:
                pass


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND), ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR), ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD), ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD), ("lpstrFileTitle", wintypes.LPWSTR), ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR), ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD), ("nFileExtension", wintypes.WORD), ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM), ("lpfnHook", wintypes.LPVOID), ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", wintypes.LPVOID), ("dwReserved", wintypes.DWORD), ("FlagsEx", wintypes.DWORD),
    ]


def browse_file():
    """Windows dosya seçme penceresini açar. Seçilen yolu ya da None döndürür."""
    buf = ctypes.create_unicode_buffer(1024)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.lpstrFilter = "Programlar\0*.exe;*.bat;*.cmd;*.lnk\0Tüm dosyalar\0*.*\0\0"
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = 1024
    ofn.lpstrTitle = "Açılacak programı seç"
    ofn.Flags = 0x00001000 | 0x00000800 | 0x00080000 | 0x00000008  # FILEMUSTEXIST|PATHMUSTEXIST|EXPLORER|NOCHANGEDIR
    if ctypes.WinDLL("comdlg32").GetOpenFileNameW(ctypes.byref(ofn)):
        return buf.value
    return None


# --- Motor gözetmeni ---

class EngineSupervisor:
    """Motor sürecini başlatır, çökerse yeniden başlatır ve mesajları dağıtır."""

    def __init__(self, app):
        self.app = app
        self.conn = None
        self.proc = None
        self.send_lock = threading.Lock()
        self.stopping = False

    def start(self):
        parent, child = multiprocessing.Pipe()
        self.proc = multiprocessing.Process(target=engine.main, args=(child,), daemon=True, name="makro-engine")
        self.proc.start()
        child.close()
        self.conn = parent
        self.send(("config", self.app.cfg))
        threading.Thread(target=self._reader, args=(parent, self.proc), daemon=True, name="engine-reader").start()

    def send(self, msg):
        with self.send_lock:
            try:
                self.conn.send(msg)
            except (OSError, ValueError):
                log.warning("motora mesaj gönderilemedi: %s", msg[0])

    def _reader(self, conn, proc):
        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                break
            self.app.on_engine_message(msg)
        if not self.stopping:
            log.error("motor beklenmedik şekilde kapandı (kod %s), yeniden başlatılıyor", proc.exitcode)
            time.sleep(0.5)
            self.start()

    def stop(self):
        self.stopping = True
        self.send(("quit",))
        if self.proc:
            self.proc.join(3)
            if self.proc.is_alive():
                self.proc.terminate()


# --- HTTP arayüz sunucusu ---

class Handler(BaseHTTPRequestHandler):
    server_version = "MakroStudio"
    app = None  # App örneği sunucu kurulurken atanır

    def log_message(self, fmt, *args):
        pass

    def _check_host(self):
        # DNS rebinding saldırılarına karşı sadece kendi adresimizi kabul et
        return self.headers.get("Host") == self.app.host

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self, token):
        return token is not None and hmac.compare_digest(token, self.app.token)

    def do_GET(self):
        if not self._check_host():
            return self._send(403, {"error": "yasak"})
        url = urlsplit(self.path)
        if url.path in STATIC:
            name, ctype = STATIC[url.path]
            try:
                with open(os.path.join(WEB_DIR, name), "rb") as f:
                    data = f.read()
            except OSError:
                return self._send(404, {"error": "bulunamadı"})
            csp = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                   "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            return self._send(200, data, ctype, {"Content-Security-Policy": csp})
        if url.path == "/api/events":
            token = parse_qs(url.query).get("t", [None])[0]
            if not self._authorized(token):
                return self._send(401, {"error": "yetkisiz"})
            return self._events()
        if url.path == "/api/state":
            if not self._authorized(self.headers.get("X-Token")):
                return self._send(401, {"error": "yetkisiz"})
            return self._send(200, self.app.state())
        self._send(404, {"error": "bulunamadı"})

    def do_POST(self):
        if not self._check_host():
            return self._send(403, {"error": "yasak"})
        if not self._authorized(self.headers.get("X-Token")):
            return self._send(401, {"error": "yetkisiz"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 8 * 1024 * 1024:
                return self._send(413, {"error": "çok büyük"})
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            return self._send(400, {"error": "geçersiz istek"})
        path = urlsplit(self.path).path
        try:
            if path == "/api/config":
                return self._send(200, self.app.update_config(body))
            if path == "/api/cmd":
                return self._send(200, self.app.command(body))
        except config.ConfigError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            log.exception("istek hatası")
            return self._send(500, {"error": str(e)})
        self._send(404, {"error": "bulunamadı"})

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q = self.app.subscribe()
        try:
            self._write_event("status", self.app.status)
            while True:
                try:
                    kind, data = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                if kind is None:
                    break
                self._write_event(kind, data)
        except OSError:
            pass
        finally:
            self.app.unsubscribe(q)

    def _write_event(self, kind, data):
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"event: {kind}\ndata: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()


class App:
    def __init__(self, start_hidden):
        self.start_hidden = start_hidden
        self.cfg = config.load()
        self.status = {"enabled": self.cfg["enabled"], "profile": self.cfg["active_profile"],
                       "exe": "", "active": [], "capturing": False, "recording": False}
        self.token = secrets.token_urlsafe(32)
        self.clients = []
        self.clients_lock = threading.Lock()
        self.cfg_lock = threading.Lock()
        self.supervisor = EngineSupervisor(self)
        self.tray = None
        self.server = None
        self.host = None
        self.key_table = {str(vk): name for vk, name in keys.key_table().items()}
        self.scan_map = {str(sc): vk for sc, vk in keys.scan_map().items()}

    @property
    def url(self):
        return f"http://{self.host}/#t={self.token}"

    # --- Olay yayını ---
    def subscribe(self):
        q = queue.Queue(maxsize=500)
        with self.clients_lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.clients_lock:
            if q in self.clients:
                self.clients.remove(q)

    def broadcast(self, kind, data):
        with self.clients_lock:
            for q in self.clients:
                try:
                    q.put_nowait((kind, data))
                except queue.Full:
                    pass

    def on_engine_message(self, msg):
        kind = msg[0]
        if kind == "status":
            self.status = msg[1]
            if self.status["enabled"] != self.cfg["enabled"]:
                # Kısayol ile açıp kapatma kalıcı olsun
                with self.cfg_lock:
                    self.cfg["enabled"] = self.status["enabled"]
                    config.save(self.cfg)
            self.broadcast("status", self.status)
            self._update_tray()
        elif kind == "error":
            log.error("motor: %s", msg[1])
            self.broadcast("engine_error", msg[1].strip().splitlines()[-1])
        else:
            self.broadcast(kind, msg[1])

    def _update_tray(self):
        if not self.tray:
            return
        name = next((p["name"] for p in self.cfg["profiles"] if p["id"] == self.status.get("profile")), "")
        state = "açık" if self.status["enabled"] else "KAPALI"
        self.tray.set_state(self.status["enabled"], f"Makro Studio · Makrolar {state} · {name}")

    # --- API ---
    def state(self):
        return {"version": VERSION, "config": self.cfg, "status": self.status,
                "keys": self.key_table, "scan_map": self.scan_map, "autostart": get_autostart()}

    def update_config(self, body):
        cfg = config.validate(body)
        with self.cfg_lock:
            self.cfg = cfg
            config.save(cfg)
        self.supervisor.send(("config", cfg))
        self._update_tray()
        return {"ok": True, "config": cfg}

    def command(self, body):
        cmd = body.get("cmd")
        if cmd == "enabled":
            self.supervisor.send(("enabled", bool(body.get("value"))))
        elif cmd == "capture":
            self.supervisor.send(("capture", bool(body.get("value"))))
        elif cmd == "record":
            self.supervisor.send(("record", bool(body.get("value")), bool(body.get("mouse"))))
        elif cmd == "stop_all":
            self.supervisor.send(("stop_all",))
        elif cmd == "autostart":
            set_autostart(bool(body.get("value")))
            return {"ok": True, "autostart": get_autostart()}
        elif cmd == "browse":
            return {"ok": True, "path": browse_file()}
        elif cmd == "quit":
            threading.Timer(0.2, self.quit).start()
        else:
            raise config.ConfigError("bilinmeyen komut")
        return {"ok": True}

    def toggle_enabled(self):
        self.supervisor.send(("enabled", not self.status["enabled"]))

    def quit(self):
        if self.tray:
            self.tray.close()

    # --- Yaşam döngüsü ---
    def run(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        Handler.app = self
        self.host = f"127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True, name="http").start()

        with open(INSTANCE_PATH, "w", encoding="utf-8") as f:
            json.dump({"url": self.url, "pid": os.getpid()}, f)

        self.supervisor.start()
        self.tray = Tray(ICON_PATH, lambda: open_window(self.url), self.toggle_enabled, self.quit)
        self._update_tray()
        if not self.start_hidden:
            open_window(self.url)
        log.info("başladı: %s", self.host)
        self.tray.loop()

        # Kapanış
        log.info("kapanıyor")
        self.broadcast(None, None)
        self.supervisor.stop()
        self.server.shutdown()
        try:
            os.remove(INSTANCE_PATH)
        except OSError:
            pass


def main():
    setup_logging()
    start_hidden = "--tray" in sys.argv
    # Tek örnek: zaten çalışıyorsa sadece pencereyi öne getir
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel32.CreateMutexW(None, False, "Local\\MakroStudio")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        if not start_hidden:
            try:
                with open(INSTANCE_PATH, encoding="utf-8") as f:
                    open_window(json.load(f)["url"])
            except (OSError, ValueError, KeyError):
                pass
        return
    try:
        App(start_hidden).run()
    except Exception:
        log.exception("ölümcül hata")
        raise
    finally:
        kernel32.CloseHandle(mutex)
