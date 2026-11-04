"""Create user-profile manifests without modifying an imported model folder."""
from pathlib import Path
import uuid
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFileDialog, QDialogButtonBox)
from storage import write_json
from model_store import speech_manifest


class SpeechImport(QDialog):
    def __init__(self, owner, folder, data_root):
        super().__init__(owner)
        self.folder = Path(folder).resolve()
        self.data_root = data_root
        self.profile_path = None
        self.setWindowTitle("Anderes Sprachmodell einrichten")
        self.resize(700, 520)
        box = QVBoxLayout(self)
        label = QLabel("Für sherpa-onnx exportierte ONNX-Modelle. Originale .nemo-, GGUF- oder Safetensors-Dateien "
                       "sind hier nicht geeignet. Die Dateien bleiben unverändert in ihrem Ordner.")
        label.setWordWrap(True)
        box.addWidget(label)
        form = QFormLayout()
        self.name = QLineEdit(self.folder.name)
        self.version = QLineEdit("lokal")
        self.backend = QComboBox()
        self.backend.addItems(["nemo_transducer", "whisper"])
        self.language = QComboBox()
        self.language.addItem("Deutsch", "de")
        self.language.addItem("Englisch", "en")
        self.language.addItem("Automatisch (mehrsprachiges Whisper)", "")
        form.addRow("Anzeigename", self.name)
        form.addRow("Version", self.version)
        form.addRow("Modellfamilie", self.backend)
        form.addRow("Whisper-Sprache", self.language)
        self.files = {}
        for role in ("encoder", "decoder", "joiner", "tokens"):
            combo = QComboBox()
            combo.addItem("Datei auswählen …", None)
            for file in sorted(self.folder.glob("*")):
                if file.is_file() and (file.suffix.lower() in {".onnx", ".ort", ".txt"}):
                    combo.addItem(file.name, file.name)
                    if role in file.stem.lower():
                        combo.setCurrentIndex(combo.count() - 1)
            self.files[role] = combo
            form.addRow(role.title(), combo)
        self.backend.currentTextChanged.connect(lambda value: self.files["joiner"].setEnabled(value != "whisper"))
        box.addLayout(form)
        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        box.addWidget(self.feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def save(self):
        spec = {"name": self.name.text().strip() or self.folder.name, "version": self.version.text(),
                "source_folder": str(self.folder), "backend": self.backend.currentText(),
                "language": self.language.currentData()}
        roles = ["encoder", "decoder", "tokens"] + (["joiner"] if spec["backend"] != "whisper" else [])
        for role in roles:
            value = self.files[role].currentData()
            if not value:
                self.feedback.setText("Bitte die Datei für " + role + " auswählen.")
                return
            spec[role] = value
        folder = Path(self.data_root) / "model-profiles" / uuid.uuid4().hex
        try:
            write_json(folder / "speech-model.json", spec)
            speech_manifest(folder)
        except (OSError, ValueError) as exc:
            self.feedback.setText(str(exc))
            return
        self.profile_path = str(folder)
        self.accept()
