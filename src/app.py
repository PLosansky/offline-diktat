from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal, QTimer, Qt, QLockFile
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap, QTextCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QTextEdit, QListWidget, QSplitter,
    QFrame, QDialog, QComboBox, QCheckBox, QSpinBox, QFormLayout,
    QFileDialog, QMessageBox, QProgressBar, QStackedWidget, QSystemTrayIcon, QMenu, QScrollArea)

import engine
import windows
from about import AboutDialog
from storage import prepare_user_directory
from settings_ui import AdvancedSettings
from llm import LocalLLM
from review import Review
from speech_import import SpeechImport
import model_store
import text_tools

VERSION = "1.1.0"
DISPLAY_VERSION = "1.1.0"
APP_NAME = "Offline-Diktat"
BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
DATA = Path(os.environ.get("DICTATE_DATA_DIR", str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DictateOffline")))
DEFAULT_MODEL = BASE / "models" if (BASE / "models" / "tokens.txt").exists() else DATA / "models"
DEFAULT = {"model": str(DEFAULT_MODEL), "device_name": "", "device_host": "", "keys": ["f9"],
           "toggle": False, "threads": min(4, os.cpu_count() or 1), "setup": False,
           "persist": False, "autostart": False, "trailing_space": True,
           "output_mode": "direct", "notifications": "Alle", "history_limit": 20,
           "history_days": 0, "draft_protection": False, "close_to_tray": True,
           "dictionary": "", "templates": "", "llm_enabled": False, "llm_model": "",
           "llm_runtime": "", "llm_threads": min(4, os.cpu_count() or 1),
           "llm_context": 4096, "llm_keep_loaded": False, "known_models": []}

STYLE = """
QWidget { background: #111922; color: #e8edf2; font-family: 'Segoe UI'; font-size: 14px; }
QMainWindow, QDialog { background: #111922; }
QLabel#title { font-size: 30px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #9eafbf; }
QLabel#status { font-size: 21px; font-weight: 600; color: #6ce0c1; }
QFrame#card { background: #1b2632; border: 1px solid #2d3b49; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QPushButton { background: #263646; border: 1px solid #394b5c; border-radius: 7px; padding: 9px 16px; }
QPushButton:hover { background: #344b60; }
QPushButton:disabled { color: #647789; background: #1b2632; }
QPushButton#primary { background: #6ce0c1; color: #0b2721; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #91ecd4; }
QTextEdit, QListWidget, QComboBox, QSpinBox, QLineEdit { background: #17222d; border: 1px solid #344553; border-radius: 7px; padding: 8px; }
QTextEdit { font-size: 16px; selection-background-color: #326a61; }
QListWidget::item { padding: 12px 6px; border-bottom: 1px solid #263644; }
QListWidget::item:selected { background: #284b49; color: #b6f5e3; border-radius: 4px; }
QProgressBar { border: none; background: #263646; border-radius: 4px; height: 9px; text-align: center; }
QProgressBar::chunk { background: #6ce0c1; border-radius: 4px; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QToolTip { background: #263646; color: #ffffff; border: 1px solid #6ce0c1; }
QStatusBar { background: #17222d; border-top: 1px solid #2d3b49; padding: 5px 18px; }
QStatusBar QLabel { background: transparent; color: #9eafbf; font-size: 12px; }
QStatusBar::item { border: none; }
QTabWidget::pane { border: 1px solid #344553; border-radius: 7px; }
QTabBar::tab { background: #1b2632; padding: 10px 18px; }
QTabBar::tab:selected { background: #284b49; color: #b6f5e3; }
"""


def text_label(text, name="", wrap=False):
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def button(text, callback, primary=False):
    obj = QPushButton(text.replace("&", "&&"))
    if primary:
        obj.setObjectName("primary")
    obj.clicked.connect(callback)
    return obj


def make_icon(color="#6ce0c1"):
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#17222d"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 64, 64, 15, 15)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(25, 12, 14, 28, 7, 7)
    from PySide6.QtGui import QPen
    painter.setPen(QPen(QColor(color), 4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(18, 23, 28, 24, 180 * 16, 180 * 16)
    painter.drawLine(32, 47, 32, 54)
    painter.drawLine(23, 54, 41, 54)
    painter.end()
    return QIcon(pix)


class Tasks(QObject):
    finished = Signal(int, object, object)
    progress = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.callbacks = {}
        self.sequence = 0
        self.finished.connect(self.deliver)

    def run(self, function, callback):
        self.sequence += 1
        number = self.sequence
        self.callbacks[number] = callback
        def work():
            try:
                result = function()
                self.finished.emit(number, result, None)
            except Exception as exc:
                self.finished.emit(number, None, exc)
        threading.Thread(target=work, daemon=True).start()

    def deliver(self, number, result, error):
        callback = self.callbacks.pop(number, None)
        if callback:
            callback(result, error)


class Events(QObject):
    pressed = Signal()
    released = Signal()
    escape = Signal()
    captured = Signal(object)


class Setup(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.cfg = dict(owner.cfg)
        self.cfg["keys"] = list(owner.cfg["keys"])
        self.loaded = owner.recognizer
        self.loaded_path = owner.cfg["model"] if self.loaded else None
        self.setWindowTitle("Offline-Diktat · Einrichtungsassistent")
        self.resize(720, 640)
        self.tasks = Tasks(self)
        self.tasks.progress.connect(self.progress_update)
        self.cancel_event = threading.Event()
        self.busy = False
        self.meter_rec = None
        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self.update_meter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(text_label("Deine Stimme. Dein Rechner.", "title"))
        self.steps = text_label("", "subtitle")
        layout.addWidget(self.steps)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.model_page()
        self.audio_page()
        self.options_page()
        self.feedback = text_label("", "muted", True)
        layout.addWidget(self.feedback)
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        row = QHBoxLayout()
        self.back = button("Zurück", self.previous)
        self.next = button("Weiter", self.advance, True)
        self.cancel_button = button("Abbrechen", self.reject)
        row.addWidget(self.cancel_button)
        row.addStretch()
        row.addWidget(self.back)
        row.addWidget(self.next)
        layout.addLayout(row)
        self.owner.events.captured.connect(self.captured)
        self.update_step()
        if not owner.testing and not self.loaded and Path(self.cfg["model"]).exists():
            self.verify()

    def new_page(self):
        page = QWidget()
        self.pages.addWidget(page)
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 5, 0, 5)
        box.setSpacing(14)
        return box

    def model_page(self):
        box = self.new_page()
        box.addWidget(text_label("1 · Sprachmodell auswählen", "status"))
        box.addWidget(text_label("Empfehlung: Parakeet DE erkennt Sprache ausschließlich auf deiner CPU. "
            "Der einmalige Download umfasst rund 671 MB. Danach ist keine Verbindung nötig.", wrap=True))
        self.path_label = text_label(self.cfg["model"], "muted", True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.path_label)
        self.model_choices = QComboBox()
        self.model_choices.addItem("Modell auswählen …", None)
        for name, path in model_store.discover_speech([BASE / "models", DATA / "models", DATA / "model-profiles", self.cfg["model"], *self.cfg["known_models"]]):
            self.model_choices.addItem(name + " · " + path, path)
        self.model_choices.currentIndexChanged.connect(self.select_model)
        box.addWidget(self.model_choices)
        self.download_button = button("Modell herunterladen", self.download, True)
        self.import_button = button("Vorhandenen Modellordner auswählen …", self.choose_model)
        self.verify_button = button("Diesen Ordner prüfen & Modell laden", self.verify)
        box.addWidget(self.download_button)
        box.addWidget(self.import_button)
        box.addWidget(self.verify_button)
        box.addWidget(text_label("Auch von USB möglich. Für andere NeMo-/Whisper-ONNX-Modelle hilft ein Importdialog "
            "beim Zuordnen der Dateien. Die Dateien bleiben am ausgewählten Ort.", "muted", True))
        box.addWidget(text_label("Modell: primeline / NVIDIA · ONNX: flozen1981 · CC BY 4.0", "muted", True))
        box.addStretch()

    def audio_page(self):
        box = self.new_page()
        box.addWidget(text_label("2 · Mikrofon auswählen", "status"))
        box.addWidget(text_label("Wähle dein Mikrofon und prüfe kurz den Ausschlag beim Sprechen.", wrap=True))
        self.devices = QComboBox()
        self.refresh_devices()
        box.addWidget(self.devices)
        self.refresh_button = button("Geräte neu suchen", self.refresh_devices)
        box.addWidget(self.refresh_button)
        self.test_button = button("Mikrofon testen", self.test_mic, True)
        box.addWidget(self.test_button)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setFormat("Mikrofonpegel")
        box.addWidget(self.level)
        box.addWidget(text_label("Der Test endet nach 15 Sekunden. Die Aufnahme wird verworfen.", "muted", True))
        box.addStretch()

    def options_page(self):
        box = self.new_page()
        box.addWidget(text_label("3 · Bedienung festlegen", "status"))
        self.key_button = button(windows.label(self.cfg["keys"]) + " · ändern", self.capture)
        box.addWidget(self.key_button)
        box.addWidget(text_label("Funktionstaste oder Kombination wie STRG + ALT + D. "
            "ESC bleibt zum Abbrechen reserviert. Wähle eine Taste, die deine anderen Programme nicht benötigen.", "muted", True))
        self.toggle_box = QCheckBox("Einmal drücken zum Starten, erneut drücken zum Stoppen")
        self.toggle_box.setChecked(self.cfg["toggle"])
        box.addWidget(self.toggle_box)
        box.addWidget(text_label("Ausgeschaltet: Taste während des Sprechens gedrückt halten.", "muted"))
        self.trailing_space_box = QCheckBox("Leerzeichen nach jedem Diktat")
        self.trailing_space_box.setChecked(self.cfg["trailing_space"])
        self.trailing_space_box.setToolTip("Fügt nach jedem vollständigen Diktat genau ein abschließendes Leerzeichen ein – bei kurzen und langen Aufnahmen.")
        box.addWidget(self.trailing_space_box)
        form = QFormLayout()
        self.threads = QSpinBox()
        self.threads.setRange(1, max(1, os.cpu_count() or 1))
        self.threads.setValue(self.cfg["threads"])
        form.addRow("CPU-Threads", self.threads)
        box.addLayout(form)
        self.persist_box = QCheckBox("Die letzten 20 Texte auf diesem Rechner dauerhaft speichern")
        self.persist_box.setChecked(self.cfg["persist"])
        box.addWidget(self.persist_box)
        self.auto_box = QCheckBox("Offline-Diktat bei der Windows-Anmeldung starten")
        self.auto_box.setChecked(self.cfg["autostart"])
        self.auto_box.setEnabled(bool(getattr(sys, "frozen", False)))
        box.addWidget(self.auto_box)
        box.addStretch()

    def refresh_devices(self):
        import sounddevice as sd
        self.devices.clear()
        self.devices.addItem("Windows-Standardmikrofon", ("", ""))
        try:
            hosts = sd.query_hostapis()
            for dev in sd.query_devices():
                if dev["max_input_channels"] > 0:
                    host = hosts[dev["hostapi"]]["name"]
                    value = (dev["name"], host)
                    self.devices.addItem(f"{dev['name']} · {host}", value)
                    if value == (self.cfg["device_name"], self.cfg["device_host"]):
                        self.devices.setCurrentIndex(self.devices.count() - 1)
        except Exception as exc:
            self.devices.setToolTip(str(exc))

    def test_mic(self):
        if self.meter_rec:
            self.stop_meter()
            return
        try:
            name, host = self.devices.currentData()
            self.meter_rec = engine.Recorder(resolve_device(name, host), seconds_limit=15)
            self.meter_rec.start()
            self.test_button.setText("Test beenden")
            self.devices.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.meter_timer.start(80)
        except Exception as exc:
            self.meter_rec = None
            self.feedback.setText(f"Mikrofon nicht verfügbar: {exc}")

    def update_meter(self):
        if self.meter_rec:
            self.level.setValue(min(100, int(self.meter_rec.peak * 250)))
            if self.meter_rec.full:
                self.stop_meter()

    def stop_meter(self):
        self.meter_timer.stop()
        if self.meter_rec:
            try:
                self.meter_rec.stop()
            except Exception:
                pass
            self.meter_rec = None
        self.test_button.setText("Mikrofon testen")
        self.devices.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.level.setValue(0)

    def progress_update(self, amount, message):
        self.progress_bar.setValue(amount)
        self.feedback.setText(message)

    def choose_model(self):
        folder = QFileDialog.getExistingDirectory(self, "Sprachmodellordner auswählen", self.cfg["model"])
        if folder:
            if not (Path(folder) / "speech-model.json").exists() and not all((Path(folder) / name).is_file() for name in engine.FILES):
                dialog = SpeechImport(self, folder, DATA)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                folder = dialog.profile_path
            self.cfg["model"] = folder
            self.path_label.setText(folder)
            self.verify()

    def select_model(self):
        folder = self.model_choices.currentData()
        if folder:
            self.cfg["model"] = folder
            self.path_label.setText(folder)
            self.verify()

    def download(self):
        # Never overwrite a manually imported model when returning to the recommendation.
        self.cfg["model"] = str(DATA / "models" / "parakeet-de-recommended")
        self.path_label.setText(self.cfg["model"])
        self.load_model(True)

    def verify(self):
        self.load_model(False)

    def load_model(self, download):
        self.busy = True
        self.loaded_path = None
        self.cancel_event.clear()
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.update_step()
        folder = self.cfg["model"]
        threads = self.threads.value()
        def work():
            if download:
                engine.download_model(folder, self.tasks.progress.emit, self.cancel_event)
            else:
                engine.validate_model(folder, self.tasks.progress.emit, self.cancel_event)
            engine.check_cancel(self.cancel_event)
            self.tasks.progress.emit(100, "Modell wird auf der CPU geladen …")
            rec = engine.Recognizer(folder, threads)
            engine.check_cancel(self.cancel_event)
            return rec
        self.tasks.run(work, self.model_ready)

    def model_ready(self, result, error):
        self.busy = False
        if error:
            self.feedback.setText(str(error))
        else:
            self.loaded = result
            self.loaded_path = self.cfg["model"]
            self.cfg["threads"] = self.threads.value()
            self.cfg["known_models"] = list(dict.fromkeys([*self.cfg["known_models"], self.cfg["model"]]))
            self.feedback.setText("✓ Modell geprüft und geladen. Weiter zum Mikrofon.")
        self.update_step()

    def capture(self):
        self.owner.hotkeys.capture = True
        self.owner.hotkeys.down.clear()
        self.key_button.setText("Jetzt Taste / Kombination drücken … ESC bricht ab")

    def captured(self, keys):
        if keys:
            self.cfg["keys"] = list(keys)
        self.key_button.setText(windows.label(self.cfg["keys"]) + " · ändern")

    def update_step(self):
        index = self.pages.currentIndex()
        self.steps.setText(f"Schritt {index + 1} von 3 · Offline • CPU")
        self.back.setEnabled(index > 0 and not self.busy)
        self.next.setText("Fertig" if index == 2 else "Weiter")
        self.next.setEnabled(not self.busy and (index != 0 or self.loaded_path == self.cfg["model"]))
        for widget in (self.download_button, self.import_button, self.verify_button, self.model_choices):
            widget.setEnabled(not self.busy)
        self.cancel_button.setText("Vorgang abbrechen" if self.busy else "Abbrechen")

    def previous(self):
        self.stop_meter()
        self.pages.setCurrentIndex(self.pages.currentIndex() - 1)
        self.feedback.setText("")
        self.update_step()

    def advance(self):
        self.stop_meter()
        index = self.pages.currentIndex()
        if index < 2:
            self.pages.setCurrentIndex(index + 1)
            self.feedback.setText("")
            self.update_step()
            return
        self.owner.hotkeys.capture = False
        self.cfg.update(toggle=self.toggle_box.isChecked(), persist=self.persist_box.isChecked(),
                        autostart=self.auto_box.isChecked(), trailing_space=self.trailing_space_box.isChecked(), setup=True)
        self.cfg["device_name"], self.cfg["device_host"] = self.devices.currentData()
        if self.threads.value() != self.cfg["threads"]:
            self.cfg["threads"] = self.threads.value()
            self.loaded = None  # reload with requested thread count after closing
        self.accept()

    def reject(self):
        if self.busy:
            self.cancel_event.set()
            self.feedback.setText("Abbruch angefordert. Ein laufender Ladevorgang wird zunächst beendet …")
            return
        self.stop_meter()
        self.owner.hotkeys.capture = False
        super().reject()


class Settings(AdvancedSettings, Setup):
    def __init__(self, owner):
        self.advanced_ready = False
        self.optional_kind = None
        self.data_root = DATA
        super().__init__(owner)
        self.setWindowTitle("Offline-Diktat · Einstellungen")
        self.resize(920, 850)
        self.add_advanced_pages()
        self.navigation = QComboBox()
        self.navigation.addItems(["Sprachmodelle", "Mikrofon", "Tastenkürzel und Bedienung",
                                  "Textausgabe und Verlauf", "Text-KI", "Wörterbuch und Vorlagen"])
        self.navigation.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.layout().insertWidget(2, self.navigation)
        # Long settings pages remain reachable on small office displays.
        self.layout().removeWidget(self.pages)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.pages)
        self.layout().insertWidget(3, self.scroll, 1)
        self.steps.setText("Einstellungen jederzeit anpassen · Einrichtungsassistent im Menü verfügbar")
        self.back.hide()
        self.persist_box.setText("Verlauf dauerhaft lokal speichern (Umfang unter Textausgabe)")
        self.advanced_ready = True
        self.update_step()

    def update_step(self):
        if not self.advanced_ready:
            return super().update_step()
        self.next.setText("Speichern")
        self.next.setEnabled(not self.busy and self.loaded_path == self.cfg["model"])
        self.navigation.setEnabled(not self.busy)
        self.pages.setEnabled(not self.busy)
        self.cancel_button.setText("Vorgang abbrechen" if self.busy else "Abbrechen")

    def advance(self):
        try:
            self.save_advanced()
        except ValueError as exc:
            self.feedback.setText(str(exc))
            return
        self.pages.setCurrentIndex(2)
        super().advance()

    def reject(self):
        if self.busy and self.optional_kind == "benchmark":
            self.cancel_event.set()
            self.owner.llm.stop()
        super().reject()


def resolve_device(name, host):
    if not name:
        return None
    import sounddevice as sd
    hosts = sd.query_hostapis()
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and dev["name"] == name and hosts[dev["hostapi"]]["name"] == host:
            return index
    raise RuntimeError("Das gespeicherte Mikrofon ist nicht angeschlossen. Bitte in den Einstellungen neu auswählen.")


def set_autostart(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "DictateOffline", 0, winreg.REG_SZ, f'"{sys.executable}" --minimized')
        else:
            try:
                winreg.DeleteValue(key, "DictateOffline")
            except FileNotFoundError:
                pass


class Main(QMainWindow):
    def __init__(self, testing=False):
        super().__init__()
        self.testing = testing
        self.cfg = engine.load_json(DATA / "settings.json", DEFAULT)
        if not self.cfg["llm_model"]:
            for root in (DATA / "text-models", BASE / "text-models", BASE / "models"):
                for spec in model_store.LLM_MODELS:
                    candidate = root / spec["file"]
                    if candidate.is_file():
                        self.cfg["llm_model"] = str(candidate)
                        break
                if self.cfg["llm_model"]:
                    break
        if not self.cfg["llm_runtime"]:
            for root in (DATA / "runtime", BASE / "runtime"):
                if root.is_dir():
                    matches = list(root.rglob("llama-server.exe"))
                    if matches:
                        self.cfg["llm_runtime"] = str(matches[0])
                        break
        if not windows.valid_hotkey(set(self.cfg["keys"])):
            self.cfg["keys"] = ["f9"]
        self.recognizer = None
        self.llm = LocalLLM()
        self.recorder = None
        self.state = "idle"
        self.cancel_event = threading.Event()
        self.target = None
        self.capture_editor = False
        self.button_recording = False
        self.append_recording = False
        self.command_recording = False
        self.current_profile = "Korrigieren"
        self.active_review = None
        self.stop_requested = False
        self.quit_requested = False
        self.histories = []
        self.history_index = -1
        self.tasks = Tasks(self)
        self.tasks.progress.connect(self.on_progress)
        self.events = Events()
        self.events.pressed.connect(self.pressed)
        self.events.released.connect(self.released)
        self.events.escape.connect(self.cancel)
        self.hotkeys = windows.Hotkeys(self.cfg["keys"], self.events.pressed.emit,
                                      self.events.released.emit, self.events.escape.emit,
                                      self.events.captured.emit)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1020, 740)
        self.setMinimumSize(820, 620)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 22)
        layout.setSpacing(18)
        header = QHBoxLayout()
        title = QVBoxLayout()
        title.addWidget(text_label(APP_NAME, "title"))
        title.addWidget(text_label("Deine Stimme wird Text. Alles bleibt auf deinem Rechner.", "subtitle"))
        header.addLayout(title)
        header.addStretch()
        header_actions = QVBoxLayout()
        self.settings_button = button("Einstellungen", self.settings)
        self.about_button = button("Über Offline-Diktat", self.show_about)
        header_actions.addWidget(self.settings_button)
        header_actions.addWidget(self.about_button)
        header.addLayout(header_actions)
        layout.addLayout(header)
        card = QFrame()
        card.setObjectName("card")
        card_box = QVBoxLayout(card)
        card_box.setContentsMargins(20, 18, 20, 18)
        self.status = text_label("Einrichtung erforderlich", "status")
        self.hint = text_label("", "muted", True)
        self.elapsed = text_label("Offline · CPU", "muted")
        card_box.addWidget(self.status)
        card_box.addWidget(self.hint)
        card_box.addWidget(self.elapsed)
        record_row = QHBoxLayout()
        self.record_button = button("Aufnahme starten", self.record_clicked, True)
        self.continue_button = button("Weiterdiktieren", lambda: self.record_clicked(append=True))
        self.new_button = button("Neuer Text", self.new_text)
        self.command_box = QCheckBox("Nächste Aufnahme als Sprachbefehl")
        self.command_box.setToolTip("Nur im Editor: Neuer Absatz · Letzten Satz löschen · Rückgängig · Stil professionell · "
                                    "Bitte formuliere den vorherigen Abschnitt professioneller")
        for widget in (self.record_button, self.continue_button, self.new_button, self.command_box):
            record_row.addWidget(widget)
        card_box.addLayout(record_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        card_box.addWidget(self.progress)
        layout.addWidget(card)
        self.feedback = text_label("", "muted", True)
        layout.addWidget(self.feedback)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 12, 0)
        left_box.addWidget(text_label("LETZTE DIKTATE", "muted"))
        self.history = QListWidget()
        self.history.currentRowChanged.connect(self.select_history)
        left_box.addWidget(self.history)
        self.clear_button = button("Verlauf löschen", self.clear_history)
        left_box.addWidget(self.clear_button)
        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.addWidget(text_label("TEXT BEARBEITEN", "muted"))
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText("Dein nächstes Diktat erscheint hier.\n\nDu kannst den Text korrigieren und anschließend kopieren.")
        self.editor.textChanged.connect(self.edited)
        right_box.addWidget(self.editor)
        editing = QHBoxLayout()
        self.ai_button = button("Mit KI bearbeiten …", self.review_text)
        self.undo_button = button("Rückgängig", self.editor.undo)
        self.original_button = button("Original wiederherstellen", self.restore_original)
        editing.addWidget(self.ai_button)
        editing.addWidget(self.undo_button)
        editing.addWidget(self.original_button)
        right_box.addLayout(editing)
        actions = QHBoxLayout()
        actions.addWidget(button("Text kopieren", self.copy_text, True))
        actions.addWidget(button("Als Textdatei speichern …", self.export_text))
        self.insert_button = button("Einfügen in 3 Sekunden", self.delayed_insert)
        actions.addWidget(self.insert_button)
        actions.addStretch()
        right_box.addLayout(actions)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([260, 680])
        layout.addWidget(split, 1)
        footer = QHBoxLayout()
        self.privacy = text_label("Verlauf nur für diese Sitzung · Keine Audio-Dateien", "muted", True)
        footer.addWidget(self.privacy)
        footer.addStretch()
        footer.addWidget(text_label("ESC · Abbrechen", "muted"))
        layout.addLayout(footer)
        self.branding = QLabel('© 2026 <a href="http://Losansky.it" style="color: #6ce0c1; text-decoration: none;">Losansky.IT</a>')
        self.branding.setOpenExternalLinks(True)
        self.branding.setToolTip("Website von Losansky.IT öffnen")
        self.branding.setContentsMargins(22, 3, 0, 3)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().setMinimumHeight(32)
        self.statusBar().addWidget(self.branding)
        self.version_label = QLabel(f"Version {DISPLAY_VERSION}")
        self.version_label.setContentsMargins(0, 3, 22, 3)
        self.statusBar().addPermanentWidget(self.version_label)
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        for title, callback in (("Offline-Diktat öffnen", self.show_window), ("Einstellungen", self.settings),
                                ("Einrichtungsassistent", self.wizard),
                                ("Über Offline-Diktat", self.show_about),
                                ("Aktuellen Vorgang abbrechen", self.cancel), ("Beenden", self.quit)):
            action = QAction(title, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_history)
        if self.cfg["persist"]:
            content = engine.load_json(DATA / "history.json", {"items": []})
            self.histories = [x for x in content["items"] if isinstance(x, dict) and isinstance(x.get("text"), str) and isinstance(x.get("time"), str)][:self.cfg["history_limit"]]
            self.prune_history()
            self.refresh_history()
        if self.cfg["draft_protection"]:
            draft = engine.load_json(DATA / "draft.json", {})
            if isinstance(draft.get("text"), str) and draft["text"]:
                match = next((i for i, item in enumerate(self.histories)
                              if item["text"] == draft["text"] and item.get("original") == draft.get("original")), None)
                if match is None:
                    self.add_history(draft["text"], draft.get("original", draft["text"]))
                else:
                    self.history.setCurrentRow(match)
        self.update_hint()
        if not testing:
            self.tray.show()
            try:
                self.hotkeys.start()
            except Exception as exc:
                self.feedback.setText(f"Tastenkürzel konnte nicht gestartet werden: {exc}")
            QTimer.singleShot(200, self.initialize)

    def initialize(self):
        # Keep an explicitly enabled autostart pointing at the renamed executable.
        if self.cfg["autostart"] and getattr(sys, "frozen", False):
            try:
                set_autostart(True)
            except OSError:
                self.notify("Autostart konnte nicht aktualisiert werden. Bitte in den Einstellungen erneut aktivieren.")
        if self.cfg["setup"]:
            self.load_engine()
        else:
            self.wizard()

    def update_hint(self):
        key = windows.label(self.cfg["keys"])
        self.hint.setText(f"{key} drücken → sprechen → {key} erneut drücken" if self.cfg["toggle"] else f"{key} gedrückt halten → sprechen → loslassen")
        self.privacy.setText((f"Bis zu {self.cfg['history_limit']} Texte lokal gespeichert" if self.cfg["persist"] else "Verlauf nur für diese Sitzung") +
                            (" · Entwurfsschutz aktiv" if self.cfg["draft_protection"] else "") + " · Keine Audio-Dateien")
        self.ai_button.setEnabled(self.cfg["llm_enabled"] and self.state == "idle")

    def change_state(self, state, text):
        self.state = state
        self.status.setText(text)
        self.settings_button.setEnabled(state == "idle")
        self.about_button.setEnabled(state == "idle")
        self.record_button.setEnabled(state in {"idle", "recording"})
        self.record_button.setText("Aufnahme stoppen" if state == "recording" else "Aufnahme starten")
        for widget in (self.continue_button, self.new_button, self.command_box, self.editor,
                       self.history, self.clear_button, self.undo_button, self.original_button, self.insert_button):
            widget.setEnabled(state == "idle")
        self.ai_button.setEnabled(state == "idle" and self.cfg["llm_enabled"])
        color = "#ff837d" if state == "recording" else "#f0c76b" if state != "idle" else "#6ce0c1"
        self.tray.setIcon(make_icon(color))
        self.tray.setToolTip(APP_NAME + " · " + text)
        self.progress.setVisible(state in {"loading", "processing", "typing"})

    def show_about(self):
        if self.state != "idle":
            self.notify("Bitte den laufenden Vorgang zuerst beenden.")
            return
        self.hotkeys.enabled = False
        self.state = "about"
        self.tray.contextMenu().setEnabled(False)
        dialog = AboutDialog(self, DISPLAY_VERSION)
        try:
            dialog.exec()
        finally:
            self.state = "idle"
            self.hotkeys.enabled = True
            self.tray.contextMenu().setEnabled(True)
            dialog.deleteLater()

    def wizard(self):
        self.settings(wizard=True)

    def settings(self, checked=False, wizard=False):
        if self.state != "idle":
            self.notify("Bitte den laufenden Vorgang zuerst beenden.")
            return
        self.hotkeys.enabled = False
        self.state = "settings"
        self.tray.contextMenu().setEnabled(False)
        dialog = Setup(self) if wizard else Settings(self)
        old_autostart = self.cfg["autostart"]
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.tray.contextMenu().setEnabled(True)
        self.state = "idle"
        if accepted:
            new_cfg = dialog.cfg
            save_errors = []
            try:
                engine.save_json(DATA / "settings.json", new_cfg)
            except OSError as exc:
                save_errors.append(f"Die Einstellungen gelten nur für diese Sitzung und konnten nicht gespeichert werden.\n\nDatei: {DATA / 'settings.json'}\n\n{exc}")
            try:
                if new_cfg["autostart"] != old_autostart:
                    set_autostart(new_cfg["autostart"])
            except OSError as exc:
                save_errors.append(f"Der Windows-Autostart konnte nicht geändert werden:\n{exc}")
            self.cfg = new_cfg
            self.llm.stop()
            self.recognizer = dialog.loaded
            self.hotkeys.set_keys(self.cfg["keys"])
            self.save_history()
            self.update_hint()
            if not self.recognizer:
                self.load_engine()
            else:
                self.change_state("idle", "Bereit zum Diktieren")
                self.feedback.setText("Öffne ein Eingabefeld in deiner Zielanwendung und nutze dein Tastenkürzel.")
            if save_errors:
                QMessageBox.warning(self, APP_NAME, "\n\n".join(save_errors))
        self.hotkeys.capture = False
        self.hotkeys.enabled = True
        self.events.captured.disconnect(dialog.captured)
        dialog.deleteLater()

    def load_engine(self):
        self.change_state("loading", "Offline-Modell wird geladen …")
        self.cancel_event.clear()
        def work():
            engine.validate_model(self.cfg["model"], self.tasks.progress.emit, self.cancel_event)
            return engine.Recognizer(self.cfg["model"], self.cfg["threads"])
        self.tasks.run(work, self.engine_ready)

    def engine_ready(self, result, error):
        if self.quit_requested:
            self.finish_quit()
            return
        if error or self.cancel_event.is_set():
            self.change_state("idle", "Modell nicht bereit")
            self.notify(str(error) if error else "Laden abgebrochen.", error=bool(error))
        else:
            self.recognizer = result
            self.change_state("idle", "Bereit zum Diktieren")

    def pressed(self):
        if not self.hotkeys.enabled:
            return
        if self.state == "recording" and self.cfg["toggle"]:
            self.stop_recording()
        elif self.state == "idle":
            self.start_recording()

    def released(self):
        if self.cfg["toggle"] or self.button_recording:
            return
        if self.state == "starting":
            self.stop_requested = True
        elif self.state == "recording":
            self.stop_recording()

    def record_clicked(self, checked=False, append=False):
        if self.state == "recording":
            self.stop_recording()
        elif self.state == "idle":
            self.start_recording(from_button=True, append=append)

    def start_recording(self, from_button=False, append=False):
        if not self.recognizer:
            self.notify("Bitte zuerst das Offline-Modell in der Einrichtung laden.")
            return
        self.target = windows.foreground()
        if windows.window_pid(self.target) == os.getpid():
            self.target = None
        self.button_recording = from_button
        self.command_recording = self.command_box.isChecked()
        self.command_box.setChecked(False)
        self.capture_editor = from_button or not self.target or self.cfg["output_mode"] == "editor" or self.command_recording
        self.append_recording = append
        self.cancel_event.clear()
        self.stop_requested = False
        self.feedback.setText("")
        self.change_state("starting", "Mikrofon wird geöffnet …")
        def work():
            rec = engine.Recorder(resolve_device(self.cfg["device_name"], self.cfg["device_host"]))
            rec.start()
            return rec
        self.tasks.run(work, self.recording_started)

    def recording_started(self, recorder, error):
        if error:
            self.change_state("idle", "Mikrofon nicht verfügbar")
            self.notify(str(error), error=True)
            if self.quit_requested:
                self.finish_quit()
            return
        self.recorder = recorder
        self.change_state("recording", "Aufnahme läuft")
        if self.cancel_event.is_set() or self.stop_requested:
            self.stop_recording()

    def tick(self):
        if self.state == "idle":
            self.llm.idle(5)
        if self.state == "recording" and self.recorder:
            seconds = self.recorder.count // engine.RATE
            self.elapsed.setText(f"● {seconds // 60:02d}:{seconds % 60:02d} · Pegel {min(100, int(self.recorder.peak * 250))}% · Max. 60 Minuten")
            if self.recorder.full:
                self.feedback.setText("Die Grenze von 60 Minuten ist erreicht. Die Aufnahme wird jetzt verarbeitet.")
                self.stop_recording()

    def stop_recording(self):
        recorder = self.recorder
        if not recorder:
            return
        self.recorder = None
        self.change_state("processing", "Sprache wird erkannt …")
        self.progress.setValue(0)
        def work():
            audio = recorder.stop()
            engine.check_cancel(self.cancel_event)
            if not len(audio):
                raise RuntimeError("Keine Aufnahme erhalten. Bitte das Mikrofon prüfen.")
            text = self.recognizer.transcribe(audio, self.tasks.progress.emit, self.cancel_event)
            return text, recorder.overflow
        self.tasks.run(work, self.transcribed)

    def transcribed(self, result, error):
        if self.quit_requested:
            self.finish_quit()
            return
        if error or self.cancel_event.is_set():
            self.change_state("idle", "Bereit zum Diktieren")
            self.feedback.setText("Aufnahme verworfen." if isinstance(error, engine.Cancelled) or self.cancel_event.is_set() else str(error))
            return
        text, overflow = result
        if self.command_recording:
            self.command_recording = False
            self.change_state("idle", "Sprachbefehl verarbeitet")
            if overflow:
                self.feedback.setText("Audioblöcke verloren: Sprachbefehl wurde nicht ausgeführt.")
            else:
                self.apply_command(text)
            return
        original = text
        text = text_tools.replacements(text, self.cfg["dictionary"])
        text = engine.format_dictation(text, self.cfg["trailing_space"])
        if not text:
            self.change_state("idle", "Keine Sprache erkannt")
            self.notify("Kein Text erkannt. Mikrofonpegel prüfen und erneut sprechen.")
            return
        if self.append_recording and self.capture_editor and 0 <= self.history_index < len(self.histories):
            item = self.histories[self.history_index]
            item["original"] = item.get("original", item["text"]).rstrip() + " " + original
            existing = self.editor.toPlainText()
            self.replace_editor(existing + (" " if existing and not existing[-1].isspace() else "") + text)
        else:
            self.add_history(text, original)
        self.elapsed.setText("Offline · CPU")
        if overflow:
            self.change_state("idle", "Text bitte prüfen")
            self.notify("Bei der Aufnahme gingen Audioblöcke verloren. Der Text liegt zur Prüfung im Verlauf.", error=True)
            return
        if self.capture_editor:
            self.change_state("idle", "Text im Editor bereit")
            self.feedback.setText("Text bearbeiten, mit KI überarbeiten oder kopieren.")
            return
        if not self.target or windows.foreground() != self.target:
            self.change_state("idle", "Text im Verlauf bereit")
            self.notify("Ziel gewechselt oder Offline-Diktat war aktiv. Text bitte aus dem Verlauf kopieren.")
            return
        self.change_state("typing", "Text wird eingefügt …")
        self.tasks.run(lambda: windows.type_text(text, self.target, self.cancel_event), self.typed)

    def typed(self, result, error):
        self.change_state("idle", "Bereit zum Diktieren")
        self.feedback.setText(str(error) if error else "Text an Windows übergeben. Falls das Zielfeld ihn nicht annimmt, kannst du ihn hier kopieren.")
        if error:
            self.notify(str(error), error=True)
        if self.quit_requested:
            self.finish_quit()

    def on_progress(self, amount, message):
        self.progress.setValue(amount)
        self.feedback.setText(message)

    def cancel(self):
        if self.active_review:
            self.active_review.reject()
            return
        if self.state != "idle":
            self.cancel_event.set()
            self.feedback.setText("Abbruch angefordert …")
            if self.state == "recording":
                self.stop_recording()

    def new_text(self):
        if self.state == "idle":
            self.add_history("")
            self.editor.setFocus()

    def replace_editor(self, text):
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def restore_original(self):
        if 0 <= self.history_index < len(self.histories):
            self.replace_editor(self.histories[self.history_index].get("original", self.histories[self.history_index]["text"]))
            self.feedback.setText("Original wiederhergestellt. Rückgängig ist möglich.")

    def apply_command(self, text):
        action = text_tools.command(text)
        if not action:
            self.feedback.setText("Kein eindeutiger Sprachbefehl erkannt. Es wurde nichts verändert: " + text)
            return
        kind, value = action
        if kind == "paragraph":
            self.replace_editor(self.editor.toPlainText().rstrip() + "\n\n")
        elif kind == "delete_sentence":
            self.replace_editor(text_tools.delete_last_sentence(self.editor.toPlainText()))
        elif kind == "undo":
            self.editor.undo()
        elif kind == "profile":
            self.current_profile = value
            self.feedback.setText("KI-Profil ausgewählt: " + value)
        elif kind == "last_paragraph":
            text = self.editor.toPlainText()
            start, end = text_tools.last_paragraph(text)
            cursor = self.editor.textCursor()
            cursor.setPosition(len(text[:start].encode("utf-16-le")) // 2)
            cursor.setPosition(len(text[:end].encode("utf-16-le")) // 2, QTextCursor.MoveMode.KeepAnchor)
            self.editor.setTextCursor(cursor)
            self.current_profile = value
            self.review_text()

    def review_text(self):
        if self.state != "idle":
            return
        if not self.cfg["llm_enabled"]:
            self.feedback.setText("Die optionale Text-KI zuerst in den Einstellungen aktivieren und einrichten.")
            return
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.Document)
        text = cursor.selectedText().replace("\u2029", "\n")
        if not text.strip():
            self.feedback.setText("Zuerst Text diktieren oder im Editor eingeben.")
            return
        self.change_state("review", "Text-KI · Vorschau")
        self.hotkeys.enabled = False
        self.tray.contextMenu().setEnabled(False)
        dialog = Review(self, text, self.current_profile)
        self.active_review = dialog
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                result = dialog.result.toPlainText()
                if 0 <= self.history_index < len(self.histories):
                    item = self.histories[self.history_index]
                    if not item.get("original"):
                        item["original"] = self.editor.toPlainText()
                cursor.beginEditBlock()
                cursor.insertText(result)
                cursor.endEditBlock()
                self.editor.setTextCursor(cursor)
                self.save_history()
                if dialog.copy_after:
                    QApplication.clipboard().setText(engine.format_dictation(result, self.cfg["trailing_space"]))
                self.feedback.setText("Vorschlag freigegeben und kopiert." if dialog.copy_after else "Vorschlag übernommen. Original und Rückgängig bleiben verfügbar.")
        finally:
            self.active_review = None
            self.change_state("idle", "Bereit zum Diktieren")
            self.hotkeys.enabled = True
            self.tray.contextMenu().setEnabled(True)
            dialog.deleteLater()

    def delayed_insert(self):
        text = engine.format_dictation(self.editor.toPlainText(), self.cfg["trailing_space"])
        if self.state != "idle" or not text:
            return
        self.cancel_event.clear()
        self.change_state("pending_insert", "In 3 Sekunden einfügen · Jetzt Zielfeld anklicken")
        self.feedback.setText("ESC bricht ab. Der Text bleibt im Editor erhalten.")
        QTimer.singleShot(3000, lambda: self.insert_now(text))

    def insert_now(self, text):
        if self.quit_requested:
            self.finish_quit()
            return
        target = windows.foreground()
        if self.cancel_event.is_set() or not target or windows.window_pid(target) == os.getpid():
            self.change_state("idle", "Einfügen abgebrochen")
            self.feedback.setText("Kein externes Zielfeld gewählt oder Abbruch angefordert. Text bleibt erhalten.")
            return
        self.change_state("typing", "Freigegebener Text wird eingefügt …")
        self.tasks.run(lambda: windows.type_text(text, target, self.cancel_event), self.typed)

    def add_history(self, text, original=None):
        self.histories.insert(0, {"time": datetime.now().strftime("%d.%m. %H:%M"), "text": text,
                                 "original": text if original is None else original, "created": time.time()})
        self.histories = self.histories[:self.cfg["history_limit"]]
        self.history_index = -1
        self.refresh_history()
        self.save_history()

    def refresh_history(self):
        self.history.blockSignals(True)
        self.history.clear()
        for item in self.histories:
            preview = item["text"].replace("\n", " ")[:32]
            self.history.addItem(f"{item['time']}\n{preview}")
        self.history.blockSignals(False)
        if self.histories:
            self.history.setCurrentRow(0)

    def select_history(self, index):
        self.history_index = index
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.histories[index]["text"] if 0 <= index < len(self.histories) else "")
        self.editor.blockSignals(False)

    def edited(self):
        if self.history_index < 0 and self.editor.toPlainText():
            self.histories.insert(0, {"time": datetime.now().strftime("%d.%m. %H:%M"),
                "text": self.editor.toPlainText(), "original": "", "created": time.time()})
            self.history_index = 0
            self.history.blockSignals(True)
            self.history.insertItem(0, self.histories[0]["time"] + "\nNeuer Entwurf")
            self.history.setCurrentRow(0)
            self.history.blockSignals(False)
        if 0 <= self.history_index < len(self.histories):
            self.histories[self.history_index]["text"] = self.editor.toPlainText()
            self.histories[self.history_index]["copied"] = False
            self.save_timer.start(600)

    def prune_history(self):
        days = self.cfg["history_days"]
        if days:
            self.histories = [item for item in self.histories if item.get("created", 0) >= time.time() - days * 86400]
        self.histories = self.histories[:self.cfg["history_limit"]]

    def save_history(self):
        try:
            path = DATA / "history.json"
            if self.cfg["persist"]:
                days = self.cfg["history_days"]
                items = [item for item in self.histories if not days or item.get("created", 0) >= time.time() - days * 86400]
                engine.save_json(path, {"items": items[:self.cfg["history_limit"]]})
            else:
                path.unlink(missing_ok=True)
            draft = DATA / "draft.json"
            if self.cfg["draft_protection"]:
                item = self.histories[self.history_index] if 0 <= self.history_index < len(self.histories) else {}
                if item.get("text") and not item.get("copied"):
                    engine.save_json(draft, item)
                else:
                    draft.unlink(missing_ok=True)
            else:
                draft.unlink(missing_ok=True)
        except OSError as exc:
            self.feedback.setText(f"Verlauf konnte nicht gespeichert oder gelöscht werden: {exc}")

    def clear_history(self):
        self.histories.clear()
        self.history_index = -1
        self.history.clear()
        self.editor.clear()
        self.save_history()

    def copy_text(self):
        text = engine.format_dictation(self.editor.toPlainText(), self.cfg["trailing_space"])
        if text:
            QApplication.clipboard().setText(text)
            if 0 <= self.history_index < len(self.histories):
                self.histories[self.history_index]["copied"] = True
                self.save_history()
            self.feedback.setText("Text kopiert. Mit STRG + V im gewünschten Eingabefeld einfügen.")

    def export_text(self):
        if not self.editor.toPlainText():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Text speichern", "Diktat.txt", "Textdateien (*.txt)")
        if path:
            try:
                Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
            except OSError as exc:
                self.notify(str(exc), error=True)

    def notify(self, message, error=False):
        self.feedback.setText(message)
        allowed = self.cfg["notifications"] == "Alle" or (self.cfg["notifications"] == "Nur Fehler" and error)
        if not self.testing and allowed and (error or not self.isActiveWindow()):
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.testing or self.quit_requested:
            event.accept()
        elif self.cfg["close_to_tray"] and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            event.ignore()
            self.quit()

    def quit(self):
        self.quit_requested = True
        self.hotkeys.enabled = False
        self.cancel()
        if self.state != "idle":
            self.status.setText("Wird beendet …")
            return
        self.finish_quit()

    def finish_quit(self):
        self.llm.stop()
        self.save_timer.stop()
        self.save_history()
        if not self.testing:
            self.hotkeys.stop()
        self.tray.hide()
        QApplication.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--smoke-test", type=Path)
    parser.add_argument("--smoke-model", type=Path)
    parser.add_argument("--smoke-audio", type=Path)
    parser.add_argument("--smoke-llm", type=Path)
    parser.add_argument("--smoke-runtime", type=Path)
    parser.add_argument("--probe-model", type=Path)
    args = parser.parse_args()
    if args.probe_model:
        engine.Recognizer(args.probe_model, threads=1)
        return 0
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Losansky.IT")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    try:
        prepare_user_directory(DATA)
    except OSError as exc:
        message = QMessageBox(QMessageBox.Icon.Critical, APP_NAME,
            "Der Benutzerordner ist nicht als beschreibbarer Datenordner verfügbar.\n\n"
            f"{DATA}\n\n"
            "Der Programmordner benötigt keine Schreibrechte. Bitte prüfen lassen, ob der oben "
            "genannte Pfad ein Ordner ist und dein Benutzer dort Dateien anlegen, ersetzen und löschen darf.",
            QMessageBox.StandardButton.Close)
        message.setDetailedText(f"{type(exc).__name__}: {exc}")
        message.exec()
        return 1
    lock = QLockFile(str(DATA / "running.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(50):
        if lock.error() == QLockFile.LockError.LockFailedError:
            QMessageBox.information(None, APP_NAME, "Offline-Diktat oder die bisherige Dictate-Version läuft bereits. Öffne oder beende sie über das Mikrofon-Symbol neben der Windows-Uhr.")
            return 0
        QMessageBox.critical(None, APP_NAME,
            f"Die Sitzungssperre konnte nicht angelegt werden:\n{DATA / 'running.lock'}\n\n"
            f"Fehler: {lock.error().name}\nBitte die Schreibrechte im Benutzerordner prüfen lassen.")
        return 1
    window = Main(testing=bool(args.smoke_test))
    if args.smoke_test:
        window.add_history(engine.format_dictation("Erster Satz. Zweiter Satz. Und dritter Satz."))
        window.change_state("idle", "Bereit zum Diktieren")
        window.show()
        def capture():
            window.grab().save(str(args.smoke_test))
            about = AboutDialog(window, DISPLAY_VERSION)
            about.show()
            app.processEvents()
            about.grab().save(str(args.smoke_test.with_name(args.smoke_test.stem + "-about.png")))
            about.tabs.setCurrentIndex(1)
            about.components.setCurrentRow(2)
            app.processEvents()
            about.grab().save(str(args.smoke_test.with_name(args.smoke_test.stem + "-licenses.png")))
            about.close()
            setup = Setup(window)
            setup.pages.setCurrentIndex(2)
            setup.update_step()
            setup.show()
            app.processEvents()
            setup.grab().save(str(args.smoke_test.with_name(args.smoke_test.stem + "-settings.png")))
            setup.reject()
            settings = Settings(window)
            settings.navigation.setCurrentIndex(4)
            settings.show()
            app.processEvents()
            settings.grab().save(str(args.smoke_test.with_name(args.smoke_test.stem + "-text-ki.png")))
            settings.reject()
            # Native packaged dependencies, without microphone access.
            import sounddevice
            import sherpa_onnx
            import ssl
            ssl.create_default_context()
            result = {"version": VERSION, "audio_devices": len(sounddevice.query_devices()),
                      "openssl": ssl.OPENSSL_VERSION, "settings_pages": settings.pages.count(),
                      "sherpa": sherpa_onnx.__version__, "input_size": windows.ctypes.sizeof(windows.INPUT),
                      "license_components": len(about.catalog),
                      "trailing_space_default": window.cfg["trailing_space"],
                      "product_name": window.windowTitle()}
            if args.smoke_model:
                import wave
                import numpy as np
                engine.validate_model(args.smoke_model)
                recognizer = engine.Recognizer(args.smoke_model)
                result["model_loaded_on_cpu"] = True
                if args.smoke_audio:
                    with wave.open(str(args.smoke_audio)) as audio_file:
                        audio = np.frombuffer(audio_file.readframes(audio_file.getnframes()), dtype=np.int16)
                    result["test_transcript"] = recognizer.transcribe(audio)
            if args.smoke_llm and args.smoke_runtime:
                cfg = dict(window.cfg, llm_model=str(args.smoke_llm), llm_runtime=str(args.smoke_runtime))
                rewritten, elapsed = window.llm.rewrite(cfg,
                    text_tools.messages("Der Server bleibt ausgeschaltet. Bitte nicht vor 14 Uhr starten.", "Deutsch → Englisch"),
                    threading.Event())
                result["llm_text"] = rewritten
                result["llm_seconds"] = elapsed
            engine.save_json(args.smoke_test.with_suffix(".json"), result)
            window.finish_quit()
        QTimer.singleShot(700, capture)
    elif not args.minimized or not window.cfg["setup"]:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
