# Herkunft und Lizenzen

## Optionale Text-KI ab 1.1

- OpenSSL 3.5.8, OpenSSL-Projekt und Mitwirkende: Apache-2.0. Unveränderte
  DLLs der verwendeten Python-Laufzeit für TLS bei Modelldownloads.
  https://github.com/openssl/openssl/tree/openssl-3.5.8
  Lizenz: resources/LICENSES/OpenSSL-3.5.8.txt.

- llama.cpp, ggml-org und Mitwirkende: MIT. CPU-Laufzeit b11669, unverändert.
  https://github.com/ggml-org/llama.cpp/tree/b11669
  Lizenz: resources/LICENSES/llama.cpp-MIT.txt.
- LLVM OpenMP in der Windows-CPU-Laufzeit: Apache-2.0 mit LLVM-Ausnahmen.
  Vollständiger mitgelieferter Lizenztext: resources/LICENSES/LLVM-OpenMP.txt.
- Qwen3 1.7B, Qwen3.5 0.8B und Qwen3.5 4B: Qwen/Alibaba Cloud und Mitwirkende,
  Apache-2.0. GGUF-Konvertierungen von Unsloth bzw. ggml-org, unveränderte Dateien.
  Originalmodell- und Konvertierungslinks sowie feste Revisionen und Prüfsummen
  stehen in MODELLE.md und model_store.py. Lizenz: resources/LICENSES/Qwen-Apache-2.0.txt.
- Vom Benutzer importierte Modelle und Laufzeiten können andere Lizenzen haben;
  maßgeblich sind deren mitgelieferte Hinweise. Sie werden nicht automatisch Teil
  des eingebauten Lizenzkatalogs.

Alle obigen Lizenztexte sind auch im Über-Fenster offline zugänglich. Ein eigenes
Modelltraining oder eine Veränderung der heruntergeladenen Modellgewichte findet
nicht statt.

Offline-Diktat 1.1 von Losansky.IT ist eine eigenständige Windows-Oberfläche mit einem
Offline-Kern, der auf den Ansätzen aus https://github.com/winidi/dictate basiert.
Insbesondere Modellwahl, Modellrevision, ONNX-Konfiguration, Pegelanhebung und
das Aufteilen langer Aufnahmen sind davon abgeleitet. Die Windows-Oberfläche,
Einrichtung, Integritätsprüfung, Eingabesteuerung und Tests wurden neu erstellt.
Die MIT-Lizenz von winidi liegt in LICENSE. Änderungen: Windows-Integration,
maximal 60 Sekunden pro Rechenabschnitt, prüfsummengesicherte Modelldateien,
kein Speichern fehlerhafter Sprachaufnahmen, optionale Textspeicherung,
abschaltbares Leerzeichen nach jedem Diktat, Branding und Offline-Lizenzansicht.
Der Hinweis © 2026 Losansky.IT bezieht sich auf die eigenen Beiträge zur Anwendung.
Die Rechte der ursprünglichen Autoren und Bibliotheksentwickler bleiben erhalten.

## Spracherkennungsmodell

- Basismodell: NVIDIA, https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- Deutsche Anpassung: primeline, https://huggingface.co/primeline/parakeet-primeline
- ONNX-Konvertierung und INT8-Quantisierung: flozen1981,
  https://huggingface.co/flozen1981/parakeet-primeline-onnx
- Feste Revision: d548e25b9bfe559aa274f361892dc4ed5d64743a
- Lizenz laut Modellkarte: Creative Commons Attribution 4.0 International,
  https://creativecommons.org/licenses/by/4.0/
- Die Modellgewichte werden unverändert verwendet; die veröffentlichte Variante
  ist bereits für Deutsch angepasst und quantisiert.

## Programmbibliotheken

- PySide6 / Qt / Shiboken: The Qt Company und Mitwirkende;
  LGPLv3 / GPLv3 / kommerzielle Lizenzen, je nach Komponente.
  Verwendet werden Qt Core, Gui, Widgets und deren Laufzeitabhängigkeiten.
  https://www.qt.io/licensing/open-source-lgpl-obligations
  https://code.qt.io/cgit/pyside/pyside-setup.git/
  https://code.qt.io/cgit/qt/qtbase.git/
  Qt liegt als austauschbare dynamische Bibliothek im Ordner _internal vor.
  Die Anwendung untersagt kein Reverse Engineering zum Debuggen eigener
  Änderungen an LGPL-Bibliotheken. Quellcode und Bauanleitung der Anwendung
  liegen separat bei.
- sherpa-onnx: k2-fsa und Mitwirkende, Apache-2.0,
  https://github.com/k2-fsa/sherpa-onnx
- ONNX Runtime: Microsoft und Mitwirkende, MIT,
  https://github.com/microsoft/onnxruntime
- NumPy: NumPy Developers, BSD-3-Clause und mitgelieferte Drittanbieterhinweise,
  https://numpy.org/
- sounddevice: Matthias Geier und Mitwirkende, MIT;
  PortAudio: PortAudio-Mitwirkende, MIT-artige Lizenz,
  https://python-sounddevice.readthedocs.io/ und https://www.portaudio.com/
- pynput: Moses Palmér und Mitwirkende, LGPLv3,
  https://github.com/moses-palmer/pynput
- cffi: MIT, https://cffi.readthedocs.io/
- six: MIT, https://github.com/benjaminp/six
- Python: Python Software Foundation License, https://www.python.org/
- PyInstaller-Bootloader: GPL mit Ausnahme für erzeugte Programme,
  https://pyinstaller.org/en/stable/license.html

Die vom installierten Paket mitgelieferten Lizenztexte befinden sich im
Programmordner unter LICENSES. Für eine öffentliche Weiterverteilung sind die
jeweiligen Lizenzpflichten einzuhalten; dieses Paket ist zunächst eine lokale
Testversion für Windows x64.
