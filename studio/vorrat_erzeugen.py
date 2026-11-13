r"""
Erzeugt Watsons Vorrat an kurzen Sätzen mit der eigenen Stimme (omnivoice.cpp) – lautlos.
Jeder Satz wird mit Whisper nachgehört; stimmt er nicht, wird er mit einem anderen Seed neu erzeugt.
Ergebnis: <stimmen>/vorrat/*.wav + vorrat.json. Schon fertige Sätze werden übersprungen.
Die Satzliste ist <stimmen>/kurzsaetze.txt; fehlt sie, wird sie aus eigene-stimme/kurzsaetze-vorlage.txt
angelegt ({NAME} = Name des Nutzers aus den Einstellungen).
Aufruf: python vorrat_erzeugen.py [--neu "Satz" ...]
"""
import difflib, json, re, sys, time, urllib.request, wave
from io import BytesIO
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pfade  # noqa: E402
import stimme  # noqa: E402  (startet den Sprachserver bei Bedarf)

LISTE = pfade.STIMMEN / "kurzsaetze.txt"
VORLAGE = pfade.PROGRAMM / "eigene-stimme" / "kurzsaetze-vorlage.txt"
VORRAT = stimme.VORRAT
INDEX = VORRAT / "vorrat.json"


def liste_anlegen():
    if LISTE.exists():
        return
    try:
        cfg = json.loads((pfade.DATEN / "einstellungen.json").read_text(encoding="utf-8-sig"))
        name = (cfg.get("charakter") or {}).get("nutzer") or ""
    except Exception:
        name = ""
    text = VORLAGE.read_text(encoding="utf-8")
    zeilen = []
    for z in text.splitlines():
        if "{NAME}" in z:
            z = z.replace("{NAME}", name) if name else re.sub(r",?\s*\{NAME\}", "", z)
        zeilen.append(z)
    LISTE.write_text("\n".join(dict.fromkeys(zeilen)) + "\n", encoding="utf-8")
VERSUCHE = 8


def schluessel(text):
    t = text.lower().replace("ß", "ss")
    t = re.sub(r"[^\wäöü ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def erzeuge(text, seed):
    body = json.dumps({"input": text, "voice": stimme.OV_VOICE, "language": "German",
                       "response_format": "wav", "seed": seed}).encode()
    req = urllib.request.Request(stimme.OV_URL + "/v1/audio/speech", data=body,
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=600).read()


def als_16k(data):
    with wave.open(BytesIO(data)) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    n = int(len(a) * 16000 / rate)
    a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    stille = np.zeros(8000, dtype=np.float32)
    return np.concatenate([stille, a, stille]), len(a) / 16000


def main():
    VORRAT.mkdir(parents=True, exist_ok=True)
    liste_anlegen()
    index = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    saetze = [z.strip() for z in LISTE.read_text(encoding="utf-8-sig").splitlines()
              if z.strip() and not z.strip().startswith("#")]
    if "--neu" in sys.argv:          # einzelne Sätze neu erzeugen
        for t in sys.argv[sys.argv.index("--neu") + 1:]:
            index.pop(schluessel(t), None)
    from faster_whisper import WhisperModel
    ohr = WhisperModel("medium", device="cpu", compute_type="int8")
    if not stimme.Mund._ov_bereit():
        sys.exit("Sprachserver startet nicht")
    for nr, text in enumerate(saetze, 1):
        k = schluessel(text)
        if k in index and (VORRAT / index[k]["datei"]).exists():
            continue
        best = None
        for v in range(VERSUCHE):
            seed = 1000 + v * 7919
            t0 = time.time()
            data = erzeuge(text, seed)
            audio, dauer = als_16k(data)
            segs, _ = ohr.transcribe(audio, language="de", beam_size=5, condition_on_previous_text=False,
                                     initial_prompt="Watson spricht.")
            gehoert = " ".join(s.text.strip() for s in segs).strip()
            guete = difflib.SequenceMatcher(None, k, schluessel(gehoert)).ratio()
            print(f"[{nr}/{len(saetze)}] {text!r} seed={seed} -> {gehoert!r} ({guete:.2f}, {dauer:.1f}s Audio, "
                  f"{time.time() - t0:.0f}s)", flush=True)
            if best is None or guete > best[0]:
                best = (guete, seed, data, gehoert)
            if guete >= 0.97:
                break
        guete, seed, data, gehoert = best
        datei = f"{len(index) + 1:03d}-{re.sub(r'[^a-z0-9]+', '-', k.encode('ascii', 'ignore').decode())[:40].strip('-')}.wav"
        (VORRAT / datei).write_bytes(data)
        index[k] = {"text": text, "datei": datei, "seed": seed, "gehoert": gehoert, "guete": round(guete, 2),
                    "geprueft_von_jim": False}
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    schlecht = [v["text"] for v in index.values() if v["guete"] < 0.97]
    print("FERTIG.", len(index), "Sätze im Vorrat. Unsicher:", schlecht, flush=True)


if __name__ == "__main__":
    main()
