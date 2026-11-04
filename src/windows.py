"""Windows foreground checks, Unicode typing and configurable keyboard hotkeys."""
import ctypes
from ctypes import wintypes
import threading
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def foreground():
    return user32.GetForegroundWindow()


def window_pid(hwnd):
    process = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process))
    return process.value


def type_text(text, target, cancel=None):
    """Never activate another app. Unicode avoids German keyboard layout problems."""
    # Wait for released modifiers, especially in toggle mode.
    deadline = time.monotonic() + 2
    while any(user32.GetAsyncKeyState(k) & 0x8000 for k in (16, 17, 18, 91, 92)):
        if time.monotonic() >= deadline:
            raise RuntimeError("Eine Zusatztaste ist noch gedrückt. Text bitte manuell kopieren.")
        time.sleep(0.02)
    raw = text.encode("utf-16-le")
    units = [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw), 2)]
    for i in range(0, len(units), 32):
        if (cancel and cancel.is_set()) or foreground() != target:
            raise RuntimeError("Fenster gewechselt oder Einfügen abgebrochen. Text liegt im Verlauf; eventuell wurde ein Teil eingefügt.")
        batch = []
        for unit in units[i:i + 32]:
            batch.extend([INPUT(type=1, ki=KEYBDINPUT(0, unit, 4, 0, 0)),
                          INPUT(type=1, ki=KEYBDINPUT(0, unit, 6, 0, 0))])
        events = (INPUT * len(batch))(*batch)
        if user32.SendInput(len(events), events, ctypes.sizeof(INPUT)) != len(events):
            raise RuntimeError("Windows hat die Eingabe blockiert. Text bitte aus dem Verlauf kopieren.")
        time.sleep(0.002)


SPECIAL = {
    "space": "Leertaste", "pause": "Pause", "scroll_lock": "Rollen",
    "insert": "Einfg", "home": "Pos1", "end": "Ende",
    "page_up": "Bild auf", "page_down": "Bild ab", "caps_lock": "Feststelltaste",
}


def key_name(key):
    from pynput import keyboard
    groups = {"ctrl": (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r),
              "alt": (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr),
              "shift": (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r),
              "win": (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r)}
    for name, values in groups.items():
        if key in values:
            return name
    if isinstance(key, keyboard.KeyCode):
        if key.vk and 65 <= key.vk <= 90:
            return chr(key.vk).lower()
        if key.vk and 48 <= key.vk <= 57:
            return chr(key.vk)
        return (key.char or "").lower()
    return key.name


def label(keys):
    return " + ".join(SPECIAL.get(k, k.upper()) for k in sorted(keys, key=lambda k: (k not in {"ctrl", "alt", "shift", "win"}, k)))


def valid_hotkey(keys):
    modifiers = {"ctrl", "alt", "shift", "win"}
    if not keys or "esc" in keys or len(keys - modifiers) != 1:
        return False
    ordinary = next(iter(keys - modifiers))
    return ordinary in SPECIAL or (ordinary.startswith("f") and ordinary[1:].isdigit()) or bool(keys & modifiers)


class Hotkeys:
    def __init__(self, keys, press, release, escape, captured):
        from pynput import keyboard
        self.keys = set(keys)
        self.down = set()
        self.active = False
        self.capture = False
        self.enabled = True
        self.press, self.release, self.escape, self.captured = press, release, escape, captured
        self.lock = threading.RLock()
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)

    def on_press(self, key):
        name = key_name(key)
        with self.lock:
            self.down.add(name)
            if self.capture:
                if name == "esc":
                    self.capture = False
                    self.captured([])
                elif name not in {"ctrl", "alt", "shift", "win"}:
                    keys = set(self.down)
                    if valid_hotkey(keys):
                        self.capture = False
                        self.captured(sorted(keys))
                return
            if name == "esc":
                self.escape()
            if self.enabled and not self.active and self.keys <= self.down:
                self.active = True
                self.press()

    def on_release(self, key):
        with self.lock:
            self.down.discard(key_name(key))
            if self.active and not self.keys <= self.down:
                self.active = False
                self.release()

    def set_keys(self, keys):
        with self.lock:
            self.keys = set(keys)
            self.active = False
            self.down.clear()

    def start(self):
        self.listener.start()

    def stop(self):
        self.listener.stop()
