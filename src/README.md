# Offline-Diktat 1.2.0 · Losansky.IT

## Neu in 1.2.0

- Text-KI mit freier Anweisung und mehreren aufeinanderfolgenden Bearbeitungsschritten.
  Der nächste Wunsch bezieht sich auf den aktuellen Vorschlag einschließlich Handkorrekturen.
  Original, Verlauf und Vorschlag bleiben sichtbar. Die Antwort erscheint nach Abschluss
  der Berechnung, nicht Wort für Wort. Erst Freigabe übernimmt oder kopiert den Text.
- Drei Schnellvorlagen sowie eigene gespeicherte Vorlagen als optionale Eingabehilfen.
  Mit „Neu vom Original beginnen“ wird der Bearbeitungsverlauf zurückgesetzt.
  Der Verlauf bleibt ausschließlich im Dialog und wird nicht gespeichert.
- Der Haken für Sprachbefehle wurde aus dem Hauptfenster entfernt.
- Automatische Updateprüfung einmal täglich nach abgeschlossener Einrichtung,
  abschaltbar unter Einstellungen → Textausgabe und Verlauf. Manuelle Prüfung im Hauptfenster.
  Dabei wird GitHub kontaktiert, jedoch kein Diktat übertragen. Ohne Internet funktioniert
  das Diktieren weiter; automatische Prüffehler öffnen kein Fenster.
- Updates kommen aus stabilen GitHub Releases von PLosansky/offline-diktat.
  Download nur nach Bestätigung; Größen- und SHA-256-Prüfung vor Bereitstellung.
  Die Prüfsumme stammt von GitHub und ist keine unabhängige Herausgebersignatur.
  Downloads liegen unter %LOCALAPPDATA%/DictateOffline/updates.
  Die Anwendung ersetzt keine laufende EXE und benötigt keine Administratorrechte.

### Update installieren

Die Anwendung über „Beenden“ vollständig schließen. Das Update-ZIP in einen neuen
Ordner entpacken und die neue Offline-Diktat.exe starten. Modelle aus dem bisherigen
Programmordner übernehmen oder deren bisherigen Pfad in den Einstellungen auswählen.
Einstellungen im Benutzerprofil bleiben erhalten. Bei geschützten Programmordnern
übernimmt die Firmen-IT das Ersetzen. Version 1.1.0 benötigt dieses erste Update manuell.

### Neue Version veröffentlichen

Eine Versionsmarkierung allein genügt nicht: Ein öffentliches, stabiles GitHub Release
mit dem passenden Windows-Paket ist erforderlich. Für Version X.Y.Z heißt das Paket
`Offline-Diktat-X.Y.Z-Update.zip`, der Tag `vX.Y.Z`. Der Updater verlangt den
SHA-256-Digest des GitHub-Release-Assets; Vorabversionen werden übersprungen.
Das Paket enthält Bibliotheken, Lizenztexte und Quellcode, aber keine persönlichen
Daten oder Modellgewichte. Modelle und die llama.cpp-Laufzeit haben eigene Versionen
und werden nicht automatisch durch die Updateprüfung verändert.

## Neu in 1.1.0

- Aufnahme per Hotkey oder Start-/Stopp-Button. Im eigenen Fenster landet das
  Ergebnis ohne Einfügehinweis im Editor. Externe Direktdiktate bleiben möglich.
- Neue Entwürfe, Weiterdiktieren, Rückgängig und Original wiederherstellen.
- Getrennter Einrichtungsassistent und sechs Einstellungsbereiche.
- Mehrere Sprachmodelle verwalten; lokale NeMo-/Whisper-ONNX-Modelle importieren.
- Optionale CPU-Text-KI mit Qwen3 1.7B, Qwen3.5 0.8B und Qwen3.5 4B zur Auswahl.
  Qwen3.5 0.8B ist wegen schwacher Ergebnisse im Beispieltest experimentell markiert.
- Korrigieren, Glätten, professioneller Stil, Umformulieren, technische
  Dokumentation, Strukturieren, Zusammenfassen, Deutsch/Englisch übersetzen,
  eigene Vorlagen, Ton und Länge. Ergebnisse sind Vorschläge, keine Garantie.
- Original und Vorschlag nebeneinander; Freigabe vor Übernahme oder Kopieren.
  Eine Auswahl im Editor begrenzt die Bearbeitung auf diesen Abschnitt.
- Einfügen des Editorinhalts nach drei Sekunden: Zielfeld anklicken; ESC bricht ab.
- Persönliches Wörterbuch mit festen Ersetzungen (`Erkannt => Gewünscht`).
- Einmalig aktivierbarer Sprachbefehlsmodus; normale Diktate lösen keine Befehle aus.
- Optionale Entwurfssicherung, konfigurierbare Verlaufsgröße und Aufbewahrungszeit.
  Bereits vollständig kopierte Entwürfe werden nicht erneut wiederhergestellt.
- Alle / nur Fehler / keine Benachrichtigungen; Schließen in den Infobereich einstellbar.

Anleitung zur Modellwahl, Offline-Einrichtung und Grenzen: **MODELLE.md**.
Die Text-KI ist standardmäßig deaktiviert. Modellgewichte sind separate Downloads.
Das bisherige Sprachmodell und die Einstellungen aus 1.0.1 werden weiterverwendet.

## Aktualisieren

Die alte Anwendung über das Mikrofon-Symbol vollständig beenden. Den gesamten
neuen Programmordner entpacken. Bei Übernahme in eine bestehende Installation
alle enthaltenen Dateien ersetzen und den vorhandenen Ordner `models` behalten.
In einem geschützten Firmen-Programmordner muss die IT das Update einspielen.
Die Anwendung selbst benötigt weiterhin nur Schreibrechte im Benutzerprofil.

Die gebauten Pakete enthalten eine CPU-Laufzeit unter `runtime`. Für einen Rechner
ohne Internet ein GGUF-Modell zusätzlich nach `text-models` kopieren oder in den
Einstellungen auswählen. DLLs neben llama-server.exe müssen erhalten bleiben.

Im Editor setzt **Aufnahme starten** einen neuen Entwurf an. **Weiterdiktieren**
ergänzt den aktuellen Text. Ein laufender Vorgang sperrt die Textbearbeitung bis
zum Abschluss, damit keine Handkorrekturen überschrieben werden.

Der optionale Entwurfsschutz sichert nur den aktuell ausgewählten, noch nicht
vollständig kopierten Entwurf. Dauerhafter Verlauf sichert zusätzlich die letzten
Einträge. Beide Speicherungen liegen unverschlüsselt im Benutzerprofil und sind
standardmäßig ausgeschaltet. Änderungen werden nach kurzer Verzögerung gespeichert.

## Fehlerkorrektur 1.0.1

Die Benutzerordnerprüfung verwendet unter Windows die nativen Ordnerattribute.
Das verhindert WinError 183, wenn ein vorhandener Ordner über die Python-Prüfung
nicht korrekt als Verzeichnis erkannt wird. Der Programmordner wird nicht
beschrieben. Einstellungen werden über eine eindeutige temporäre Datei im selben
Benutzerordner atomar ersetzt. Fehlgeschlagene Schreibvorgänge erhalten die zuvor
gespeicherten Einstellungen und werden verständlich angezeigt.

Der Start prüft Schreib- und Ersetzungsrechte ausschließlich mit eigenen
Testdateien im Benutzerordner. Es werden keine Rechte verändert, keine
Sicherheitsrichtlinien umgangen und keine Benutzerdateien gelöscht.

Eine deutsche Windows-Oberfläche für lokale CPU-Spracherkennung mit Parakeet DE.
Basierend auf Ansätzen aus winidi/dictate. Herkunft und Lizenzen: THIRD_PARTY.md.

## Änderungen gegenüber der ersten Testversion

- Produktname Offline-Diktat und Version 1.0 (intern 1.0.0).
- Echte Statusleiste: © 2026 Losansky.IT mit Website-Link; Version rechts.
- Über-Fenster mit Herkunft, Komponenten, Versionen und offline lesbaren Lizenzen.
- Abschaltbare Option „Leerzeichen nach jedem Diktat“, standardmäßig aktiv.
- Anwendungseinstellungen, Modellpfad und optionaler Verlauf bleiben kompatibel.

## Aus dem Quellcode starten

Python 3.12 x64 verwenden, eine virtuelle Umgebung erstellen und die Pakete aus
requirements.txt installieren. Anschließend `python app.py` starten. Der Ordner
resources muss neben app.py liegen. Ein Modellordner kann in der Einrichtung
gewählt oder heruntergeladen werden.

## Windows-Paket erstellen

`build.ps1` erstellt mit PyInstaller eine Anwendung unter
dist/Offline-Diktat/Offline-Diktat.exe. Das Paket beinhaltet die Python-Laufzeit,
die Bibliotheken und Lizenzressourcen. Ein Modell kann zusätzlich im Unterordner
models abgelegt werden. Immer den vollständigen Programmordner verwenden.

## Tests

`python -m unittest discover -s . -p 'test_*.py' -v`

Die Tests prüfen unter anderem Aufteilung langer Aufnahmen, Tastenkürzel,
Fensterwechsel, Textverlauf, Leerzeichen, Offline-Lizenzanzeige, WinError 183,
Erst- und Zweitstart, getrennte Programm-/Benutzerordner sowie Schreibfehler.

## Kompatibilität

Der bisherige Speicherort %LOCALAPPDATA%/DictateOffline und der gleichnamige
Autostart-Eintrag bleiben bewusst erhalten. Das verhindert den Verlust vorhandener
Einstellungen und doppelte Autostarts. Beim Start der EXE wird ein bereits aktivierter
Autostart auf den neuen Programmpfad aktualisiert. Der Sperrmechanismus verhindert,
dass die alte und neue Version im selben Benutzerprofil parallel aufnehmen.

Die bewährte Parakeet-Erkennung bleibt verfügbar. Das abschließende Leerzeichen
wird auf das vollständige Diktat angewendet sowie beim Kopieren und Einfügen aus
dem Editor berücksichtigt. Bei deaktivierter Option wird kein Leerzeichen ergänzt.
