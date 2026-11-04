"""Regression coverage for WinError 183 and profile-only configuration writes."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import engine
import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.base = Path(self.root.name)

    def tearDown(self):
        self.root.cleanup()

    def test_first_start_second_start_and_setting_round_trip(self):
        data = self.base / 'Benutzer mit Leerzeichen' / 'DictateOffline'
        storage.prepare_user_directory(data)
        engine.save_json(data / 'settings.json', {'keys': ['f8'], 'trailing_space': False})
        storage.prepare_user_directory(data)
        self.assertEqual(engine.load_json(data / 'settings.json', {}),
                         {'keys': ['f8'], 'trailing_space': False})
        self.assertEqual([p.name for p in data.iterdir()], ['settings.json'])

    @unittest.skipUnless(os.name == 'nt', 'Windows attribute fallback')
    def test_existing_directory_with_failed_python_directory_check(self):
        data = self.base / 'DictateOffline'
        data.mkdir()
        # This reproduces the relevant failure mode: mkdir raises EEXIST,
        # but Python's stat-based is_dir() does not acknowledge the directory.
        with patch.object(Path, 'is_dir', return_value=False):
            with self.assertRaises(FileExistsError):
                data.mkdir(parents=True, exist_ok=True)
            storage.prepare_user_directory(data)
            engine.save_json(data / 'settings.json', {'language': 'Deutsch'})
            storage.prepare_user_directory(data)
        self.assertEqual(json.loads((data / 'settings.json').read_text()), {'language': 'Deutsch'})

    def test_directory_created_during_check(self):
        with patch.object(storage, 'is_directory', side_effect=[False, True]), \
             patch.object(Path, 'mkdir', side_effect=FileExistsError(183, 'already exists')):
            self.assertEqual(storage.ensure_directory(self.base / 'race'), self.base / 'race')

    def test_same_name_regular_file_is_not_accepted_or_removed(self):
        data = self.base / 'DictateOffline'
        data.write_text('Diese Datei erhalten.', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            storage.prepare_user_directory(data)
        self.assertEqual(data.read_text(encoding='utf-8'), 'Diese Datei erhalten.')

    def test_failed_replace_preserves_existing_settings_and_cleans_temp(self):
        target = self.base / 'settings.json'
        engine.save_json(target, {'keys': ['f9']})
        with patch.object(storage.os, 'replace', side_effect=PermissionError('Corporate access denied')):
            with self.assertRaises(PermissionError):
                engine.save_json(target, {'keys': ['f8']})
        self.assertEqual(json.loads(target.read_text()), {'keys': ['f9']})
        self.assertEqual([p.name for p in self.base.iterdir()], ['settings.json'])

    def test_short_windows_file_lock_is_retried_without_truncating_target(self):
        target = self.base / 'settings.json'
        engine.save_json(target, {'keys': ['f9']})
        original_replace = storage.os.replace
        calls = []
        def locked_once(source, destination):
            calls.append(1)
            if len(calls) == 1:
                self.assertEqual(json.loads(target.read_text()), {'keys': ['f9']})
                error = PermissionError('Temporarily locked')
                error.winerror = 32
                raise error
            return original_replace(source, destination)
        with patch.object(storage.os, 'replace', side_effect=locked_once):
            engine.save_json(target, {'keys': ['f8']})
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(target.read_text()), {'keys': ['f8']})

    def test_save_does_not_touch_program_directory_or_global_temp(self):
        program = self.base / 'Programme'
        program.mkdir()
        data = self.base / 'LocalAppData' / 'DictateOffline'
        old_cwd = Path.cwd()
        original = tempfile.NamedTemporaryFile
        writes = []
        def track(*args, **kwargs):
            writes.append(Path(kwargs['dir']))
            return original(*args, **kwargs)
        try:
            os.chdir(program)
            with patch.object(storage.tempfile, 'NamedTemporaryFile', side_effect=track):
                storage.prepare_user_directory(data)
                engine.save_json(data / 'settings.json', {'setup': True})
        finally:
            os.chdir(old_cwd)
        self.assertTrue(writes)
        self.assertTrue(all(path == data for path in writes))
        self.assertEqual(list(program.iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
