"""Additional settings pages; reused with the existing microphone/hotkey controls."""
import os
import threading
from pathlib import Path
from PySide6.QtWidgets import (QLabel, QComboBox, QCheckBox, QSpinBox, QFormLayout,
    QLineEdit, QPushButton, QTextEdit, QFileDialog)
import model_store
from text_tools import replacements, messages


class AdvancedSettings:
    def add_advanced_pages(self):
        box = self.new_page()
        box.addWidget(QLabel("Textausgabe und Verlauf"))
        form = QFormLayout()
        self.output_mode = QComboBox()
        self.output_mode.addItems(["Direkt einfügen", "Im Editor bearbeiten"])
        self.output_mode.setCurrentIndex(int(self.cfg["output_mode"] == "editor"))
        form.addRow("Standard", self.output_mode)
        self.notifications = QComboBox()
        self.notifications.addItems(["Alle", "Nur Fehler", "Keine"])
        self.notifications.setCurrentText(self.cfg["notifications"])
        form.addRow("Benachrichtigungen", self.notifications)
        self.history_limit = QSpinBox()
        self.history_limit.setRange(1, 500)
        self.history_limit.setValue(self.cfg["history_limit"])
        form.addRow("Maximale Einträge", self.history_limit)
        self.history_days = QSpinBox()
        self.history_days.setRange(0, 365)
        self.history_days.setSpecialValueText("Kein Zeitlimit")
        self.history_days.setValue(self.cfg["history_days"])
        form.addRow("Aufbewahrung in Tagen", self.history_days)
        self.drafts = QCheckBox("Aktuellen Entwurf lokal sichern und nach Neustart wiederherstellen")
        self.drafts.setChecked(self.cfg["draft_protection"])
        self.close_tray = QCheckBox("Beim Schließen im Infobereich weiterlaufen")
        self.close_tray.setChecked(self.cfg["close_to_tray"])
        box.addLayout(form)
        box.addWidget(self.drafts)
        box.addWidget(self.close_tray)
        self.check_updates = QCheckBox("Automatisch täglich nach Updates suchen (Verbindung zu GitHub)")
        self.check_updates.setChecked(self.cfg.get("check_updates", True))
        box.addWidget(self.check_updates)
        update_info = QLabel("Es werden nur Versionsinformationen abgerufen, keine Diktate übertragen. "
                            "Downloads erfolgen erst nach Bestätigung. Manuelle Prüfung im Hauptfenster.")
        update_info.setWordWrap(True)
        box.addWidget(update_info)
        label = QLabel("Verlauf und Entwurf sind separate, unverschlüsselte lokale Textdateien im Benutzerprofil. "
                       "Ohne Aktivierung bleiben Texte nur für diese Sitzung erhalten. Audio wird nicht gespeichert.")
        label.setWordWrap(True)
        box.addWidget(label)
        box.addStretch()

        box = self.new_page()
        box.addWidget(QLabel("Optionale Text-KI · lokal · CPU · Freigabe vor Übernahme"))
        self.llm_enabled = QCheckBox("Text-KI aktivieren")
        self.llm_enabled.setChecked(self.cfg["llm_enabled"])
        box.addWidget(self.llm_enabled)
        self.llm_choice = QComboBox()
        self.llm_choice.addItems([x["name"] for x in model_store.LLM_MODELS])
        box.addWidget(self.llm_choice)
        self.llm_info = QLabel()
        self.llm_info.setWordWrap(True)
        box.addWidget(self.llm_info)
        self.llm_choice.currentIndexChanged.connect(self.model_info)
        self.model_info()
        self.llm_path = QLineEdit(self.cfg["llm_model"])
        box.addWidget(QLabel("Aktive GGUF-Datei (wird beim nächsten KI-Aufruf verwendet)"))
        box.addWidget(self.llm_path)
        self.installed_llm = QComboBox()
        self.installed_llm.addItem("Vorhandene Textmodelle auswählen …", None)
        roots = {self.data_root / "text-models", Path(self.cfg["llm_model"]).parent if self.cfg["llm_model"] else self.data_root / "text-models"}
        for root in roots:
            if root.is_dir():
                for path in sorted(root.glob("*.gguf")):
                    self.installed_llm.addItem(path.name, str(path))
        self.installed_llm.currentIndexChanged.connect(lambda: self.llm_path.setText(self.installed_llm.currentData()) if self.installed_llm.currentData() else None)
        box.addWidget(self.installed_llm)
        self.llm_download = QPushButton("Gewähltes Textmodell herunterladen / vorhandenes prüfen")
        self.llm_download.clicked.connect(lambda: self.optional_job("model"))
        box.addWidget(self.llm_download)
        self.llm_import = QPushButton("Vorhandene GGUF-Datei auswählen …")
        self.llm_import.clicked.connect(self.pick_llm)
        box.addWidget(self.llm_import)
        self.runtime_path = QLineEdit(self.cfg["llm_runtime"])
        box.addWidget(QLabel("CPU-Laufzeit · llama-server.exe"))
        box.addWidget(self.runtime_path)
        self.runtime_download = QPushButton("CPU-Laufzeit herunterladen (llama.cpp b11669 · 20 MB)")
        self.runtime_download.clicked.connect(lambda: self.optional_job("runtime"))
        box.addWidget(self.runtime_download)
        self.runtime_import = QPushButton("Vorhandene llama-server.exe auswählen …")
        self.runtime_import.clicked.connect(self.pick_runtime)
        box.addWidget(self.runtime_import)
        form = QFormLayout()
        self.llm_threads = QSpinBox()
        self.llm_threads.setRange(1, max(1, os.cpu_count() or 1))
        self.llm_threads.setValue(self.cfg["llm_threads"])
        form.addRow("CPU-Threads Text-KI", self.llm_threads)
        self.context = QComboBox()
        for size in (2048, 4096, 8192, 16384):
            self.context.addItem(str(size), size)
        self.context.setCurrentText(str(self.cfg["llm_context"]))
        form.addRow("Kontextgröße (mehr benötigt mehr RAM)", self.context)
        box.addLayout(form)
        self.keep_loaded = QCheckBox("Modell für weitere Bearbeitungen geladen lassen (max. 5 Minuten inaktiv)")
        self.keep_loaded.setChecked(self.cfg["llm_keep_loaded"])
        box.addWidget(self.keep_loaded)
        self.benchmark = QPushButton("Lokalen Kurztest ausführen")
        self.benchmark.clicked.connect(lambda: self.optional_job("benchmark"))
        box.addWidget(self.benchmark)
        box.addStretch()

        box = self.new_page()
        box.addWidget(QLabel("Persönliches Wörterbuch · eine Ersetzung pro Zeile"))
        self.dictionary = QTextEdit()
        self.dictionary.setAcceptRichText(False)
        self.dictionary.setPlaceholderText("Losanski => Losansky\ncheck em kay => Checkmk")
        self.dictionary.setPlainText(self.cfg["dictionary"])
        box.addWidget(self.dictionary)
        box.addWidget(QLabel("Eigene KI-Vorlagen · Name => Bearbeitungsvorgabe"))
        self.templates_edit = QTextEdit()
        self.templates_edit.setAcceptRichText(False)
        self.templates_edit.setPlaceholderText("Supportantwort => Formuliere als kurze, freundliche Supportantwort.")
        self.templates_edit.setPlainText(self.cfg["templates"])
        box.addWidget(self.templates_edit)

    def model_info(self):
        model = model_store.LLM_MODELS[self.llm_choice.currentIndex()]
        self.llm_info.setText(f"{model['size']/1e9:.2f} GB Download · {model['ram']}. "
            f"Kontext und Laufzeit verändern den Verbrauch. Quelle: {model['repo']} · Apache-2.0. "
            "Qualität und Geschwindigkeit bitte auf deinem Rechner vergleichen.")

    def pick_llm(self):
        path, _ = QFileDialog.getOpenFileName(self, "Textmodell auswählen", self.llm_path.text(), "GGUF (*.gguf)")
        if path:
            self.llm_path.setText(path)

    def pick_runtime(self):
        path, _ = QFileDialog.getOpenFileName(self, "CPU-Laufzeit auswählen", self.runtime_path.text(), "llama-server.exe (llama-server.exe)")
        if path:
            self.runtime_path.setText(path)

    def optional_config(self):
        return dict(self.cfg, llm_model=self.llm_path.text().strip(), llm_runtime=self.runtime_path.text().strip(),
                    llm_threads=self.llm_threads.value(), llm_context=self.context.currentData(),
                    llm_keep_loaded=self.keep_loaded.isChecked())

    def optional_job(self, kind):
        self.busy = True
        self.optional_kind = kind
        self.cancel_event.clear()
        self.owner.llm.stop()
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.feedback.setText("Bitte warten …")
        cfg = self.optional_config()
        index = self.llm_choice.currentIndex()
        self.update_step()
        def work():
            if kind == "model":
                return model_store.download_llm(index, self.data_root / "text-models", self.cancel_event, self.tasks.progress.emit)
            if kind == "runtime":
                return model_store.install_runtime(self.data_root / "runtime", self.cancel_event, self.tasks.progress.emit)
            return self.owner.llm.rewrite(cfg, messages("hallo wir haben das problem geprüft und melden uns morgen wieder", "Korrigieren"),
                                           self.cancel_event, self.tasks.progress.emit)
        def done(result, error):
            self.busy = False
            self.optional_kind = None
            if error:
                self.feedback.setText(str(error))
            elif kind == "model":
                self.llm_path.setText(result)
                self.feedback.setText("Textmodell vollständig und Prüfsumme bestätigt.")
            elif kind == "runtime":
                self.runtime_path.setText(result)
                self.feedback.setText("CPU-Laufzeit installiert. Keine Administratorrechte erforderlich.")
            else:
                self.feedback.setText(f"Kurztest: {result[1]:.1f} Sekunden einschließlich Laden. Ergebnis: {result[0]} "
                                      "Dies ist kein allgemeiner Hardware-Benchmark.")
            self.update_step()
        self.tasks.run(work, done)

    def save_advanced(self):
        rules = self.dictionary.toPlainText()
        replacements("", rules)
        templates = self.templates_edit.toPlainText()
        for line in templates.splitlines():
            if line.strip() and ("=>" not in line or not all(x.strip() for x in line.split("=>", 1))):
                raise ValueError("KI-Vorlagen: pro Zeile 'Name => Bearbeitungsvorgabe' eintragen.")
        self.cfg.update(self.optional_config())
        self.cfg.update(output_mode="editor" if self.output_mode.currentIndex() else "direct",
            notifications=self.notifications.currentText(), history_limit=self.history_limit.value(),
            history_days=self.history_days.value(), draft_protection=self.drafts.isChecked(),
            close_to_tray=self.close_tray.isChecked(), llm_enabled=self.llm_enabled.isChecked(),
            dictionary=rules, templates=templates, check_updates=self.check_updates.isChecked())
