"""Pinned, checksum-verified optional downloads and explicit speech-model manifests."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import tempfile
import urllib.request
import zipfile

from storage import ensure_directory, write_json

LLM_MODELS = [
    {"name": "Qwen3 1.7B · Q4_K_M · Ausgangsmodell", "repo": "unsloth/Qwen3-1.7B-GGUF",
     "revision": "d7f544eead698dbd1f15126ef60b45a1e1933222", "file": "Qwen3-1.7B-Q4_K_M.gguf",
     "size": 1107409472, "sha256": "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897",
     "ram": "Grobe Planung: 1,5–2,5 GB RAM, zusätzlich zur Spracherkennung"},
    {"name": "Qwen3.5 0.8B · Q4_0 · Experimentell", "repo": "ggml-org/Qwen3.5-0.8B-GGUF",
     "revision": "807dfd9a6fadbf703207aac3bfb0b2b3040d077c", "file": "Qwen3.5-0.8B-Q4_0.gguf",
     "size": 563036064, "sha256": "57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf",
     "ram": "Grobe Planung: 0,8–1,5 GB RAM. Im Beispieltest unzuverlässig: Anweisungen ignoriert und Uhrzeit verändert"},
    {"name": "Qwen3.5 4B · Q4_K_M · Größer", "repo": "unsloth/Qwen3.5-4B-GGUF",
     "revision": "e87f176479d0855a907a41277aca2f8ee7a09523", "file": "Qwen3.5-4B-Q4_K_M.gguf",
     "size": 2740937888, "sha256": "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
     "ram": "Grobe Planung: 3–5 GB RAM, zusätzlich zur Spracherkennung"},
]
RUNTIME = {"url": "https://github.com/ggml-org/llama.cpp/releases/download/b11669/llama-b11669-bin-win-cpu-x64.zip",
           "size": 19537886, "sha256": "37b3efcf962847ca869745fd4ccf7f5e7e8dacfeff9fa3523b4ca8cdc66d632b"}


def download_verified(url, path, size, digest, cancel, progress):
    from engine import check_cancel
    path = Path(path)
    ensure_directory(path.parent)
    if path.is_file() and path.stat().st_size == size:
        progress(0, "Prüfe vorhandene Datei …")
        if checksum(path, cancel) == digest:
            return path
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".download", delete=False) as tmp:
        partial = Path(tmp.name)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Offline-Diktat/1.1"})
        h, count = hashlib.sha256(), 0
        with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as output:
            while True:
                check_cancel(cancel)
                block = response.read(1024 * 1024)
                if not block:
                    break
                count += len(block)
                if count > size:
                    raise ValueError("Download größer als erwartet.")
                h.update(block)
                output.write(block)
                progress(int(100 * count / size), f"{count / 1e6:.0f} / {size / 1e6:.0f} MB")
        check_cancel(cancel)
        if count != size or h.hexdigest() != digest:
            raise ValueError("Download unvollständig oder Prüfsumme falsch. Vorhandenes Modell bleibt erhalten.")
        os.replace(partial, path)
        return path
    finally:
        partial.unlink(missing_ok=True)


def checksum(path, cancel):
    from engine import check_cancel
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            check_cancel(cancel)
            h.update(block)
    return h.hexdigest()


def download_llm(index, root, cancel, progress):
    spec = LLM_MODELS[index]
    path = Path(root) / spec["file"]
    url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{spec['file']}"
    download_verified(url, path, spec["size"], spec["sha256"], cancel, progress)
    write_json(path.with_suffix(".source.json"), spec)
    return str(path)


def install_runtime(root, cancel, progress):
    from engine import check_cancel
    root = Path(root) / "llama-b11669-cpu-x64"
    ensure_directory(root)
    archive = download_verified(RUNTIME["url"], root / "runtime.zip", RUNTIME["size"], RUNTIME["sha256"], cancel, progress)
    with zipfile.ZipFile(archive) as zip_file:
        for info in zip_file.infolist():
            check_cancel(cancel)
            target = (root / info.filename).resolve()
            if not target.is_relative_to(root.resolve()) or ":" in info.filename or "\\" in info.filename:
                raise ValueError("Ungültiger Pfad im Laufzeitpaket.")
            if info.is_dir():
                ensure_directory(target)
                continue
            payload = zip_file.read(info)
            if target.is_file() and target.stat().st_size == len(payload):
                if checksum(target, cancel) == hashlib.sha256(payload).hexdigest():
                    continue
            ensure_directory(target.parent)
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as temp:
                temp.write(payload)
                temporary = Path(temp.name)
            try:
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
    matches = list(root.rglob("llama-server.exe"))
    if len(matches) != 1:
        raise ValueError("Keine eindeutige llama-server.exe im Laufzeitpaket.")
    return str(matches[0])


def speech_manifest(folder):
    """Custom models need an explicit manifest; never guess architecture from file names."""
    folder = Path(folder)
    path = folder / "speech-model.json"
    if not path.exists():
        return None
    spec = json.loads(path.read_text(encoding="utf-8"))
    source = Path(spec.get("source_folder", folder))
    if not source.is_absolute():
        raise ValueError("Der Modell-Quellordner muss ein absoluter Pfad sein.")
    if spec.get("backend") not in {"nemo_transducer", "whisper"}:
        raise ValueError("Unterstützte Sprachmodell-Anbindungen: nemo_transducer und whisper (sherpa-onnx).")
    fields = ["encoder", "decoder", "tokens"] + (["joiner"] if spec["backend"] == "nemo_transducer" else [])
    for field in fields:
        value = spec.get(field)
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ValueError(f"Modellbeschreibung: relativer Dateiname für {field} fehlt.")
        target = (source / value).resolve()
        if not target.is_relative_to(source.resolve()) or not target.is_file() or target.stat().st_size == 0:
            raise ValueError(f"Modelldatei fehlt oder liegt außerhalb des Ordners: {field}")
    spec["_root"] = str(source)
    return spec


def discover_speech(roots):
    found, seen = [], set()
    for root in roots:
        root = Path(root)
        candidates = [root]
        try:
            candidates += [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            pass
        for folder in candidates:
            key = str(folder.resolve()).casefold()
            if key in seen:
                continue
            seen.add(key)
            try:
                spec = speech_manifest(folder)
                if spec:
                    found.append((f"{spec.get('name', folder.name)} · {spec.get('version', 'lokal')}", str(folder)))
                elif all((folder / n).is_file() for n in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")):
                    found.append(("Parakeet DE · Empfohlen (Prüfung beim Laden)", str(folder)))
            except (ValueError, OSError, TypeError):
                pass
    return found
