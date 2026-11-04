"""Explicit review boundary: generation never types or changes the clipboard."""
import threading
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QTextEdit, QPushButton, QSplitter, QWidget)
from text_tools import PROFILES, messages


class Review(QDialog):
    def __init__(self, owner, text, profile="Korrigieren"):
        super().__init__(owner)
        self.owner = owner
        self.original = text
        self.cancel_event = threading.Event()
        self.busy = False
        self.copy_after = False
        self.setWindowTitle("Text-KI · Vorschau und Freigabe")
        self.resize(1000, 720)
        box = QVBoxLayout(self)
        box.addWidget(QLabel("Original bleibt erhalten. Erst deine Freigabe übernimmt den Vorschlag."))
        row = QHBoxLayout()
        self.profile = QComboBox()
        self.profile.addItems(PROFILES)
        self.templates = {}
        for line in owner.cfg["templates"].splitlines():
            if "=>" in line:
                name, instruction = (s.strip() for s in line.split("=>", 1))
                self.templates["Eigene: " + name] = instruction
        self.profile.addItems(self.templates)
        self.profile.setCurrentText(profile)
        self.tone = QComboBox()
        self.tone.addItems(["Beibehalten", "Sachlich", "Freundlich", "Formell"])
        self.tone.setToolTip("Gewünschter Ton")
        self.length = QComboBox()
        self.length.addItems(["Beibehalten", "Kürzer"])
        self.length.setToolTip("Gewünschte Länge")
        row.addWidget(self.profile, 2)
        row.addWidget(QLabel("Ton:"))
        row.addWidget(self.tone)
        row.addWidget(QLabel("Länge:"))
        row.addWidget(self.length)
        box.addLayout(row)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        for title, attr in [("ORIGINAL", "source"), ("VORSCHLAG · vor Freigabe prüfen", "result")]:
            panel = QWidget()
            layout = QVBoxLayout(panel)
            layout.addWidget(QLabel(title))
            editor = QTextEdit()
            editor.setAcceptRichText(False)
            setattr(self, attr, editor)
            layout.addWidget(editor)
            self.split.addWidget(panel)
        self.source.setPlainText(text)
        self.source.setReadOnly(True)
        box.addWidget(self.split, 1)
        self.status = QLabel("Namen, Zahlen und Verneinungen bitte besonders prüfen.")
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        row = QHBoxLayout()
        self.generate = QPushButton("Vorschlag erstellen")
        self.generate.clicked.connect(self.run)
        self.abort = QPushButton("Verwerfen / Schließen")
        self.abort.clicked.connect(self.reject)
        self.approve = QPushButton("Im Editor übernehmen")
        self.approve.clicked.connect(self.accept)
        self.copy = QPushButton("Freigeben und kopieren")
        self.copy.clicked.connect(self.approve_copy)
        for widget in (self.generate, self.abort, self.approve, self.copy):
            row.addWidget(widget)
        box.addLayout(row)
        self.approve.setEnabled(False)
        self.copy.setEnabled(False)
        for combo in (self.profile, self.tone, self.length):
            combo.currentIndexChanged.connect(self.invalidate)
        self.result.textChanged.connect(self.result_changed)

    def result_changed(self):
        ready = bool(self.result.toPlainText().strip()) and not self.busy
        self.approve.setEnabled(ready)
        self.copy.setEnabled(ready)

    def invalidate(self):
        self.result.clear()

    def run(self):
        self.busy = True
        self.cancel_event.clear()
        self.result.clear()
        self.result.setReadOnly(True)
        self.generate.setEnabled(False)
        for combo in (self.profile, self.tone, self.length):
            combo.setEnabled(False)
        self.abort.setText("Bearbeitung abbrechen")
        self.status.setText("Text-KI arbeitet lokal auf der CPU …")
        request = messages(self.original, self.profile.currentText(), self.tone.currentText(),
                           self.length.currentText(), self.templates.get(self.profile.currentText(), ""))
        self.owner.tasks.run(lambda: self.owner.llm.rewrite(dict(self.owner.cfg), request,
            self.cancel_event), self.finished)

    def finished(self, result, error):
        self.busy = False
        self.generate.setEnabled(True)
        self.result.setReadOnly(False)
        for combo in (self.profile, self.tone, self.length):
            combo.setEnabled(True)
        self.abort.setText("Verwerfen / Schließen")
        if error or self.cancel_event.is_set():
            self.status.setText(str(error) if error else "Abgebrochen. Original bleibt erhalten.")
            return
        text, elapsed = result
        self.result.setPlainText(text)
        numbers_changed = re.findall(r"\d+(?:[.,:]\d+)*", self.original) != re.findall(r"\d+(?:[.,:]\d+)*", text)
        self.status.setText(f"Fertig nach {elapsed:.1f} Sekunden. " +
            ("Zahlen oder Uhrzeiten unterscheiden sich vom Original – bitte vor Freigabe prüfen." if numbers_changed else
             "Vorschlag prüfen und bei Bedarf hier bearbeiten."))

    def accept(self):
        if not self.busy and self.result.toPlainText().strip():
            super().accept()

    def approve_copy(self):
        self.copy_after = True
        self.accept()

    def reject(self):
        if self.busy:
            self.cancel_event.set()
            self.owner.llm.stop()
            self.status.setText("Wird abgebrochen. Original bleibt erhalten …")
            return
        super().reject()
