"""Optional daily release checks using independent background tasks."""
import time
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox
import updates
import engine


class UpdateSupport:
    def init_updates(self, data, version, testing):
        self.update_data, self.update_version = data, version
        self.update_busy = False
        self.update_available = None
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.auto_update_check)
        if not testing:
            self.update_timer.start(60 * 60 * 1000)
            QTimer.singleShot(15000, self.auto_update_check)

    def auto_update_check(self):
        if (self.cfg.get("check_updates", True) and self.cfg.get("setup") and
                self.state == "idle" and time.time() - self.cfg.get("update_checked", 0) >= 86400):
            self.check_updates(manual=False)

    def check_updates(self, checked=False, manual=True):
        if self.update_busy:
            return
        self.update_busy = True
        self.cfg["update_checked"] = time.time()
        try:
            engine.save_json(self.update_data / "settings.json", self.cfg)
        except OSError:
            pass
        def done(release, error):
            self.update_busy = False
            if error:
                if manual:
                    QMessageBox.information(self, "Updateprüfung", str(error))
                return
            if not release:
                if manual:
                    QMessageBox.information(self, "Updateprüfung", "Du verwendest die aktuelle veröffentlichte Version.")
                return
            self.update_available = release
            if not manual:
                # No modal interruption while dictating or editing a document.
                self.update_button.setText(f"Update {release['version']} verfügbar")
                return
            prompt = QMessageBox(self)
            prompt.setWindowTitle("Update verfügbar")
            prompt.setText(f"Offline-Diktat {release['version']} ist verfügbar ({release['size'] / 1024**2:.0f} MB).\n\n"
                "Jetzt herunterladen? Die Installation erfolgt anschließend manuell. Einstellungen und Modelle bleiben erhalten.")
            prompt.setDetailedText(release["notes"])
            prompt.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if prompt.exec() == QMessageBox.StandardButton.Yes:
                self.update_busy = True
                self.update_button.setText("Update wird heruntergeladen …")
                self.tasks.run(lambda: updates.download(release, self.update_data / "updates"), downloaded)
        def downloaded(path, error):
            self.update_busy = False
            self.update_button.setText("Nach Updates suchen")
            if error:
                QMessageBox.warning(self, "Update-Download", str(error))
                return
            QMessageBox.information(self, "Update heruntergeladen", "Download und SHA-256-Prüfsumme geprüft.\n\n"
                "Die Anwendung vollständig beenden und das ZIP in einen neuen Programmordner entpacken. "
                "Vorhandene Modelle übernehmen. Bei geschützten Firmenordnern die IT um Installation bitten.\n\n" + path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.update_data / "updates")))
        self.tasks.run(lambda: updates.latest(self.update_version), done)
