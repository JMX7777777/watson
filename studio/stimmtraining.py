"""
Stimm-Training: Der Nutzer liest Sätze am Handy vor, Watson speichert sie als Trainingsdaten
für eine eigene deutsche Kokoro-Stimme (Format: WAV, mono, 24 kHz, 16 Bit + Text).

Ablage:  Watson/studio/stimm-training/
           saetze.txt          die Sätze zum Vorlesen (eine Zeile = ein Satz)
           wavs/satz_0001.wav  die Aufnahmen
           metadata.csv        satz_0001.wav|Text   (für das Training)
"""
import threading
import wave
from io import BytesIO

import numpy as np

import pfade

ORDNER = pfade.PROGRAMM / "stimm-training"
WAVS = ORDNER / "wavs"
SAETZE = ORDNER / "saetze.txt"
METADATA = ORDNER / "metadata.csv"
RATE = 24000
_lock = threading.Lock()


def _saetze():
    try:
        return [z.strip() for z in SAETZE.read_text(encoding="utf-8").splitlines() if z.strip()]
    except OSError:
        return []


def _datei(nr):
    return WAVS / f"satz_{nr:04d}.wav"


def _metadata_schreiben():
    saetze = _saetze()
    zeilen = [f"{_datei(i + 1).name}|{t}" for i, t in enumerate(saetze) if _datei(i + 1).exists()]
    METADATA.write_text("\n".join(zeilen) + ("\n" if zeilen else ""), encoding="utf-8")


def status():
    saetze = _saetze()
    fertig = [i + 1 for i in range(len(saetze)) if _datei(i + 1).exists()]
    naechster = next((i + 1 for i in range(len(saetze)) if not _datei(i + 1).exists()), None)
    sekunden = 0.0
    for nr in fertig:
        try:
            with wave.open(str(_datei(nr))) as w:
                sekunden += w.getnframes() / w.getframerate()
        except Exception:
            pass
    return {"gesamt": len(saetze), "fertig": len(fertig), "naechster": naechster,
            "minuten": round(sekunden / 60, 1)}


def satz(nr):
    saetze = _saetze()
    if not 1 <= nr <= len(saetze):
        return {"error": "Diesen Satz gibt es nicht."}
    return {"nr": nr, "text": saetze[nr - 1], "gesamt": len(saetze), "aufgenommen": _datei(nr).exists()}


def audio(nr):
    p = _datei(nr)
    return p.read_bytes() if p.exists() else None


def loeschen(nr):
    with _lock:
        p = _datei(nr)
        if p.exists():
            p.unlink()
        _metadata_schreiben()
    return {"ok": True}


def _db(x):
    return 20 * np.log10(max(float(x), 1e-9))


def speichern(nr, wav_bytes):
    """Prüft die Aufnahme, schneidet Stille vorn/hinten ab und speichert sie. Gibt Hinweise zur Qualität zurück."""
    saetze = _saetze()
    if not 1 <= nr <= len(saetze):
        return {"error": "Diesen Satz gibt es nicht."}
    try:
        with wave.open(BytesIO(wav_bytes)) as w:
            rate, kanaele, breite = w.getframerate(), w.getnchannels(), w.getsampwidth()
            roh = w.readframes(w.getnframes())
    except Exception:
        return {"error": "Die Aufnahme ist keine gültige WAV-Datei."}
    if breite != 2:
        return {"error": "Unerwartetes Format (nicht 16 Bit)."}
    x = np.frombuffer(roh, dtype=np.int16).astype(np.float32) / 32768.0
    if kanaele > 1:
        x = x.reshape(-1, kanaele).mean(axis=1)
    if rate != RATE:                                   # zur Sicherheit auf 24 kHz bringen
        n = int(len(x) * RATE / rate)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)

    # Lautstärke in 20-ms-Stücken
    fr = int(RATE * 0.02)
    if len(x) < fr * 10:
        return {"error": "Die Aufnahme ist zu kurz. Bitte den ganzen Satz vorlesen."}
    stuecke = x[: len(x) // fr * fr].reshape(-1, fr)
    pegel = np.array([_db(np.sqrt(np.mean(s ** 2))) for s in stuecke])
    rauschen = float(np.percentile(pegel, 10))
    sprache = float(np.percentile(pegel, 90))
    spitze = float(np.abs(x).max())
    uebersteuert = int((np.abs(x) > 0.985).sum())

    # Stille vorn und hinten abschneiden (0,2 s Rand lassen)
    schwelle = max(rauschen + 12, sprache - 35)
    laut = np.where(pegel > schwelle)[0]
    if not len(laut):
        return {"error": "Ich höre keine Sprache. Ist das Mikrofon an?"}
    rand = int(0.2 / 0.02)
    a, b = max(0, laut[0] - rand), min(len(pegel), laut[-1] + rand + 1)
    x = x[a * fr: b * fr]
    dauer = len(x) / RATE

    hinweise, schlecht = [], False
    if dauer < 0.8:
        return {"error": "Die Aufnahme ist zu kurz. Bitte den ganzen Satz vorlesen."}
    if dauer > 30:
        return {"error": "Die Aufnahme ist länger als 30 Sekunden. Bitte nur den einen Satz lesen."}
    if uebersteuert > 20 or spitze > 0.999:
        hinweise.append("Zu laut, die Aufnahme ist übersteuert. Bitte etwas weiter weg vom Handy sprechen.")
        schlecht = True
    elif sprache < -38:
        hinweise.append("Sehr leise. Bitte etwas näher ans Handy oder etwas lauter sprechen.")
        schlecht = True
    if rauschen > -45:
        hinweise.append("Viel Hintergrundgeräusch. Gibt es einen ruhigeren Ort?")
        schlecht = True
    elif rauschen > -55:
        hinweise.append("Etwas Hintergrundgeräusch, das geht aber noch.")

    with _lock:
        WAVS.mkdir(parents=True, exist_ok=True)
        with wave.open(str(_datei(nr)), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        _metadata_schreiben()
    return {"ok": True, "dauer": round(dauer, 1), "hinweise": hinweise, "nochmal_empfohlen": schlecht,
            "pegel": round(sprache, 1), "rauschen": round(rauschen, 1)}
