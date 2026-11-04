"""Offline engine, inspired by winidi/dictate (MIT). See THIRD_PARTY.md."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.request
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from storage import ensure_directory, write_json

RATE = 16000
REPO = "flozen1981/parakeet-primeline-onnx"
REVISION = "d548e25b9bfe559aa274f361892dc4ed5d64743a"
# Pinned revision; LFS SHA-256 and Git blob SHA-1 for tokens.txt.
FILES = {
    "encoder.int8.onnx": (1548009, "sha256", "d4232f86718da0330167fb10789d1a35cffe6a60cd58239957943a8d9bc24c63"),
    "encoder.int8.onnx.data": (650776320, "sha256", "d3b0d27912043d38a3c2ce4f2c03124be30bc1ff57d976302908954b2e8fe7bb"),
    "decoder.int8.onnx": (11845275, "sha256", "fb4ddefe200706cabb27ee3fc1c81efa50555a4c8a8e00b663cc795216fb9369"),
    "joiner.int8.onnx": (6355277, "sha256", "8220c0d117d81bdd0d8c770881932ac340f1ce4b36932941d561d11ad1aaffce"),
    "tokens.txt": (102132, "git", "6fc5460dee56572d6b34a19e42a45aeddc245cde"),
}


class Cancelled(Exception):
    pass


def format_dictation(text, trailing_space=True):
    """Apply the separator once, after the complete dictation is recognized."""
    if not text.strip():
        return ""
    return text.rstrip() + " " if trailing_space else text


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled("Abgebrochen.")


def check_file(path: Path, spec, cancel=None):
    size, algorithm, digest = spec
    if not path.is_file() or path.stat().st_size != size:
        raise ValueError(f"Datei fehlt oder hat die falsche Größe: {path.name}")
    h = hashlib.sha256() if algorithm == "sha256" else hashlib.sha1()
    if algorithm == "git":
        h.update(f"blob {size}\0".encode())
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            check_cancel(cancel)
            h.update(block)
    if h.hexdigest() != digest:
        raise ValueError(f"Prüfsumme stimmt nicht: {path.name}. Bitte erneut herunterladen.")


def validate_model(folder, progress=lambda p, s: None, cancel=None):
    folder = Path(folder)
    from model_store import speech_manifest
    custom = speech_manifest(folder)
    if custom:
        folder_root = Path(custom["_root"])
        for name, digest in custom.get("sha256", {}).items():
            target = (folder_root / name).resolve()
            if not target.is_relative_to(folder_root.resolve()):
                raise ValueError("Ungültiger Modellpfad.")
            from model_store import checksum
            if checksum(target, cancel) != digest:
                raise ValueError(f"Prüfsumme stimmt nicht: {name}")
        check_cancel(cancel)
        progress(90, "Kompatibilität des importierten Modells wird separat geprüft …")
        probe_model(folder, cancel)
        progress(100, "Lokales Modell konnte auf der CPU geladen werden.")
        return folder
    for i, (name, spec) in enumerate(FILES.items()):
        check_cancel(cancel)
        progress(i * 100 // len(FILES), f"Prüfe {name} …")
        check_file(folder / name, spec, cancel)
    progress(100, "Modelldateien geprüft.")
    return folder


def probe_model(folder, cancel):
    # Native loaders may abort on unsupported models. Isolate the first load so the GUI survives.
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).with_name("app.py")))
    command += ["--probe-model", str(folder)]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + 180
    try:
        while process.poll() is None:
            check_cancel(cancel)
            if time.monotonic() > deadline:
                raise ValueError("Das importierte Modell konnte nicht innerhalb von drei Minuten geladen werden.")
            time.sleep(0.1)
        if process.returncode != 0:
            raise ValueError("Das importierte Modell ist mit dieser CPU/Laufzeit nicht kompatibel oder unvollständig. Das bisherige Modell bleibt auswählbar.")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def download_model(folder, progress=lambda p, s: None, cancel=None):
    folder = Path(folder)
    ensure_directory(folder)
    total = sum(x[0] for x in FILES.values())
    completed = 0
    for name, spec in FILES.items():
        check_cancel(cancel)
        target = folder / name
        try:
            check_file(target, spec, cancel)
        except (ValueError, OSError):
            partial = target.with_name(name + ".download")
            try:
                url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
                request = urllib.request.Request(url, headers={"User-Agent": "Offline-Diktat/1.0"})
                with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as out:
                    count = 0
                    while True:
                        check_cancel(cancel)
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        out.write(block)
                        count += len(block)
                        progress(int(100 * (completed + count) / total),
                                 f"{name} · {(completed + count) / 1e6:.0f} / {total / 1e6:.0f} MB")
                check_file(partial, spec, cancel)
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        completed += spec[0]
        progress(int(completed * 100 / total), f"{name} vollständig.")
    return folder


def split_audio(audio, max_seconds=60):
    """Cut near low energy; preserve all samples. Bound each inference's memory."""
    maximum = int(max_seconds * RATE)
    window = int(0.4 * RATE)
    search = min(int(10 * RATE), maximum // 2)
    if maximum < window * 2:
        raise ValueError("Abschnitt zu kurz")
    offset = 0
    while len(audio) - offset > maximum:
        tail = audio[offset + maximum - search:offset + maximum]
        n = len(tail) // window
        energy = np.mean(tail[:n * window].reshape(n, window).astype(np.float32) ** 2, axis=1)
        cut = maximum - search + int(energy.argmin()) * window + window // 2
        yield audio[offset:offset + cut]
        offset += cut
    if offset < len(audio):
        yield audio[offset:]


class Recognizer:
    def __init__(self, folder, threads=4):
        import sherpa_onnx
        folder = Path(folder)
        from model_store import speech_manifest
        spec = speech_manifest(folder)
        if spec:
            folder = Path(spec["_root"])
        self.chunk_seconds = 60
        if spec and spec["backend"] == "whisper":
            self.chunk_seconds = 25
            self.rec = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(folder / spec["encoder"]), decoder=str(folder / spec["decoder"]),
                tokens=str(folder / spec["tokens"]), language=spec.get("language", "de"),
                task="transcribe", num_threads=threads, provider="cpu")
        elif spec:
            self.rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                **{key: str(folder / spec[key]) for key in ("encoder", "decoder", "joiner", "tokens")},
                model_type="nemo_transducer", num_threads=threads, provider="cpu", decoding_method="greedy_search")
        else:
            self.rec = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(folder / "encoder.int8.onnx"),
            decoder=str(folder / "decoder.int8.onnx"),
            joiner=str(folder / "joiner.int8.onnx"),
            tokens=str(folder / "tokens.txt"),
            model_type="nemo_transducer", num_threads=threads,
            provider="cpu", decoding_method="greedy_search",
        )
        warmup = self.rec.create_stream()
        warmup.accept_waveform(RATE, np.zeros(RATE, dtype=np.float32))
        self.rec.decode_stream(warmup)

    def decode(self, audio):
        if not len(audio):
            return ""
        peak = float(np.abs(audio).max())
        if peak < 0.0001:
            return ""
        if peak < 0.5:
            audio = audio * min(30.0, 0.5 / peak)
        stream = self.rec.create_stream()
        stream.accept_waveform(RATE, np.ascontiguousarray(audio))
        self.rec.decode_stream(stream)
        return stream.result.text.strip()

    def transcribe(self, audio, progress=lambda p, s: None, cancel=None):
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        audio = audio.reshape(-1)
        parts, processed = [], 0
        for chunk in split_audio(audio, getattr(self, "chunk_seconds", 60)):
            check_cancel(cancel)
            text = self.decode(chunk)
            if not text and len(chunk) > 20 * RATE:
                retries = []
                for small in split_audio(chunk, 20):
                    check_cancel(cancel)
                    retries.append(self.decode(small))
                text = " ".join(t for t in retries if t)
            parts.append(text)
            processed += len(chunk)
            progress(int(processed * 100 / max(1, len(audio))), "Sprache wird erkannt …")
        check_cancel(cancel)
        return " ".join(p for p in parts if p)


class Recorder:
    """RAM only. No audio or transcript ever goes to a log or temp file."""
    def __init__(self, device=None, seconds_limit=60 * 60):
        self.device = device
        self.limit = seconds_limit * RATE
        self.frames = []
        self.count = 0
        self.peak = 0.0
        self.overflow = False
        self.full = False
        self.stream = None

    def start(self):
        import sounddevice as sd
        self.frames, self.count = [], 0
        self.peak, self.overflow, self.full = 0.0, False, False
        def callback(data, frames, timing, status):
            self.overflow |= bool(status.input_overflow)
            self.peak = float(np.max(np.abs(data.astype(np.float32)))) / 32768.0
            room = self.limit - self.count
            if room > 0:
                copy = data[:room, 0].copy()
                self.frames.append(copy)
                self.count += len(copy)
            self.full = self.count >= self.limit
        self.stream = sd.InputStream(device=self.device, samplerate=RATE, channels=1,
                                     dtype="int16", callback=callback)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            self.stream = None
            raise

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None
        audio = np.concatenate(self.frames) if self.frames else np.empty(0, dtype=np.int16)
        self.frames = []
        return audio


def load_json(path, default):
    try:
        return {**default, **json.loads(Path(path).read_text(encoding="utf-8"))}
    except (OSError, ValueError, TypeError):
        return dict(default)


def save_json(path, data):
    write_json(path, data)
