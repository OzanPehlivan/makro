"""Motor testleri. Gerçek giriş GÖNDERİLMEZ: send() sahte bir kaydediciyle değiştirilir,
tuş olayları hook kurulmadan doğrudan Engine.handle'a verilir."""
import copy
import os
import queue
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config, engine, keys  # noqa: E402
from core.winapi import INJECT_TAG, INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE  # noqa: E402

VK_R, VK_C, VK_F1, VK_F2, VK_F3, VK_LCTRL, VK_LSHIFT, VK_ESC = 0x52, 0x43, 0x70, 0x71, 0x72, 0xA2, 0xA0, 0x1B


class Recorder:
    """send() yerine geçer, gönderilen olayları okunur biçimde saklar."""

    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def __call__(self, arr, count=None):
        n = len(arr) if count is None else count
        out = []
        for inp in arr[:n]:
            if inp.type == INPUT_KEYBOARD:
                assert inp.ki.dwExtraInfo == INJECT_TAG
                up = bool(inp.ki.dwFlags & KEYEVENTF_KEYUP)
                if inp.ki.dwFlags & KEYEVENTF_UNICODE:
                    out.append(("uni", inp.ki.wScan, up))
                else:
                    out.append(("key", inp.ki.wVk, up))
            else:
                assert inp.mi.dwExtraInfo == INJECT_TAG
                out.append(("mouse", inp.mi.dwFlags, inp.mi.mouseData))
        with self.lock:
            self.events.extend(out)

    def take(self):
        with self.lock:
            ev, self.events = self.events, []
        return ev


def binding(vk, action, mode, mods=(), block=True, bid=None):
    return {"id": bid or config.new_id(), "name": "", "enabled": True,
            "trigger": {"vk": vk, "mods": list(mods)}, "block": block, "mode": mode, "action": action}


def make_cfg(bindings, apps=()):
    cfg = config.default_config()
    cfg["profiles"][0]["bindings"] = bindings
    cfg["profiles"][0]["apps"] = list(apps)
    return config.validate(cfg)


def wait_for(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.rec = Recorder()
        self._orig_send = engine.send
        engine.send = self.rec
        self.eng = engine.Engine(queue.SimpleQueue())
        self.disp = threading.Thread(target=self.eng.dispatcher, daemon=True)
        self.disp.start()

    def tearDown(self):
        self.eng.stop_all()
        for r in self.eng.runners.values():
            r.kill()
        self.eng.dispatch_q.put(("quit", None))
        self.disp.join(1)
        engine.send = self._orig_send

    def apply(self, bindings, **kw):
        self.eng.apply_config(make_cfg(bindings, **kw))
        return self.eng

    def press(self, vk):
        return self.eng.handle(vk, True)

    def release(self, vk):
        return self.eng.handle(vk, False)

    def runner(self, b):
        return self.eng.runners[b["id"]]

    def idle(self, b, timeout=2.0):
        """Runner işini bitirip (tuşları bırakıp) "durdu" bildirene kadar bekler."""
        return wait_for(lambda: not self.runner(b).active and b["id"] not in self.eng.active_ids, timeout)

    # --- Tıklama ---
    def test_hold_click_rate_and_stop(self):
        b = binding(VK_R, {"type": "click", "button": "left", "cps": 200}, "hold")
        self.apply([b])
        self.assertTrue(self.press(VK_R))
        time.sleep(0.5)
        self.release(VK_R)
        self.assertTrue(self.idle(b))
        ev = self.rec.take()
        downs = [e for e in ev if e == ("mouse", 0x0002, 0)]
        ups = [e for e in ev if e == ("mouse", 0x0004, 0)]
        self.assertEqual(len(downs), len(ups), "her basışın bırakışı olmalı")
        self.assertTrue(90 <= len(downs) <= 110, f"200 CPS * 0.5 sn ~ 100, gelen {len(downs)}")
        time.sleep(0.1)
        self.assertEqual(self.rec.take(), [], "bırakınca tıklama durmalı")

    def test_right_click_and_block_flag(self):
        b = binding(VK_R, {"type": "click", "button": "right", "cps": 50}, "hold", block=False)
        self.apply([b])
        self.assertFalse(self.press(VK_R), "engelle kapalıyken tuş geçmeli")
        time.sleep(0.1)
        self.assertFalse(self.release(VK_R))
        self.idle(b)
        ev = self.rec.take()
        self.assertIn(("mouse", 0x0008, 0), ev)
        self.assertIn(("mouse", 0x0010, 0), ev)

    def test_toggle_mode(self):
        b = binding(VK_R, {"type": "click", "button": "left", "cps": 100}, "toggle")
        self.apply([b])
        self.press(VK_R)
        self.release(VK_R)
        time.sleep(0.2)
        self.assertTrue(self.runner(b).active, "bırakınca devam etmeli")
        self.press(VK_R)
        self.release(VK_R)
        self.assertTrue(self.idle(b))

    def test_rapid_press_release_cycles(self):
        b = binding(VK_R, {"type": "click", "button": "left", "cps": 1000}, "hold")
        self.apply([b])
        for _ in range(300):
            self.press(VK_R)
            self.release(VK_R)
        self.press(VK_R)
        time.sleep(0.1)
        self.assertTrue(self.runner(b).active, "son basış kaybolmamalı")
        self.release(VK_R)
        self.assertTrue(self.idle(b))
        ev = self.rec.take()
        self.assertEqual(ev.count(("mouse", 2, 0)), ev.count(("mouse", 4, 0)))
        time.sleep(0.05)
        self.assertEqual(self.rec.take(), [])

    # --- Tuş tekrarı ---
    def test_spam_with_modifier_releases(self):
        b = binding(VK_F1, {"type": "spam", "key": {"vk": VK_C, "mods": ["ctrl"]}, "rate": 100}, "hold")
        self.apply([b])
        self.press(VK_F1)
        time.sleep(0.15)
        self.release(VK_F1)
        self.idle(b)
        ev = self.rec.take()
        self.assertEqual(ev[0], ("key", VK_LCTRL, False))
        self.assertEqual(ev[-1], ("key", VK_LCTRL, True), "Ctrl en sonda bırakılmalı")
        self.assertEqual(ev.count(("key", VK_C, False)), ev.count(("key", VK_C, True)))
        self.assertGreater(ev.count(("key", VK_C, False)), 5)

    # --- Metin ---
    def test_text_unicode(self):
        text = "Merhaba ğüşİıç 😀"
        b = binding(VK_F1, {"type": "text", "text": text, "method": "unicode", "delay": 0, "enter": True}, "press")
        self.apply([b])
        self.press(VK_F1)
        self.release(VK_F1)
        self.assertTrue(self.idle(b))
        ev = self.rec.take()
        self.assertEqual(ev[-2:], [("key", keys.VK_RETURN, False), ("key", keys.VK_RETURN, True)])
        units = [e[1] for e in ev if e[0] == "uni" and not e[2]]
        decoded = b"".join(u.to_bytes(2, "little") for u in units).decode("utf-16-le")
        self.assertEqual(decoded, text)

    def test_text_releases_held_modifiers_first(self):
        b = binding(VK_F1, {"type": "text", "text": "a", "method": "unicode", "delay": 0, "enter": False}, "press",
                    mods=["ctrl"])
        self.apply([b])
        self.press(VK_LCTRL)
        self.assertTrue(self.press(VK_F1))
        self.assertTrue(self.idle(b))
        ev = self.rec.take()
        self.assertEqual(ev[0], ("key", VK_LCTRL, True), "yazmadan önce Ctrl bırakılmalı")

    def test_text_with_delay_can_be_interrupted(self):
        b = binding(VK_F1, {"type": "text", "text": "x" * 100, "method": "unicode", "delay": 20, "enter": False}, "press")
        self.apply([b])
        self.press(VK_F1)
        self.release(VK_F1)
        time.sleep(0.1)
        self.eng.stop_all()
        self.assertTrue(self.idle(b, 0.5))
        typed = [e for e in self.rec.take() if e[0] == "uni" and not e[2]]
        self.assertLess(len(typed), 20)

    # --- Dizi ---
    def test_sequence_press_repeat(self):
        steps = [{"t": "key", "vk": VK_C, "mods": [], "do": "tap"}, {"t": "wait", "ms": 5},
                 {"t": "mouse", "btn": "x1", "do": "click"}, {"t": "scroll", "amount": -2}]
        b = binding(VK_F1, {"type": "seq", "steps": steps, "repeat": 3}, "press")
        self.apply([b])
        self.press(VK_F1)
        self.release(VK_F1)
        self.assertTrue(self.idle(b))
        ev = self.rec.take()
        self.assertEqual(ev.count(("key", VK_C, False)), 3)
        self.assertEqual(ev.count(("mouse", 0x0080, 1)), 3)  # XDOWN, XBUTTON1
        self.assertEqual(ev.count(("mouse", 0x0800, (-240) & 0xFFFFFFFF)), 3)

    def test_sequence_hold_stop_releases_held_keys(self):
        steps = [{"t": "key", "vk": VK_C, "mods": [], "do": "down"},
                 {"t": "mouse", "btn": "left", "do": "down"}, {"t": "wait", "ms": 5000}]
        b = binding(VK_F1, {"type": "seq", "steps": steps, "repeat": 1}, "hold")
        self.apply([b])
        self.press(VK_F1)
        time.sleep(0.1)
        self.release(VK_F1)
        self.assertTrue(self.idle(b, 0.5), "uzun bekleme hemen kesilmeli")
        ev = self.rec.take()
        self.assertIn(("key", VK_C, True), ev, "basılı tuş bırakılmalı")
        self.assertIn(("mouse", 0x0004, 0), ev, "basılı sol tık bırakılmalı")

    # --- Tuş atama ---
    def test_remap_down_repeat_up(self):
        b = binding(VK_F1, {"type": "remap", "target": {"vk": VK_C, "mods": ["ctrl"]}}, "hold")
        self.apply([b])
        self.assertTrue(self.press(VK_F1))
        self.assertTrue(self.press(VK_F1))  # otomatik tekrar
        self.assertTrue(self.release(VK_F1))
        time.sleep(0.1)
        ev = self.rec.take()
        self.assertEqual(ev, [("key", VK_LCTRL, False), ("key", VK_C, False), ("key", VK_C, False),
                              ("key", VK_C, True), ("key", VK_LCTRL, True)])

    def test_disable_blocks_key(self):
        b = binding(0x5B, {"type": "disable"}, "hold")
        self.apply([b])
        self.assertTrue(self.press(0x5B))
        self.assertTrue(self.release(0x5B))
        self.assertEqual(self.rec.take(), [])

    # --- Eşleştirme ---
    def test_modifier_matching(self):
        plain = binding(VK_R, {"type": "disable"}, "hold", bid="plain")
        ctrl = binding(VK_R, {"type": "remap", "target": {"vk": VK_F3, "mods": []}}, "hold", mods=["ctrl"], bid="ctrl")
        self.apply([plain, ctrl])
        self.press(VK_LCTRL)
        self.press(VK_R)
        self.assertIs(self.eng.pressed[VK_R]["id"], "ctrl")
        self.release(VK_R)
        self.release(VK_LCTRL)
        self.press(VK_LSHIFT)
        self.press(VK_R)
        self.assertEqual(self.eng.pressed[VK_R]["id"], "plain", "Shift basılıyken değiştiricisiz atama çalışmalı")
        self.release(VK_R)
        self.release(VK_LSHIFT)

    def test_unbound_key_passes(self):
        self.apply([])
        self.assertFalse(self.press(VK_C))
        self.assertFalse(self.release(VK_C))

    def test_toggle_hotkey(self):
        b = binding(VK_R, {"type": "disable"}, "hold")
        self.apply([b])
        self.assertTrue(self.press(0x13))
        self.assertTrue(self.release(0x13))
        self.assertFalse(self.eng.enabled)
        self.assertFalse(self.press(VK_R), "kapalıyken atama çalışmamalı")
        self.release(VK_R)
        self.press(0x13)
        self.release(0x13)
        self.assertTrue(self.eng.enabled)
        self.assertTrue(self.press(VK_R))
        self.release(VK_R)

    # --- Yakalama ve kayıt ---
    def test_capture_combo(self):
        self.apply([])
        self.eng.set_capture(True)
        self.assertFalse(self.press(VK_LCTRL))
        self.assertTrue(self.press(VK_C), "yakalanan tuş uygulamaya gitmemeli")
        self.assertTrue(self.release(VK_C))
        self.release(VK_LCTRL)
        msgs = []
        while not self.eng.outbox.empty():
            msgs.append(self.eng.outbox.get())
        self.assertIn(("captured", {"vk": VK_C, "mods": ["ctrl"]}), msgs)
        self.assertFalse(self.eng.capturing)

    def test_capture_modifier_alone_and_escape(self):
        self.apply([])
        self.eng.set_capture(True)
        self.press(VK_LSHIFT)
        self.release(VK_LSHIFT)
        self.eng.set_capture(True)
        self.press(VK_ESC)
        self.release(VK_ESC)
        msgs = [m for m in iter_queue(self.eng.outbox) if m[0] == "captured"]
        self.assertEqual(msgs, [("captured", {"vk": VK_LSHIFT, "mods": []}), ("captured", None)])

    def test_recording(self):
        b = binding(VK_R, {"type": "disable"}, "hold")
        self.apply([b])
        self.eng.set_recording(True)
        self.assertFalse(self.press(VK_R), "kayıtta atamalar çalışmamalı")
        time.sleep(0.03)
        self.release(VK_R)
        self.eng.set_recording(False)
        rec = [m for m in iter_queue(self.eng.outbox) if m[0] == "recorded"][0][1]
        self.assertEqual(rec[0], {"t": "key", "vk": VK_R, "mods": [], "do": "down"})
        self.assertEqual(rec[1]["t"], "wait")
        self.assertGreaterEqual(rec[1]["ms"], 25)
        self.assertEqual(rec[2], {"t": "key", "vk": VK_R, "mods": [], "do": "up"})

    # --- Profil ---
    def test_auto_profile_switch(self):
        cfg = config.default_config()
        game = {"id": "oyun", "name": "Oyun", "apps": ["game.exe"],
                "bindings": [binding(VK_R, {"type": "disable"}, "hold")]}
        cfg["profiles"].append(game)
        self.eng.apply_config(config.validate(cfg))
        self.assertNotEqual(self.eng.profile_id, "oyun")
        self.eng.fg_exe = "game.exe"
        self.eng._select_profile()
        self.assertEqual(self.eng.profile_id, "oyun")
        self.assertTrue(self.press(VK_R))
        self.release(VK_R)


def iter_queue(q):
    while not q.empty():
        yield q.get()


class ConfigTest(unittest.TestCase):
    def test_default_valid(self):
        config.validate(config.default_config())

    def test_duplicate_trigger_rejected(self):
        a = binding(VK_R, {"type": "disable"}, "hold")
        with self.assertRaises(config.ConfigError):
            make_cfg([a, copy.deepcopy(a) | {"id": "b"}])

    def test_hotkey_conflict_rejected(self):
        with self.assertRaises(config.ConfigError):
            make_cfg([binding(0x13, {"type": "disable"}, "hold")])

    def test_left_click_trigger_rejected(self):
        with self.assertRaises(config.ConfigError):
            make_cfg([binding(1, {"type": "disable"}, "hold")])

    def test_bad_values_rejected(self):
        for action in ({"type": "click", "button": "left", "cps": 0},
                       {"type": "click", "button": "sol", "cps": 10},
                       {"type": "spam", "key": None, "rate": 5},
                       {"type": "launch", "target": "  ", "args": ""},
                       {"type": "seq", "steps": [{"t": "zıpla"}], "repeat": 1},
                       {"type": "nope"}):
            with self.assertRaises(config.ConfigError, msg=str(action)):
                make_cfg([binding(VK_R, action, "hold")])

    def test_invalid_mode_falls_back(self):
        cfg = make_cfg([binding(VK_R, {"type": "text", "text": "a"}, "toggle")])
        self.assertEqual(cfg["profiles"][0]["bindings"][0]["mode"], "press")


if __name__ == "__main__":
    unittest.main(verbosity=2)
