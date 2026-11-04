"""Regression tests: chunk integrity, cancellation, hotkeys, output and privacy."""
import ctypes
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import engine
import windows
from pynput import keyboard


class EngineTests(unittest.TestCase):
    def test_separate_dictations_have_a_separator(self):
        result = "".join(engine.format_dictation(t) for t in
                         ["Erster Satz.", "Zweiter Satz.", "Und dritter Satz."])
        self.assertEqual(result, "Erster Satz. Zweiter Satz. Und dritter Satz. ")

    def test_separator_handles_existing_whitespace_long_text_and_disabled(self):
        for text in ["Kurz.", "Satz. ", "Satz.  \t\n", "Sehr lang. " * 5000]:
            self.assertEqual(engine.format_dictation(text), text.rstrip() + " ")
            self.assertEqual(engine.format_dictation(text, False), text)
        self.assertEqual(engine.format_dictation(" \n\t"), "")
        self.assertEqual(engine.format_dictation(""), "")

    def test_long_audio_preserves_every_sample_and_bounds_inference(self):
        # 12 minutes of samples must neither disappear nor overlap.
        audio = np.arange(engine.RATE * 720, dtype=np.float32) % 317
        chunks = list(engine.split_audio(audio))
        self.assertTrue(all(0 < len(c) <= 60 * engine.RATE for c in chunks))
        np.testing.assert_array_equal(np.concatenate(chunks), audio)

    def test_empty_and_short_audio(self):
        self.assertEqual(list(engine.split_audio(np.array([], dtype=np.float32))), [])
        audio = np.ones(1000, dtype=np.float32)
        np.testing.assert_array_equal(list(engine.split_audio(audio))[0], audio)

    def test_model_integrity_rejects_corruption_and_git_pointer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model"
            path.write_bytes(b"abcdef")
            spec = (6, "sha256", hashlib.sha256(b"abcdef").hexdigest())
            engine.check_file(path, spec)
            path.write_bytes(b"abcdeg")
            with self.assertRaises(ValueError):
                engine.check_file(path, spec)
            path.write_bytes(b"version https://git-lfs.github.com/spec/v1")
            with self.assertRaises(ValueError):
                engine.check_file(path, spec)

    def test_cancel_prevents_decoding(self):
        rec = object.__new__(engine.Recognizer)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(engine.Cancelled):
            rec.transcribe(np.zeros(100, dtype=np.int16), cancel=cancel)

    def test_retry_and_order(self):
        rec = object.__new__(engine.Recognizer)
        lengths = []
        def decode(audio):
            lengths.append(len(audio))
            return "kurz" if len(audio) <= 20 * engine.RATE else ""
        with patch.object(rec, "decode", side_effect=decode):
            result = rec.transcribe(np.ones(engine.RATE * 45, dtype=np.float32))
        self.assertTrue(all(n <= 20 * engine.RATE for n in lengths[1:]))
        self.assertEqual(sum(lengths[1:]), 45 * engine.RATE)
        self.assertEqual(len(result.split()), len(lengths) - 1)


class WindowsTests(unittest.TestCase):
    def new_keys(self, keys):
        self.events = []
        return windows.Hotkeys(keys, lambda: self.events.append("press"),
            lambda: self.events.append("release"), lambda: self.events.append("esc"),
            lambda k: self.events.append(k))

    def test_hold_does_not_repeat(self):
        keys = self.new_keys(["f9"])
        keys.on_press(keyboard.Key.f9)
        keys.on_press(keyboard.Key.f9)
        keys.on_release(keyboard.Key.f9)
        self.assertEqual(self.events, ["press", "release"])

    def test_combination_release_and_escape(self):
        keys = self.new_keys(["ctrl", "alt", "d"])
        keys.on_press(keyboard.Key.ctrl_l)
        keys.on_press(keyboard.Key.alt_l)
        keys.on_press(keyboard.KeyCode.from_vk(68))
        keys.on_release(keyboard.Key.ctrl_l)
        keys.on_press(keyboard.Key.esc)
        self.assertEqual(self.events, ["press", "release", "esc"])

    def test_capture_does_not_start_recording(self):
        keys = self.new_keys(["f9"])
        keys.capture = True
        keys.on_press(keyboard.Key.f9)
        self.assertEqual(self.events, [["f9"]])

    def test_reject_unsafe_bare_letters_or_escape(self):
        self.assertFalse(windows.valid_hotkey({"a"}))
        self.assertFalse(windows.valid_hotkey({"esc"}))
        self.assertTrue(windows.valid_hotkey({"ctrl", "alt", "a"}))

    def test_focus_change_blocks_typing(self):
        with patch.object(windows, "foreground", return_value=2), patch.object(windows.user32, "GetAsyncKeyState", return_value=0), patch.object(windows.user32, "SendInput") as send:
            with self.assertRaises(RuntimeError):
                windows.type_text("Geheim", 1)
            send.assert_not_called()

    def test_unicode_and_blocked_injection(self):
        units = []
        def capture(count, events, size):
            self.assertEqual(size, 40)
            units.extend(events[i].ki.wScan for i in range(0, count, 2))
            return count
        with patch.object(windows, "foreground", return_value=1), patch.object(windows.user32, "GetAsyncKeyState", return_value=0), patch.object(windows.user32, "SendInput", side_effect=capture):
            windows.type_text("ÄÖÜß 😀", 1)
        actual = b"".join(x.to_bytes(2, "little") for x in units).decode("utf-16-le")
        self.assertEqual(actual, "ÄÖÜß 😀")
        with patch.object(windows, "foreground", return_value=1), patch.object(windows.user32, "GetAsyncKeyState", return_value=0), patch.object(windows.user32, "SendInput", return_value=0):
            with self.assertRaises(RuntimeError):
                windows.type_text("Text", 1)


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        import app
        self.module = app
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(app, "DATA", Path(self.temp.name))
        self.patch.start()
        self.window = app.Main(testing=True)

    def tearDown(self):
        self.window.timer.stop()
        self.window.save_timer.stop()
        self.window.close()
        self.patch.stop()
        self.temp.cleanup()

    def test_history_edit_and_no_default_disk_storage(self):
        self.window.add_history("Erster Text")
        self.window.editor.setPlainText("Korrigierter Text")
        self.window.add_history("Zweiter Text")
        self.window.history.setCurrentRow(1)
        self.assertEqual(self.window.editor.toPlainText(), "Korrigierter Text")
        self.assertFalse((Path(self.temp.name) / "history.json").exists())

    def test_optional_persistence_and_erasure(self):
        self.window.cfg["persist"] = True
        self.window.add_history("Lokal gespeichert")
        path = Path(self.temp.name) / "history.json"
        self.assertTrue(path.exists())
        self.window.cfg["persist"] = False
        self.window.save_history()
        self.assertFalse(path.exists())

    def test_setup_requires_valid_model(self):
        setup = self.module.Setup(self.window)
        self.assertFalse(setup.next.isEnabled())
        self.assertEqual(setup.pages.count(), 3)
        setup.reject()

    def test_separator_default_for_existing_settings_and_persistence(self):
        path = Path(self.temp.name) / 'settings.json'
        engine.save_json(path, {'keys': ['f8'], 'toggle': True})
        cfg = engine.load_json(path, self.module.DEFAULT)
        self.assertTrue(cfg['trailing_space'])
        self.assertEqual(cfg['keys'], ['f8'])
        self.window.cfg = cfg
        setup = self.module.Setup(self.window)
        self.assertTrue(setup.trailing_space_box.isChecked())
        setup.trailing_space_box.setChecked(False)
        setup.pages.setCurrentIndex(2)
        setup.advance()
        engine.save_json(path, setup.cfg)
        self.assertFalse(engine.load_json(path, self.module.DEFAULT)['trailing_space'])

    def test_insertion_and_history_use_separator_only_after_full_result(self):
        self.window.target = 123
        self.window.tasks.run = lambda fn, callback: callback(fn(), None)
        with patch.object(windows, 'foreground', return_value=123), patch.object(windows, 'type_text') as send:
            self.window.transcribed(('Ein Satz. Noch ein Satz.', False), None)
            self.assertEqual(send.call_args.args[0], 'Ein Satz. Noch ein Satz. ')
            self.assertEqual(self.window.editor.toPlainText(), 'Ein Satz. Noch ein Satz. ')
            self.window.cfg['trailing_space'] = False
            self.window.transcribed(('Ohne Abstand.', False), None)
            self.assertEqual(send.call_args.args[0], 'Ohne Abstand.')

    def test_about_loads_all_local_licenses_without_network(self):
        from about import AboutDialog
        with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network access')):
            dialog = AboutDialog(self.window)
            self.assertGreater(len(dialog.catalog), 10)
            for index, item in enumerate(dialog.catalog):
                dialog.components.setCurrentRow(index)
                self.assertTrue(item['files'], item['name'])
                for file_index in range(dialog.license_files.count()):
                    dialog.license_files.setCurrentIndex(file_index)
                    self.assertTrue(dialog.license_text.toPlainText().strip(),
                                    dialog.license_files.currentData())
                    self.assertNotIn('Lizenzdatei fehlt.', dialog.license_text.toPlainText())
            dialog.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
