import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import updates


class UpdateTests(unittest.TestCase):
    def release(self):
        name = "Offline-Diktat-1.2.0-Update.zip"
        return dict(tag_name="v1.2.0", assets=[dict(name=name,
            browser_download_url=f"https://github.com/{updates.REPOSITORY}/releases/download/v1.2.0/{name}",
            digest="sha256:" + hashlib.sha256(b"zip").hexdigest(), size=3)])

    def check(self, payload, current="1.1.0"):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
            return updates.latest(current)

    def test_numeric_versions_and_no_downgrade(self):
        self.assertGreater(updates.version("v1.10.0"), updates.version("1.2.0"))
        self.assertIsNone(self.check(self.release(), "1.2.0"))
        self.assertIsNone(self.check(self.release(), "2.0.0"))
        self.assertIsNone(self.check(dict(self.release(), prerelease=True)))

    def test_requires_digest_and_known_download_origin(self):
        payload = self.release()
        payload["assets"][0]["digest"] = None
        with self.assertRaises(ValueError):
            self.check(payload)
        payload = self.release()
        payload["assets"][0]["browser_download_url"] = "https://example.com/update.zip"
        with self.assertRaises(ValueError):
            self.check(payload)

    def test_corrupt_download_keeps_previous_file_and_removes_partial(self):
        release = self.check(self.release())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / release["name"]
            target.write_bytes(b"previous")
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"bad")):
                with self.assertRaises(ValueError):
                    updates.download(release, folder)
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(list(Path(folder).glob("*.part")), [])

    def test_verified_download(self):
        release = self.check(self.release())
        with tempfile.TemporaryDirectory() as folder:
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"zip")):
                path = updates.download(release, folder)
            self.assertEqual(Path(path).read_bytes(), b"zip")
