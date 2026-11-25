"""Makro motoru. Arayüzden ayrı bir süreçte çalışır, böylece arayüz motoru asla yavaşlatamaz.

Yapı:
- Hook thread'i: düşük seviye klavye/fare hook'ları ve ön plan uygulaması takibi.
  Geri çağrılar iş yapmaz, sadece bayrak kurar; böylece sistem girişine gecikme eklenmez.
- Runner thread'leri: her tıklama/tekrar/metin/dizi ataması için önceden açılmış bir thread.
  Tetikte yeni thread açılmadığı için gecikme mikrosaniyeler düzeyindedir.
- Dispatcher thread'i: tuş atama ve program açma gibi anlık işler.
"""
import ctypes
import os
import queue
import sys
import threading
import time
import traceback
from ctypes import wintypes

from . import keys
from .winapi import (
    ABOVE_NORMAL_PRIORITY_CLASS, EVENT_SYSTEM_FOREGROUND, HOOKPROC, INJECT_TAG,
    INPUT_SIZE, KBDLLHOOKSTRUCT, MSLLHOOKSTRUCT, THREAD_PRIORITY_HIGHEST,
    THREAD_PRIORITY_TIME_CRITICAL, WH_KEYBOARD_LL, WH_MOUSE_LL, WINEVENT_OUTOFCONTEXT,
    WINEVENTPROC, WM_KEYDOWN, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP,
    WM_QUIT, WM_RBUTTONDOWN, WM_RBUTTONUP, WM_SYSKEYDOWN, WM_USER, WM_XBUTTONDOWN,
    WM_XBUTTONUP, disable_power_throttling, foreground_exe, kernel32, set_thread_priority,
    user32,
)

SPIN_WINDOW = 0.0008  # Hedef zamana bu kadar kala uyumayı bırakıp hassas bekle (sn)
POLL = 0.004  # Uzun beklemelerde durdurma isteğini kontrol aralığı (sn)
MAX_BATCH = 16  # Geride kalınca tek SendInput çağrısındaki en fazla tekrar
TEXT_CHUNK = 400  # Tek SendInput çağrısındaki en fazla olay (metin yazarken)

WM_APPLY_HOOKS = WM_USER + 1

_send_input = user32.SendInput


def send(arr, count=None):
    """Hazır INPUT dizisini gönderir. Testlerde bu fonksiyon değiştirilir."""
    n = len(arr) if count is None else count
    if n:
        _send_input(n, arr, INPUT_SIZE)


def send_events(events):
    for i in range(0, len(events), TEXT_CHUNK):
        send(keys.build(events[i:i + TEXT_CHUNK]))


class Runner(threading.Thread):
    """Bir atamanın aksiyonunu çalıştıran, önceden açılmış thread."""

    def __init__(self, engine, binding):
        super().__init__(daemon=True, name=f"runner-{binding['id']}")
        self.engine = engine
        self.binding = binding
        self.action = binding["action"]
        self.go = threading.Event()
        self.state_lock = threading.Lock()
        self.active = False
        self.alive = True
        self.gen = 0  # Her başlatmada artar; biten çalışma yeni başlatmayı silmesin
        self.held = []  # Bizim basılı tuttuğumuz olaylar (bırakmak için)
        self._prepare()

    # -- Hazırlık: sıcak döngüde nesne üretmemek için dizileri önceden kur --
    def _prepare(self):
        a = self.action
        t = a["type"]
        if t == "click":
            pair = keys.mouse_events(a["button"])
            self.batch = keys.build(pair * MAX_BATCH)
            self.pair_len = 2
            self.period = 1.0 / a["cps"]
        elif t == "spam":
            key = a["key"]
            self.mod_down = keys.build([("key", keys.VK_OF_MOD[m], False) for m in key["mods"]])
            self.mod_up = keys.build([("key", keys.VK_OF_MOD[m], True) for m in reversed(key["mods"])])
            tap = keys.key_events(key["vk"])
            self.batch = keys.build(tap * MAX_BATCH)
            self.pair_len = len(tap)
            self.period = 1.0 / a["rate"]
        elif t == "text":
            text = a["text"] + ("\n" if a["enter"] else "")
            self.chars = [keys.char_events(ch, a["method"]) for ch in text]
            self.all_events = [ev for group in self.chars for ev in group]

    # -- Hook thread'inden çağrılanlar (hızlı, engellemeyen) --
    def start_run(self):
        with self.state_lock:
            if self.active or not self.alive:
                return
            self.gen += 1
            self.active = True
        self.engine.notify_active(self.binding["id"], True)
        self.go.set()

    def stop_run(self):
        self.active = False

    def toggle(self):
        if self.active:
            self.stop_run()
        else:
            self.start_run()

    def kill(self):
        self.alive = False
        self.active = False
        self.go.set()

    # -- Çalışma döngüsü --
    def run(self):
        set_thread_priority(THREAD_PRIORITY_HIGHEST)
        bid = self.binding["id"]
        while True:
            self.go.wait()
            self.go.clear()
            if not self.alive:
                self.engine.notify_active(bid, False)
                break
            if not self.active:
                self.engine.notify_active(bid, False)
                continue
            gen = self.gen
            try:
                getattr(self, "_run_" + self.action["type"])()
            except Exception:
                self.engine.log_error(traceback.format_exc())
            finally:
                self._release_held()
                with self.state_lock:
                    # Bu sırada yeniden başlatıldıysa aktif kalır, go zaten kurulu
                    finished = self.gen == gen
                    if finished:
                        self.active = False
                if finished:
                    self.engine.notify_active(bid, False)

    def wait_until(self, deadline):
        """Hedef zamana kadar bekler. Durdurulursa False döner."""
        perf = time.perf_counter
        sleep = time.sleep
        while self.active:
            remaining = deadline - perf()
            if remaining <= 0:
                return True
            if remaining > SPIN_WINDOW:
                sleep(min(remaining - SPIN_WINDOW, POLL))
            else:
                sleep(0)  # GIL'i bırakarak bekle, hook thread'i hiç bekletilmesin
        return False

    def _repeat_batch(self):
        """Mutlak zaman çizelgesiyle tekrar: hız kaymaz, geride kalırsa toplu gönderir."""
        perf = time.perf_counter
        sleep = time.sleep
        batch = self.batch
        pair_len = self.pair_len
        period = self.period
        next_at = perf()
        while self.active:
            now = perf()
            if now >= next_at:
                due = int((now - next_at) / period) + 1
                send(batch, min(due, MAX_BATCH) * pair_len)
                next_at += due * period  # Sınırı aşan gecikme telafi edilmez
            remaining = next_at - perf()
            if remaining > SPIN_WINDOW:
                sleep(min(remaining - SPIN_WINDOW, POLL))
            else:
                while self.active and perf() < next_at:
                    sleep(0)

    def _run_click(self):
        self._repeat_batch()

    def _run_spam(self):
        if len(self.mod_down):
            send(self.mod_down)
            self.held.append(("arr", self.mod_up))
        self._repeat_batch()

    def _run_text(self):
        self.engine.release_user_mods()
        delay = self.action["delay"] / 1000
        if not delay:
            send_events(self.all_events)
            return
        next_at = time.perf_counter()
        for group in self.chars:
            if not self.wait_until(next_at):
                return
            send(keys.build(group))
            next_at += delay

    def _run_seq(self):
        self.engine.release_user_mods()
        steps = self.action["steps"]
        looping = self.binding["mode"] != "press"
        count = 0
        while self.active:
            for step in steps:
                if not self.active or not self._do_step(step):
                    return
            count += 1
            if not looping and count >= self.action["repeat"]:
                return
            if not steps:
                return

    def _do_step(self, s):
        t = s["t"]
        if t == "wait":
            return self.wait_until(time.perf_counter() + s["ms"] / 1000)
        if t == "key":
            send(keys.build(keys.key_events(s["vk"], s["mods"], s["do"])))
            self._track(("vk", s["vk"], tuple(s["mods"])), s["do"])
        elif t == "mouse":
            send(keys.build(keys.mouse_events(s["btn"], s["do"])))
            self._track(("btn", s["btn"]), s["do"])
        elif t == "text":
            events = []
            for ch in s["text"]:
                events += keys.char_events(ch)
            send_events(events)
        elif t == "scroll":
            send(keys.build(keys.scroll_events(s["amount"])))
        return True

    def _track(self, item, do):
        if do == "down":
            if item not in self.held:
                self.held.append(item)
        elif do == "up" and item in self.held:
            self.held.remove(item)

    def _release_held(self):
        """Durdurulunca bizim bastığımız her şeyi bırak: tuş asla basılı kalmaz."""
        while self.held:
            item = self.held.pop()
            if item[0] == "arr":
                send(item[1])
            elif item[0] == "vk":
                send(keys.build(keys.key_events(item[1], item[2], "up")))
            else:
                send(keys.build(keys.mouse_events(item[1], "up")))


class Engine:
    def __init__(self, outbox):
        self.outbox = outbox
        self.cfg = None
        self.enabled = True
        self.profile_id = None
        self.manual_profile = None
        self.fg_exe = ""
        self.runners = {}  # binding id -> Runner (tüm profiller)
        self.lookup = {}  # vk -> {mods frozenset veya None: binding}
        self.bindings = {}  # binding id -> binding
        self.mouse_triggers = False
        self.toggle_key = (0x13, frozenset())
        self.down_keys = set()  # Fiziksel olarak basılı tuşlar
        self.blocked = set()  # Basışı engellenen, bırakışı da engellenecek tuşlar
        self.pressed = {}  # vk -> o basışın tetiklediği binding
        self.active_ids = set()
        self.capturing = False
        self.cap_mod = None
        self.recording = False
        self.record_mouse = False
        self.record_events = []
        self.dispatch_q = queue.SimpleQueue()
        self.hook_tid = None
        self.kb_hook = None
        self.mouse_hook = None
        self.lock = threading.Lock()
        self.status_lock = threading.Lock()

    # --- Mesajlar ---
    def post(self, *msg):
        self.outbox.put(msg)

    def log_error(self, text):
        self.post("error", text)

    def push_status(self):
        with self.status_lock:
            self.post("status", {
                "enabled": self.enabled,
                "profile": self.profile_id,
                "exe": self.fg_exe,
                "active": sorted(self.active_ids),
                "capturing": self.capturing,
                "recording": self.recording,
            })

    def notify_active(self, binding_id, on):
        with self.status_lock:
            if on:
                self.active_ids.add(binding_id)
            elif binding_id in self.active_ids:
                self.active_ids.discard(binding_id)
            else:
                return
        self.push_status()

    # --- Ayar ---
    def apply_config(self, cfg):
        with self.lock:
            self.stop_all()
            for r in self.runners.values():
                r.kill()
            self.cfg = cfg
            self.enabled = cfg["enabled"]
            hk = cfg["toggle_hotkey"]
            self.toggle_key = (hk["vk"], frozenset(hk["mods"]))
            self.manual_profile = cfg["active_profile"]
            self.runners = {}
            self.bindings = {}
            for p in cfg["profiles"]:
                for b in p["bindings"]:
                    if not b["enabled"]:
                        continue
                    self.bindings[b["id"]] = b
                    if b["action"]["type"] in ("click", "spam", "text", "seq"):
                        r = Runner(self, b)
                        r.start()
                        self.runners[b["id"]] = r
            self._select_profile(force=True)
        self.push_status()

    def _profile_for(self, exe):
        if self.cfg["auto_switch"] and exe:
            for p in self.cfg["profiles"]:
                if exe in p["apps"]:
                    return p
        for p in self.cfg["profiles"]:
            if p["id"] == self.manual_profile:
                return p
        return self.cfg["profiles"][0]

    def _select_profile(self, force=False):
        profile = self._profile_for(self.fg_exe)
        if profile["id"] == self.profile_id and not force:
            return
        if not force:
            self.stop_all()
        self.profile_id = profile["id"]
        lookup = {}
        mouse = False
        for b in profile["bindings"]:
            if not b["enabled"]:
                continue
            t = b["trigger"]
            lookup.setdefault(t["vk"], {})[frozenset(t["mods"]) or None] = b
            mouse = mouse or t["vk"] in keys.TRIGGER_MOUSE_VKS
        self.lookup = lookup
        self.mouse_triggers = mouse
        self.request_hooks()
        self.push_status()

    def on_foreground(self):
        exe = foreground_exe()
        if exe != self.fg_exe:
            self.fg_exe = exe
            if self.cfg:
                self._select_profile()
            self.push_status()

    def set_enabled(self, on):
        self.enabled = on
        if not on:
            self.stop_all()
        self.push_status()

    def stop_all(self):
        for r in self.runners.values():
            r.stop_run()
        # Basılı tutulan tuş atamalarını bırak
        for vk, b in list(self.pressed.items()):
            if b["action"]["type"] == "remap":
                self.dispatch_q.put(("remap_up", b))
        self.pressed.clear()

    # --- Yakalama ve kayıt ---
    def set_capture(self, on):
        self.capturing = on
        self.cap_mod = None
        self.request_hooks()
        self.push_status()

    def _finish_capture(self, vk, mods):
        self.capturing = False
        self.cap_mod = None
        self.request_hooks()
        self.post("captured", None if vk is None else {
            "vk": vk, "mods": [m for m in keys.MOD_ORDER if m in mods]})
        self.push_status()

    def set_recording(self, on, mouse=False):
        if on:
            self.stop_all()
            self.record_events = []
            self.record_mouse = mouse
            self.recording = True
        elif self.recording:
            self.recording = False
            self.post("recorded", self._events_to_steps(self.record_events))
        self.request_hooks()
        self.push_status()

    @staticmethod
    def _events_to_steps(events):
        steps = []
        prev = None
        for t, vk, down in events:
            if prev is not None:
                ms = round((t - prev) * 1000)
                if ms > 0:
                    steps.append({"t": "wait", "ms": ms})
            prev = t
            if vk in keys.VK_MOUSE:
                steps.append({"t": "mouse", "btn": keys.VK_MOUSE[vk], "do": "down" if down else "up"})
            else:
                steps.append({"t": "key", "vk": vk, "mods": [], "do": "down" if down else "up"})
        return steps[:5000]

    def release_user_mods(self):
        """Kullanıcının basılı tuttuğu değiştiricileri (Ctrl, Shift...) yazmadan önce bırakır."""
        mods = [vk for vk in self.down_keys if vk in keys.MOD_OF_VK]
        if mods:
            send(keys.build([("key", vk, True) for vk in mods]))

    # --- Hook mantığı (hook thread'inde çalışır, hızlı olmalı) ---
    def handle(self, vk, down):
        """Fiziksel bir tuş olayını işler. True dönerse olay engellenir."""
        if not down:
            self.down_keys.discard(vk)
            b = self.pressed.pop(vk, None)
            if b is not None:
                self._trigger_up(b)
            if self.capturing:
                if vk == self.cap_mod:
                    self._finish_capture(vk, ())
            elif self.recording:
                self._record(vk, False)
            if vk in self.blocked:
                self.blocked.discard(vk)
                return True
            return False

        repeat = vk in self.down_keys
        self.down_keys.add(vk)

        if self.capturing:
            return self._capture_down(vk, repeat)
        if self.recording:
            if not repeat:
                self._record(vk, True)
            return False
        if repeat:
            if vk in self.blocked:
                b = self.pressed.get(vk)
                if b is not None and b["action"]["type"] == "remap":
                    self.dispatch_q.put(("remap_repeat", b))
                return True
            return False

        mods = keys.mods_of(self.down_keys, exclude=vk)
        if (vk, mods) == self.toggle_key:
            self.set_enabled(not self.enabled)
            self.blocked.add(vk)
            return True
        if not self.enabled:
            return False

        entry = self.lookup.get(vk)
        if entry is None:
            return False
        # Önce birebir değiştirici eşleşmesi, yoksa değiştiricisiz atama (Shift'e basarken de çalışsın)
        b = entry.get(mods or None) or entry.get(None)
        if b is None:
            return False
        self.pressed[vk] = b
        self._trigger_down(b)
        if b["block"]:
            self.blocked.add(vk)
            return True
        return False

    def _capture_down(self, vk, repeat):
        if repeat:
            return vk in self.blocked
        if vk in keys.MOD_OF_VK:
            self.cap_mod = vk  # Tek başına bırakılırsa değiştiricinin kendisi atanır
            return False
        self.cap_mod = None
        mods = keys.mods_of(self.down_keys, exclude=vk)
        self.blocked.add(vk)
        if vk == keys.VK_ESCAPE and not mods:
            self._finish_capture(None, ())
        else:
            self._finish_capture(vk, mods)
        return True

    def _record(self, vk, down):
        self.record_events.append((time.perf_counter(), vk, down))

    def _trigger_down(self, b):
        t = b["action"]["type"]
        if t == "remap":
            self.dispatch_q.put(("remap_down", b))
        elif t == "launch":
            self.dispatch_q.put(("launch", b))
        elif t == "disable":
            pass
        else:
            r = self.runners.get(b["id"])
            if r is None:
                return
            if b["mode"] == "toggle":
                r.toggle()
            else:
                r.start_run()

    def _trigger_up(self, b):
        t = b["action"]["type"]
        if t == "remap":
            self.dispatch_q.put(("remap_up", b))
        elif b["mode"] == "hold":
            r = self.runners.get(b["id"])
            if r is not None:
                r.stop_run()

    # --- Dispatcher thread'i ---
    def dispatcher(self):
        set_thread_priority(THREAD_PRIORITY_HIGHEST)
        remap_down = set()
        while True:
            kind, b = self.dispatch_q.get()
            if kind == "quit":
                for target in list(remap_down):
                    send(keys.build(keys.key_events(target[0], target[1], "up")))
                return
            try:
                if kind.startswith("remap"):
                    target = b["action"]["target"]
                    key = (target["vk"], tuple(target["mods"]))
                    if kind == "remap_down":
                        send(keys.build(keys.key_events(*key, "down")))
                        remap_down.add(key)
                        self.notify_active(b["id"], True)
                    elif kind == "remap_repeat":
                        if key[0] not in keys.VK_MOUSE:
                            send(keys.build([("key", key[0], False)]))
                    elif key in remap_down:
                        send(keys.build(keys.key_events(*key, "up")))
                        remap_down.discard(key)
                        self.notify_active(b["id"], False)
                elif kind == "launch":
                    a = b["action"]
                    self.notify_active(b["id"], True)
                    try:
                        if a["args"]:
                            os.startfile(a["target"], arguments=a["args"])
                        else:
                            os.startfile(a["target"])
                    finally:
                        self.notify_active(b["id"], False)
            except Exception:
                self.log_error(traceback.format_exc())

    # --- Hook thread'i ---
    def request_hooks(self):
        if self.hook_tid:
            user32.PostThreadMessageW(self.hook_tid, WM_APPLY_HOOKS, 0, 0)

    def _apply_hooks(self):
        # Fare hook'u her fare hareketinde çağrılır; sadece gerçekten gerekiyorsa kurulur
        want_mouse = self.mouse_triggers or self.capturing or self.recording
        if want_mouse and not self.mouse_hook:
            self.mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, None, 0)
        elif not want_mouse and self.mouse_hook:
            user32.UnhookWindowsHookEx(self.mouse_hook)
            self.mouse_hook = None

    def hook_thread(self, ready):
        set_thread_priority(THREAD_PRIORITY_TIME_CRITICAL)
        call_next = user32.CallNextHookEx
        from_address = KBDLLHOOKSTRUCT.from_address
        handle = self.handle

        def kb_proc(code, wparam, lparam):
            if code == 0:
                k = from_address(lparam)
                try:
                    if k.dwExtraInfo != INJECT_TAG and handle(k.vkCode, wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                        return 1
                except Exception:
                    self.log_error(traceback.format_exc())
            return call_next(None, code, wparam, lparam)

        mouse_vk = {
            WM_MBUTTONDOWN: (4, True), WM_MBUTTONUP: (4, False),
            WM_LBUTTONDOWN: (1, True), WM_LBUTTONUP: (1, False),
            WM_RBUTTONDOWN: (2, True), WM_RBUTTONUP: (2, False),
        }
        ms_from = MSLLHOOKSTRUCT.from_address

        def mouse_proc(code, wparam, lparam):
            # Fare hareketi en sık olay: ilk kontrolde hemen geçir
            if code == 0 and wparam != 0x0200:
                m = ms_from(lparam)
                if m.dwExtraInfo != INJECT_TAG:
                    if wparam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                        vk = 4 + (m.mouseData >> 16)  # XBUTTON1=1 -> 5, XBUTTON2=2 -> 6
                        down = wparam == WM_XBUTTONDOWN
                    elif wparam in mouse_vk:
                        vk, down = mouse_vk[wparam]
                    else:
                        return call_next(None, code, wparam, lparam)
                    if vk in (1, 2):
                        # Sol/sağ tık sadece kayda girer, asla engellenmez
                        if self.recording and self.record_mouse:
                            self._record(vk, down)
                    elif handle(vk, down):
                        return 1
            return call_next(None, code, wparam, lparam)

        def win_event(hook, event, hwnd, obj, child, thread, ms):
            try:
                self.on_foreground()
            except Exception:
                self.log_error(traceback.format_exc())

        # Geri çağrı nesneleri çöp toplanmasın diye referans tutulur
        self._kb_proc = HOOKPROC(kb_proc)
        self._mouse_proc = HOOKPROC(mouse_proc)
        self._win_event = WINEVENTPROC(win_event)

        self.hook_tid = kernel32.GetCurrentThreadId()
        self.kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, None, 0)
        win_hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self._win_event,
            0, 0, WINEVENT_OUTOFCONTEXT,
        )
        self._apply_hooks()
        ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APPLY_HOOKS:
                self._apply_hooks()
        if self.mouse_hook:
            user32.UnhookWindowsHookEx(self.mouse_hook)
        user32.UnhookWindowsHookEx(self.kb_hook)
        user32.UnhookWinEvent(win_hook)

    def start(self):
        threading.Thread(target=self.dispatcher, daemon=True, name="dispatcher").start()
        ready = threading.Event()
        self._hook = threading.Thread(target=self.hook_thread, args=(ready,), daemon=True, name="hooks")
        self._hook.start()
        ready.wait()

    def shutdown(self):
        with self.lock:
            self.stop_all()
            for r in self.runners.values():
                r.kill()
        self.dispatch_q.put(("quit", None))
        if self.hook_tid:
            user32.PostThreadMessageW(self.hook_tid, WM_QUIT, 0, 0)
        self._hook.join(1)
        # Runner'ların bıraktığı tuşların gönderilmesi için kısa süre tanı
        deadline = time.time() + 1
        for r in self.runners.values():
            r.join(max(0, deadline - time.time()))


def main(conn):
    """Motor süreci giriş noktası. conn: ana süreçle multiprocessing bağlantısı."""
    kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS)
    disable_power_throttling()
    # GIL el değiştirme aralığını kısalt: hook thread'i en fazla bu kadar bekler
    sys.setswitchinterval(0.0005)

    outbox = queue.SimpleQueue()

    def sender():
        while True:
            msg = outbox.get()
            if msg is None:
                return
            try:
                conn.send(msg)
            except (OSError, EOFError, ValueError):
                return

    send_thread = threading.Thread(target=sender, daemon=True, name="sender")
    send_thread.start()

    engine = Engine(outbox)
    engine.start()
    engine.fg_exe = foreground_exe()
    try:
        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                break  # Ana süreç kapandı
            kind = msg[0]
            if kind == "config":
                engine.apply_config(msg[1])
            elif kind == "enabled":
                engine.set_enabled(msg[1])
            elif kind == "capture":
                engine.set_capture(msg[1])
            elif kind == "record":
                engine.set_recording(msg[1], msg[2])
            elif kind == "stop_all":
                engine.stop_all()
            elif kind == "quit":
                break
    finally:
        engine.shutdown()
        outbox.put(None)
        send_thread.join(1)
