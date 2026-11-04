"""GitHub release discovery and verified downloads; never executes an update."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import urllib.error

REPOSITORY = "PLosansky/offline-diktat"
RELEASES = f"https://github.com/{REPOSITORY}/releases"


def version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("Keine stabile Versionsnummer.")
    return tuple(map(int, match.groups()))


def latest(current):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Offline-Diktat-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            release = json.loads(response.read(1024 * 1024))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError("Noch kein öffentliches Release verfügbar oder Repository nicht öffentlich erreichbar.") from exc
        raise ValueError(f"Updateprüfung nicht möglich (HTTP {exc.code}). Später erneut versuchen.") from exc
    if release.get("draft") or release.get("prerelease") or version(release["tag_name"]) <= version(current):
        return None
    tag = release["tag_name"]
    name = f"Offline-Diktat-{tag.lstrip('v')}-Update.zip"
    asset = next((a for a in release.get("assets", []) if a["name"] == name), None)
    if not asset:
        raise ValueError("Neue Version vorhanden, aber noch kein Windows-Updatepaket veröffentlicht.")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("Das Updatepaket hat keine überprüfbare SHA-256-Prüfsumme.")
    url = asset["browser_download_url"]
    if url != f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}":
        raise ValueError("Unerwartete Downloadadresse.")
    return dict(version=tag, name=name, url=url, digest=digest[7:].lower(),
                size=int(asset["size"]), notes=(release.get("body") or "")[:12000])


def download(release, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    size = release["size"]
    if not 0 < size <= 2 * 1024 ** 3:
        raise ValueError("Ungültige Größe des Updatepakets.")
    handle, temporary = tempfile.mkstemp(prefix="update-", suffix=".part", dir=folder)
    try:
        digest, count = hashlib.sha256(), 0
        with os.fdopen(handle, "wb") as out:
            req = urllib.request.Request(release["url"], headers={"User-Agent": "Offline-Diktat-Updater"})
            with urllib.request.urlopen(req, timeout=30) as response:
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > size:
                        raise ValueError("Update ist größer als angekündigt.")
                    digest.update(chunk)
                    out.write(chunk)
        if count != size or digest.hexdigest() != release["digest"]:
            raise ValueError("Update unvollständig oder Prüfsumme falsch. Download wurde verworfen.")
        target = folder / release["name"]
        os.replace(temporary, target)
        return str(target)
    finally:
        Path(temporary).unlink(missing_ok=True)
