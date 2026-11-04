# Modelle in Offline-Diktat 1.1

## Spracherkennung

Das bisherige Parakeet-DE-Modell bleibt die Empfehlung und wird nicht durch die
Text-KI ersetzt. Der Download verwendet weiterhin die feste Revision und
Prüfsummen aus engine.py. Bereits installierte Modelle werden im Programmordner
`models`, im Benutzerordner und an zuvor ausgewählten Orten gesucht.

Unter **Einstellungen → Sprachmodelle** lassen sich mehrere lokale Modelle
auswählen und prüfen. Mit **Vorhandenen Modellordner auswählen** können auch
andere für sherpa-onnx exportierte NeMo-Transducer- oder Whisper-ONNX-Modelle
importiert werden. Im Importdialog werden Modellfamilie, Anzeigename, Version und
Dateien zugeordnet. Bei Whisper lässt sich Deutsch, Englisch oder automatische
Spracherkennung auswählen, sofern das Modell diese Sprachen unterstützt.

Die Anwendung legt die Zuordnung in `%LOCALAPPDATA%\DictateOffline\model-profiles`
ab. Der Quellordner wird nicht beschrieben oder kopiert. Ein USB-Laufwerk muss
also auch später verfügbar sein. Vor dem ersten Laden wird die Kompatibilität in
einem separaten Prozess geprüft, damit ein ungeeignetes Modell nicht die
Oberfläche beendet. Lokale Modelle werden nicht als offiziell empfohlen markiert.

Beliebige neuere Modelle sind nicht automatisch kompatibel. GGUF gehört in die
Text-KI, nicht in die Spracherkennung. Originale `.nemo`- oder Safetensors-Dateien
sind keine sherpa-onnx-Exporte. Das Modell muss die benötigten Sprachen selbst
unterstützen. Ein neues Sprachmodell muss mit echten Diktaten getestet werden.

Optional können Modelle bereits eine `speech-model.json` im Modellordner enthalten:

```json
{
  "name": "Mein Whisper-Modell",
  "version": "lokale Version",
  "backend": "whisper",
  "encoder": "encoder.onnx",
  "decoder": "decoder.onnx",
  "tokens": "tokens.txt",
  "language": "de"
}
```

Für NeMo `backend` auf `nemo_transducer` setzen und `joiner` ergänzen. Externe
ONNX-Datendateien müssen neben ihren ONNX-Dateien liegen. Ein optionales Objekt
`sha256` ordnet relativen Dateinamen SHA-256-Prüfsummen zu. Bei einem Import ohne
Prüfsummen werden Dateien und Ladefähigkeit geprüft, nicht die Herkunft bestätigt.

## Optionale Text-KI

Unter **Einstellungen → Text-KI**:

1. Text-KI aktivieren.
2. Eines der drei Modelle auswählen und herunterladen oder eine GGUF-Datei wählen.
3. Die mitgelieferte CPU-Laufzeit wird automatisch gefunden. Alternativ lässt sie
   sich herunterladen oder als vorhandene `llama-server.exe` auswählen.
4. Optional den lokalen Kurztest starten, dann Einstellungen speichern.

| Modell | Download | Grobe RAM-Planung, kein Benchmark |
| --- | ---: | ---: |
| Qwen3 1.7B Q4_K_M | 1,11 GB | 1,5–2,5 GB |
| Qwen3.5 0.8B Q4_0 | 0,56 GB | 0,8–1,5 GB |
| Qwen3.5 4B Q4_K_M | 2,74 GB | 3–5 GB |

Der Arbeitsspeicher der Spracherkennung kommt hinzu. Kontextgröße, Backend und
Rechner verändern den tatsächlichen Bedarf. Alle Angebote sind Vergleichsoptionen;
die beste Qualität für eigene Texte muss vor Ort geprüft werden. Kleine Modelle
können Anweisungen ignorieren, Fakten verändern oder ungeeignete Texte erzeugen.
Es gibt deshalb keine automatische Übernahme eines KI-Ergebnisses.

Modelldownloads sind an feste Revisionen und SHA-256-Prüfsummen gebunden
(model_store.py). Lokale, abweichende GGUF-Dateien werden anhand ihrer Kennung und
beim Laden geprüft; deren Herkunft wird nicht bestätigt. Andere GGUF-Architekturen
müssen von der ausgewählten llama.cpp-Version unterstützt werden.

Offizielle Quellen und Konvertierungen:

- https://huggingface.co/Qwen/Qwen3-1.7B
- https://huggingface.co/unsloth/Qwen3-1.7B-GGUF
- https://huggingface.co/Qwen/Qwen3.5-0.8B
- https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/unsloth/Qwen3.5-4B-GGUF
- https://github.com/ggml-org/llama.cpp/releases/tag/b11669

## CPU, Daten und Grenzen

Die Text-KI läuft als eigener, unsichtbarer CPU-Prozess. Sie lauscht ausschließlich
auf `127.0.0.1`, mit zufälligem Port und Sitzungsschlüssel. Diktate werden nicht an
externe APIs gesendet. Internetzugriffe erfolgen nur bei angeforderten Downloads
oder beim Öffnen eines Quellenlinks. Die Anwendung bietet keine Cloud-Text-KI.

Standardmäßig wird das Textmodell nach der Bearbeitung entladen. Optional bleibt
es geladen; nach fünf Minuten Inaktivität wird es trotzdem entladen. Ein Abbruch
beendet den eigenen KI-Prozess, während das Original im Editor erhalten bleibt.

Für lange Diktate kann ein Abschnitt markiert werden. Vor der Bearbeitung wird die
Tokenzahl des tatsächlich formatierten Prompts geprüft. Bei überschrittener
Kontextgrenze oder abgeschnittener Antwort wird nichts übernommen. Eine größere
Kontextgröße benötigt mehr RAM; eine automatische abschnittsweise KI-Bearbeitung
mit möglichem Kontextverlust findet nicht statt.

Sprachbefehle sind ein separater, einmalig aktivierter Modus im Hauptfenster.
Unterstützt werden ganze Äußerungen: „Neuer Absatz“, „Letzten Satz löschen“,
„Rückgängig“, „Stil professionell“, „Stil korrigieren“, „Stil glätten“ und
„Bitte formuliere den vorherigen Abschnitt professioneller“. Unbekannte oder
gemischte Äußerungen führen keine Aktion aus. Satzgrenzen werden anhand von
Satzzeichen erkannt; bei Abkürzungen bitte prüfen und gegebenenfalls rückgängig machen.
