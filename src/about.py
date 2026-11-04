"""Offline component and license viewer. Network is only used for clicked links."""
from html import escape
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QTabWidget, QSplitter, QListWidget, QTextBrowser, QComboBox)

RESOURCES = Path(__file__).resolve().parent / "resources"


class AboutDialog(QDialog):
    def __init__(self, parent=None, version="1.0"):
        super().__init__(parent)
        self.setWindowTitle("Über Offline-Diktat")
        self.resize(900, 680)
        self.setMinimumSize(760, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        overview = QWidget()
        box = QVBoxLayout(overview)
        box.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Offline-Diktat")
        title.setObjectName("title")
        box.addWidget(title)
        subtitle = QLabel(f"Version {version} · Offline · CPU")
        subtitle.setObjectName("muted")
        box.addWidget(subtitle)
        company = QLabel('Eine Anwendung von <a href="http://Losansky.it" style="color: #6ce0c1;">Losansky.IT</a>')
        company.setOpenExternalLinks(True)
        box.addSpacing(20)
        box.addWidget(company)
        box.addWidget(QLabel("© 2026 Losansky.IT"))
        description = QLabel("Sprechen statt tippen: Aufnahme per Tastenkürzel, lokale Spracherkennung "
                             "und direkte Texteingabe in deine Anwendung. Die Erkennung läuft auf deinem Rechner.")
        description.setWordWrap(True)
        box.addSpacing(16)
        box.addWidget(description)
        credits = QLabel("Die Windows-Oberfläche und Anpassungen verwenden Open-Source-Komponenten. "
                         "Grundlage ist winidi/dictate; das Sprachmodell stammt von NVIDIA und primeline, "
                         "die ONNX-Variante von flozen1981. Die jeweiligen Urheberrechte bleiben erhalten.")
        credits.setWordWrap(True)
        credits.setObjectName("muted")
        box.addSpacing(16)
        box.addWidget(credits)
        box.addStretch()
        hint = QLabel("Alle mitgelieferten Lizenztexte sind im zweiten Reiter auch ohne Internet lesbar. "
                      "Website- und Quellcode-Links öffnen sich erst beim Anklicken im Browser.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        box.addWidget(hint)
        self.tabs.addTab(overview, "Über")

        components_page = QWidget()
        component_layout = QVBoxLayout(components_page)
        component_layout.setContentsMargins(14, 14, 14, 14)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.components = QListWidget()
        self.components.setWordWrap(True)
        self.components.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        split.addWidget(self.components)
        detail = QWidget()
        detail_box = QVBoxLayout(detail)
        detail_box.setContentsMargins(12, 0, 0, 0)
        self.description = QTextBrowser()
        self.description.setOpenExternalLinks(True)
        self.description.setMaximumHeight(200)
        detail_box.addWidget(self.description)
        detail_box.addWidget(QLabel("Lizenztext (offline)"))
        self.license_files = QComboBox()
        self.license_files.setMinimumContentsLength(18)
        self.license_files.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        detail_box.addWidget(self.license_files)
        self.license_text = QTextBrowser()
        self.license_text.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        detail_box.addWidget(self.license_text, 1)
        split.addWidget(detail)
        split.setSizes([240, 610])
        component_layout.addWidget(split, 1)
        self.tabs.addTab(components_page, "Komponenten && Lizenzen")
        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton("Schließen")
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        layout.addLayout(close_row)

        try:
            self.catalog = json.loads((RESOURCES / "components.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.catalog = []
            self.description.setPlainText("Die Komponentenübersicht fehlt. Bitte den vollständigen Programmordner verwenden.")
        for item in self.catalog:
            self.components.addItem(f"{item['name']}\n{item['version']}")
        self.components.currentRowChanged.connect(self.select_component)
        self.license_files.currentIndexChanged.connect(self.select_license)
        if self.catalog:
            self.components.setCurrentRow(0)

    def select_component(self, index):
        if not 0 <= index < len(self.catalog):
            return
        item = self.catalog[index]
        links = " · ".join(f'<a style="color: #6ce0c1;" href="{escape(url, quote=True)}">{escape(label)}</a>'
                           for label, url in item.get("links", []))
        self.description.setHtml(
            f"<b>{escape(item['name'])}</b> · {escape(item['version'])}<br>"
            f"{escape(item['description'])}<br><br>"
            f"<b>Lizenz:</b> {escape(item['license'])}<br>{links}")
        self.license_files.blockSignals(True)
        self.license_files.clear()
        for entry in item["files"]:
            self.license_files.addItem(entry["label"], entry["path"])
        self.license_files.blockSignals(False)
        self.select_license()

    def select_license(self, _index=0):
        relative = self.license_files.currentData()
        if not relative:
            self.license_text.setPlainText("Kein Lizenztext hinterlegt.")
            return
        path = (RESOURCES / relative).resolve()
        if not path.is_relative_to(RESOURCES.resolve()):
            self.license_text.setPlainText("Ungültiger Lizenzpfad.")
            return
        try:
            self.license_text.setPlainText(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            self.license_text.setPlainText("Lizenzdatei fehlt. Bitte den vollständigen Programmordner verwenden.")
