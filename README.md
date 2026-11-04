# Offline-Diktat

Windows-Anwendung von Losansky.IT für lokale, CPU-basierte Spracherkennung.
Aktueller Stand: **1.2.0**.

Aufnahme per Tastenkürzel oder Schaltfläche, Texteingabe in Windows-Anwendungen,
Editor und optional eine lokale Text-KI mit Vorschau und ausdrücklicher Freigabe.
Freie Bearbeitungsanweisungen können im Dialog schrittweise verfeinert werden.
Nach dem Herunterladen oder manuellen Import der Modelle ist der Betrieb offline möglich.
Die abschaltbare Updateprüfung verwendet öffentliche GitHub Releases.

## Entwicklung

Windows und Python 3.12 x64 verwenden. In PowerShell im Repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r src/requirements.txt
.\.venv\Scripts\python.exe src/app.py
```

Tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s src -p 'test_*.py' -v
```

Ein Windows-Paket erstellt `src/build.ps1`. Modellgewichte und die optionale
llama.cpp-Laufzeit werden separat bezogen; sie sind nicht im Repository enthalten.

## Dokumentation und Herkunft

- [Bedienung und Versionshinweise](src/README.md)
- [Modelle und Offline-Einrichtung](src/MODELLE.md)
- [Herkunft und Drittanbieter-Lizenzen](src/THIRD_PARTY.md)
- [Erhaltener MIT-Lizenztext des Ursprungsprojekts](src/LICENSE)

Die Anwendung basiert in Teilen auf Ansätzen aus winidi/dictate. Bestehende
Urheber- und Lizenzhinweise bleiben erhalten. Diese Repository-Einrichtung legt
keine neue Lizenz für eigene Beiträge fest.

Persönliche Einstellungen, Diktate, Verlauf, Modellgewichte, lokale Arbeitsdateien
und erzeugte Programmpakete werden nicht versioniert.
