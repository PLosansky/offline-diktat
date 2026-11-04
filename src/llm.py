"""Optional managed llama.cpp CPU process. Only loopback receives text."""
from pathlib import Path
import json
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.request
import urllib.error

from engine import Cancelled, check_cancel


class LocalLLM:
    def __init__(self):
        self.process = None
        self.signature = None
        self.last_used = time.monotonic()
        self.lock = threading.Lock()
        # Loopback HTTP needs neither proxy discovery nor an HTTPS/SSL context.
        # An optional text feature must not depend on TLS during application startup.
        self.opener = urllib.request.OpenerDirector()
        self.opener.add_handler(urllib.request.HTTPHandler())
        self.opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
        self.opener.add_handler(urllib.request.HTTPErrorProcessor())

    def stop(self):
        with self.lock:
            process, self.process = self.process, None
            self.signature = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def request(self, route, body=None, timeout=10):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + route, data=data,
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not echo server responses containing the user's original prompt.
            raise RuntimeError(f"Lokale Text-KI meldet HTTP {exc.code}. Modell, Kontextgröße und Laufzeit prüfen.") from exc

    def start(self, cfg, cancel, progress):
        signature = (cfg["llm_runtime"], cfg["llm_model"], cfg["llm_threads"], cfg["llm_context"])
        if self.process and self.process.poll() is None and self.signature == signature:
            return
        self.stop()
        executable, model = Path(signature[0]), Path(signature[1])
        if not executable.is_file() or executable.name.lower() != "llama-server.exe":
            raise ValueError("Bitte unter Einstellungen → Text-KI die CPU-Laufzeit herunterladen oder llama-server.exe auswählen.")
        if not model.is_file():
            raise ValueError("Bitte ein GGUF-Textmodell herunterladen oder auswählen.")
        with model.open("rb") as f:
            if f.read(4) != b"GGUF":
                raise ValueError("Die ausgewählte Datei ist kein GGUF-Modell.")
        check_cancel(cancel)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        self.key = secrets.token_urlsafe(32)
        args = [str(executable.resolve()), "-m", str(model.resolve()), "--host", "127.0.0.1",
                "--port", str(port), "--api-key", self.key, "-ngl", "0", "--threads", str(signature[2]),
                "--ctx-size", str(signature[3]), "--parallel", "1", "--jinja", "--reasoning-budget", "0",
                "--no-context-shift"]
        progress(0, "Text-KI wird auf der CPU geladen …")
        with self.lock:
            check_cancel(cancel)
            self.process = subprocess.Popen(args, cwd=executable.parent,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            process = self.process
            self.signature = signature
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            check_cancel(cancel)
            if process.poll() is not None:
                raise RuntimeError("Text-KI konnte nicht starten. CPU-Kompatibilität, freien RAM und GGUF-Modell prüfen.")
            try:
                if self.request("/health", timeout=1).get("status") == "ok":
                    return
            except (OSError, RuntimeError):
                pass
            if cancel.wait(0.15):
                raise Cancelled("Abgebrochen.")
        self.stop()
        raise RuntimeError("Das Laden des Textmodells hat zu lange gedauert.")

    def rewrite(self, cfg, messages, cancel, progress=lambda p, s: None):
        started = time.monotonic()
        try:
            self.start(cfg, cancel, progress)
            check_cancel(cancel)
            # Count the actual rendered chat template, not characters or guessed word counts.
            prompt = self.request("/apply-template", {"messages": messages,
                "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
            tokens = self.request("/tokenize", {"content": prompt, "add_special": True})["tokens"]
            available = cfg["llm_context"] - len(tokens) - 64
            if available < 256:
                raise ValueError("Dieser Text ist für die gewählte Kontextgröße zu lang. Einen Abschnitt markieren oder die Kontextgröße erhöhen. Es wurde nichts abgeschnitten.")
            progress(20, "Text wird bearbeitet … Abbrechen ist jederzeit möglich.")
            qwen35 = "qwen3.5" in Path(cfg.get("llm_model", "")).name.casefold()
            small35 = qwen35 and "0.8b" in Path(cfg.get("llm_model", "")).name.casefold()
            result = self.request("/v1/chat/completions", {"messages": messages,
                "temperature": 1.0 if small35 else (0.3 if qwen35 else 0.7),
                "top_p": 1.0 if small35 else 0.8,
                "top_k": 20, "min_p": 0.0, "presence_penalty": 2.0 if small35 else 0.0,
                "repeat_penalty": 1.0, "seed": 42,
                "max_tokens": min(4096, available), "stream": False,
                "chat_template_kwargs": {"enable_thinking": False}}, timeout=900)
            check_cancel(cancel)
            choice = result["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Die KI-Antwort wurde nicht vollständig abgeschlossen. Bitte einen kürzeren Abschnitt bearbeiten. Das Original bleibt erhalten.")
            content = choice["message"].get("content", "").strip()
            if not content or "<think>" in content or "</think>" in content:
                raise ValueError("Kein verwendbarer Text erhalten. Bitte Modell oder Vorlage prüfen.")
            self.last_used = time.monotonic()
            return content, time.monotonic() - started
        except Exception:
            self.stop()
            if cancel.is_set():
                raise Cancelled("Bearbeitung abgebrochen. Original erhalten.")
            raise
        finally:
            if not cfg.get("llm_keep_loaded", False):
                self.stop()

    def idle(self, minutes):
        if self.process and time.monotonic() - self.last_used > minutes * 60:
            self.stop()
