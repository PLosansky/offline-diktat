import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import engine
import model_store
import text_tools
from llm import LocalLLM


class TextTests(unittest.TestCase):
    def test_local_client_does_not_initialize_tls_or_proxies(self):
        with patch('urllib.request.HTTPSHandler', side_effect=AssertionError('TLS must not initialize')):
            client = LocalLLM()
        names = {type(handler).__name__ for handler in client.opener.handlers}
        self.assertNotIn('ProxyHandler', names)
        self.assertNotIn('HTTPSHandler', names)

    def test_literal_dictionary_no_cascade_and_word_boundaries(self):
        self.assertEqual(text_tools.replacements("losanski LosanskiX check em kay", "Losanski => Losansky\nLosansky => Falsch\ncheck em kay => Checkmk"),
                         "Losansky LosanskiX Checkmk")
        with self.assertRaises(ValueError):
            text_tools.replacements("", "ungültig")

    def test_commands_match_whole_utterance(self):
        self.assertEqual(text_tools.command("Neuer Absatz."), ("paragraph", None))
        self.assertIsNone(text_tools.command("Ich sagte neuer Absatz und sprach weiter."))
        self.assertEqual(text_tools.delete_last_sentence("Erster Satz. Zweiter Satz."), "Erster Satz. ")
        self.assertEqual(text_tools.last_paragraph("😀 Anfang.\n\nLetzter Absatz. "), (11, 26))

    def test_manifest_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            spec = {"backend": "whisper", "encoder": "../escape.onnx", "decoder": "d", "tokens": "t"}
            (folder / "speech-model.json").write_text(json.dumps(spec))
            with self.assertRaises(ValueError):
                model_store.speech_manifest(folder)

    def test_custom_manifest_references_read_only_source_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "source"
            profile = folder / "profile"
            source.mkdir()
            profile.mkdir()
            for name in ["e.onnx", "d.onnx", "tokens.txt"]:
                (source / name).write_bytes(b"model")
            spec = dict(backend="whisper", source_folder=str(source), encoder="e.onnx", decoder="d.onnx", tokens="tokens.txt")
            (profile / "speech-model.json").write_text(json.dumps(spec))
            self.assertEqual(model_store.speech_manifest(profile)["_root"], str(source))
            self.assertEqual(len(list(source.iterdir())), 3)

    def test_truncated_llm_output_is_never_accepted(self):
        client = LocalLLM()
        replies = [{"prompt": "prompt"}, {"tokens": [1, 2]},
                   {"choices": [{"finish_reason": "length", "message": {"content": "Unvollständig"}}]}]
        with patch.object(client, "start"), patch.object(client, "request", side_effect=replies):
            with self.assertRaisesRegex(ValueError, "nicht vollständig"):
                client.rewrite({"llm_context": 4096}, [], threading.Event())

    def test_context_overflow_never_sends_generation_request(self):
        client = LocalLLM()
        replies = [{"prompt": "prompt"}, {"tokens": list(range(2000))}]
        with patch.object(client, "start"), patch.object(client, "request", side_effect=replies) as request:
            with self.assertRaisesRegex(ValueError, "zu lang"):
                client.rewrite({"llm_context": 2048}, [], threading.Event())
            self.assertEqual(request.call_count, 2)

    def test_cancel_discards_completed_response(self):
        cancel = threading.Event()
        cancel.set()
        client = LocalLLM()
        with patch.object(client, "start"), patch.object(client, "request") as request:
            with self.assertRaises(engine.Cancelled):
                client.rewrite({"llm_context": 2048}, [], cancel)
            request.assert_not_called()


class WorkbenchTests(unittest.TestCase):
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
        self.window.llm.stop()
        self.window.close()
        self.patch.stop()
        self.temp.cleanup()

    def test_internal_dictation_does_not_type_or_notify(self):
        self.window.capture_editor = True
        with patch.object(self.window, "notify") as notify, patch.object(self.module.windows, "type_text") as typing:
            self.window.transcribed(("Ein eigener Entwurf.", False), None)
            typing.assert_not_called()
            notify.assert_not_called()
            self.assertEqual(self.window.editor.toPlainText(), "Ein eigener Entwurf. ")

    def test_normal_dictation_does_not_execute_command(self):
        self.window.capture_editor = True
        self.window.add_history("Vorhandener Text.")
        self.window.transcribed(("Letzten Satz löschen.", False), None)
        self.assertEqual(self.window.editor.toPlainText(), "Letzten Satz löschen. ")
        self.assertEqual(self.window.histories[1]["text"], "Vorhandener Text.")

    def test_explicit_command_does_not_create_new_dictation(self):
        self.window.add_history("Erster Satz. Zweiter Satz.")
        self.window.command_recording = True
        self.window.transcribed(("Letzten Satz löschen.", False), None)
        self.assertEqual(self.window.editor.toPlainText(), "Erster Satz. ")
        self.window.editor.undo()
        self.assertEqual(self.window.editor.toPlainText(), "Erster Satz. Zweiter Satz.")
        self.assertFalse(self.window.command_recording)

    def test_continue_preserves_manual_corrections_and_original(self):
        self.window.add_history("Original.")
        self.window.replace_editor("Handkorrektur.")
        self.window.capture_editor = True
        self.window.append_recording = True
        self.window.transcribed(("Weiterer Satz.", False), None)
        self.assertEqual(self.window.editor.toPlainText(), "Handkorrektur. Weiterer Satz. ")
        self.window.restore_original()
        self.assertEqual(self.window.editor.toPlainText(), "Original. Weiterer Satz.")

    def test_draft_is_opt_in_restored_and_deleted_when_disabled(self):
        self.window.add_history("Nicht verlieren", "Original")
        path = Path(self.temp.name) / "draft.json"
        self.assertFalse(path.exists())
        self.window.cfg["draft_protection"] = True
        self.window.save_history()
        engine.save_json(Path(self.temp.name) / "settings.json", self.window.cfg)
        restored = self.module.Main(testing=True)
        self.assertEqual(restored.editor.toPlainText(), "Nicht verlieren")
        self.assertEqual(restored.histories[0]["original"], "Original")
        restored.cfg["draft_protection"] = False
        restored.save_history()
        self.assertFalse(path.exists())
        restored.timer.stop()
        restored.save_timer.stop()
        restored.close()

    def test_settings_are_separate_and_save_all_pages(self):
        self.window.recognizer = object()
        dialog = self.module.Settings(self.window)
        self.assertEqual(dialog.pages.count(), 6)
        self.assertTrue(dialog.next.isEnabled())
        dialog.output_mode.setCurrentIndex(1)
        dialog.drafts.setChecked(True)
        dialog.dictionary.setPlainText("Losanski => Losansky")
        dialog.advance()
        self.assertEqual(dialog.cfg["output_mode"], "editor")
        self.assertTrue(dialog.cfg["draft_protection"])
        self.assertEqual(dialog.cfg["dictionary"], "Losanski => Losansky")
        dialog.close()

    def test_preview_has_no_side_effects_before_approval(self):
        from review import Review
        self.window.add_history("Originaltext")
        self.qt.clipboard().setText("Zwischenablage unverändert")
        dialog = Review(self.window, "Originaltext")
        self.assertFalse(dialog.approve.isEnabled())
        dialog.finished(("Vorschlag", 1.0), None)
        self.assertEqual(self.window.editor.toPlainText(), "Originaltext")
        self.assertEqual(self.qt.clipboard().text(), "Zwischenablage unverändert")
        dialog.reject()
        self.assertEqual(self.window.editor.toPlainText(), "Originaltext")

    def test_failed_generation_cannot_be_approved(self):
        from review import Review
        dialog = Review(self.window, "Original")
        dialog.finished(None, RuntimeError("Testfehler"))
        self.assertFalse(dialog.approve.isEnabled())
        dialog.reject()

    def test_pending_insert_cancel_never_calls_windows(self):
        self.window.add_history("Text")
        self.window.cancel_event.set()
        with patch.object(self.module.windows, "type_text") as typing:
            self.window.insert_now("Text")
            typing.assert_not_called()

    def test_keep_original_before_dictionary(self):
        self.window.cfg["dictionary"] = "Losanski => Losansky"
        self.window.capture_editor = True
        self.window.transcribed(("Losanski", False), None)
        self.assertEqual(self.window.editor.toPlainText(), "Losansky ")
        self.window.restore_original()
        self.assertEqual(self.window.editor.toPlainText(), "Losanski")

    def test_approval_replaces_only_selection_and_can_be_undone(self):
        from review import Review
        from PySide6.QtWidgets import QDialog
        from PySide6.QtGui import QTextCursor
        self.window.cfg["llm_enabled"] = True
        self.window.add_history("Anfang. Mitte. Ende.")
        cursor = self.window.editor.textCursor()
        cursor.setPosition(8)
        cursor.setPosition(14, QTextCursor.MoveMode.KeepAnchor)
        self.window.editor.setTextCursor(cursor)
        self.qt.clipboard().setText("Unverändert")
        def approved(dialog):
            self.assertEqual(dialog.original, "Mitte.")
            dialog.result.setPlainText("Neu.")
            return QDialog.DialogCode.Accepted
        with patch.object(Review, "exec", new=approved):
            self.window.review_text()
        self.assertEqual(self.window.editor.toPlainText(), "Anfang. Neu. Ende.")
        self.assertEqual(self.qt.clipboard().text(), "Unverändert")
        self.window.editor.undo()
        self.assertEqual(self.window.editor.toPlainText(), "Anfang. Mitte. Ende.")

    def test_copy_honors_separator_and_clears_pending_draft(self):
        self.window.cfg["draft_protection"] = True
        self.window.add_history("Bearbeiteter Text.")
        self.window.copy_text()
        self.assertEqual(self.qt.clipboard().text(), "Bearbeiteter Text. ")
        self.assertFalse((Path(self.temp.name) / "draft.json").exists())
        self.window.cfg["trailing_space"] = False
        self.window.copy_text()
        self.assertEqual(self.qt.clipboard().text(), "Bearbeiteter Text.")

    def test_draft_and_history_do_not_duplicate_on_restart(self):
        self.window.cfg.update(draft_protection=True, persist=True)
        self.window.add_history("Ein Entwurf")
        engine.save_json(Path(self.temp.name) / "settings.json", self.window.cfg)
        restored = self.module.Main(testing=True)
        self.assertEqual(len(restored.histories), 1)
        restored.timer.stop()
        restored.save_timer.stop()
        restored.close()


if __name__ == "__main__":
    unittest.main()
