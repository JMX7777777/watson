"""
Watsons Ohren und Mund – alles lokal auf dem eigenen Computer.

Mund:   Piper (deutsche Stimmen Thorsten / Kerstin) oder die eigene geklonte Stimme aus VoiceStudio; Satz für Satz.
Ohren:  Whisper "small" erkennt Sprache; Stimmerkennung (VAD) merkt, wann jemand spricht.
"Hey Watson": Watson hört im Hintergrund zu und reagiert nur, wenn „Watson“ gesagt wird.
Danach hört er noch kurz ohne Aktivierungswort zu (Folgefragen), wie ein echtes Gespräch.
"""
import queue
import re
import threading
import time
import wave
from collections import deque
from io import BytesIO
from pathlib import Path

import numpy as np
import sounddevice as sd
import webrtcvad

HERE = Path(__file__).resolve().parent
import pfade
VOICES = {"thorsten": pfade.STIMMEN / "de_DE-thorsten-high.onnx",
          "kerstin": pfade.STIMMEN / "de_DE-kerstin-low.onnx"}
# Eigene Stimme (geklont in VoiceStudio, Engine OmniVoice). Auswahlwert "vs:<Profilname>", z. B. "vs:Anna".
VS_URL = "http://127.0.0.1:3900/v1/audio/speech"
VS_STEPS = 8          # 16 = VoiceStudio-Standard (doppelt so langsam); 8 halbiert die Wartezeit
VS_SPEED = 0.9        # etwas ruhiger sprechen
# Eigene Stimme, schnelle Version: omnivoice.cpp läuft nativ (ARM64) in WSL Ubuntu als kleiner Sprachserver.
# Auswahlwert "ov:eigene". Stimmprobe: stimmen/eigene-stimme.wav (+ .txt mit dem gesprochenen Text).
OV_URL = "http://127.0.0.1:8091"
OV_DISTRO = "Ubuntu-24.04"
OV_DIR = "/opt/omnivoice.cpp"
# Kokoro (deutsch, Stimme „Martin“): schnell wie Piper, klingt natürlicher. Auswahlwert "kokoro:martin".
KOKORO_DIR = pfade.STIMMEN / "kokoro"
KOKORO_TEMPO = 1.0   # Kokoro-eigenes Tempo (1.0 = normal, kleiner = langsamer); Martins Vorlage nutzt 1.125
OV_STEPS = 16       # Rechenschritte: 8 = schnell, aber s-Laute unsauber (Lispeln); 16 = deutlich sauberer, etwa doppelt so langsam
OV_STEPS_DATEI = pfade.STIMMEN / "sprachserver_schritte.txt"   # mit welchen Schritten der laufende Server gestartet wurde
OV_CMD = ["wsl.exe", "-d", OV_DISTRO, "-u", "root", "--", OV_DIR + "/build/tts-server",
          "--model", OV_DIR + "/models/omnivoice-base-Q8_0.gguf",
          "--codec", OV_DIR + "/models/omnivoice-tokenizer-Q8_0.gguf",
          "--host", "127.0.0.1", "--port", "8091", "--lang", "German", "--steps", str(OV_STEPS)]
OV_VOICE = "eigene"
# Vorrat: häufige kurze Sätze, einmal sauber erzeugt und geprüft (werkzeuge/kurzsaetze-erzeugen.py).
# Kurze Sätze sind beim Klonen unzuverlässig – aus dem Vorrat kommen sie sofort und fehlerfrei.
VORRAT = pfade.STIMMEN / "vorrat"
_vorrat_cache = {"mtime": None, "index": {}}


def _schluessel(text):
    t = text.lower().replace("ß", "ss")
    t = re.sub(r"[^\wäöü ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _aus_vorrat(text):
    """Pfad zur fertigen Aufnahme, falls der Satz im Vorrat ist – sonst None."""
    idx = VORRAT / "vorrat.json"
    try:
        m = idx.stat().st_mtime
        if _vorrat_cache["mtime"] != m:
            import json
            _vorrat_cache.update(mtime=m, index=json.loads(idx.read_text(encoding="utf-8")))
        e = _vorrat_cache["index"].get(_schluessel(text))
        if e and (VORRAT / e["datei"]).exists():
            return VORRAT / e["datei"]
    except Exception:
        pass
    return None
RATE = 16000
FRAME = 480                      # 30 ms
FOLLOWUP_SECONDS = 8

WAKE_RE = re.compile(r"(hey|hei|hi|hallo|ok|okay)?[\s,\-]*[wv]a[tdrzs]{1,4}oh?n\w*[\s,.!?:]*", re.IGNORECASE)
STOP_RE = re.compile(r"^\s*(stopp?|halt|ruhe|sei still|aufhören)\W*$", re.IGNORECASE)
# Gesprächsmodus beenden per Sprache
GESPRAECH_ENDE_RE = re.compile(r"^\W*(gespräch beenden|beende das gespräch|sprachmodus (beenden|aus)|gesprächsmodus (beenden|aus)"
                               r"|tschüss,? watson|auf wiedersehen,? watson|ende,? watson)\W*$", re.IGNORECASE)
# Whisper „erfindet“ bei Rauschen gern Sätze aus Fernseh-Untertiteln – die nie als Frage behandeln
HALLU_KURZ = {"vielen dank", "danke", "danke schön", "dankeschön", "tschüss", "bis zum nächsten mal",
              "vielen dank für ihre aufmerksamkeit", "bis bald", "musik", "applaus"}
LEISE_GRENZE = 0.003  # mittlere Lautstärke darunter = kein Sprechen (normales Sprechen am Laptop: etwa 0,02–0,1)
HALLU_RE = re.compile(r"untertitel|amara\.org|f[üu]r'?s zuschauen|f[üu]rs zuh[öo]ren|abonniert|copyright|www\.|\bswr\b|\bzdf\b",
                      re.IGNORECASE)


def _beep(freq=880, ms=110, vol=0.2):
    t = np.linspace(0, ms / 1000, int(22050 * ms / 1000), False)
    sd.play((np.sin(2 * np.pi * freq * t) * vol * np.hanning(len(t))).astype(np.float32), 22050)
    sd.wait()


# ---------- Text vorlesbar machen (Tabellen, Bibelstellen) ----------
# Bibelbücher: Abkürzung/Name -> wie man es ausspricht. Nummerierte Bücher bekommen ihre Nummer extra (1 -> "erster" …).
_BUECHER = {
    "mo": "Mose", "mose": "Mose", "gen": "erstes Buch Mose", "ex": "zweites Buch Mose", "lev": "drittes Buch Mose",
    "num": "viertes Buch Mose", "dtn": "fünftes Buch Mose",
    "jos": "Josua", "josua": "Josua", "ri": "Richter", "richter": "Richter", "rut": "Rut", "ruth": "Rut",
    "sam": "Samuel", "samuel": "Samuel", "kön": "Könige", "kö": "Könige", "kon": "Könige", "könige": "Könige",
    "chr": "Chronik", "chronik": "Chronik", "esr": "Esra", "esra": "Esra", "neh": "Nehemia", "nehemia": "Nehemia",
    "est": "Ester", "ester": "Ester", "hi": "Hiob", "hiob": "Hiob", "ijob": "Ijob",
    "ps": "Psalm", "psalm": "Psalm", "psalmen": "Psalm", "spr": "Sprüche", "sprüche": "Sprüche",
    "pred": "Prediger", "prediger": "Prediger", "koh": "Kohelet", "kohelet": "Kohelet", "hld": "Hoheslied",
    "jes": "Jesaja", "jesaja": "Jesaja", "jer": "Jeremia", "jeremia": "Jeremia", "klgl": "Klagelieder",
    "hes": "Hesekiel", "hesekiel": "Hesekiel", "ez": "Ezechiel", "dan": "Daniel", "daniel": "Daniel",
    "hos": "Hosea", "hosea": "Hosea", "joel": "Joel", "am": "Amos", "amos": "Amos", "obd": "Obadja", "obadja": "Obadja",
    "jona": "Jona", "mi": "Micha", "micha": "Micha", "nah": "Nahum", "nahum": "Nahum", "hab": "Habakuk",
    "habakuk": "Habakuk", "zef": "Zefanja", "zefanja": "Zefanja", "hag": "Haggai", "haggai": "Haggai",
    "sach": "Sacharja", "sacharja": "Sacharja", "mal": "Maleachi", "maleachi": "Maleachi",
    "mt": "Matthäus", "matth": "Matthäus", "matthäus": "Matthäus", "mk": "Markus", "mark": "Markus", "markus": "Markus",
    "lk": "Lukas", "luk": "Lukas", "lukas": "Lukas", "joh": "Johannes", "johannes": "Johannes",
    "apg": "Apostelgeschichte", "apostelgeschichte": "Apostelgeschichte", "röm": "Römer", "rom": "Römer", "römer": "Römer",
    "kor": "Korinther", "korinther": "Korinther", "gal": "Galater", "galater": "Galater", "eph": "Epheser",
    "epheser": "Epheser", "phil": "Philipper", "philipper": "Philipper", "kol": "Kolosser", "kolosser": "Kolosser",
    "thess": "Thessalonicher", "thessalonicher": "Thessalonicher", "tim": "Timotheus", "timotheus": "Timotheus",
    "tit": "Titus", "titus": "Titus", "phlm": "Philemon", "philemon": "Philemon", "hebr": "Hebräer", "heb": "Hebräer",
    "hebräer": "Hebräer", "jak": "Jakobus", "jakobus": "Jakobus", "petr": "Petrus", "pet": "Petrus", "petrus": "Petrus",
    "jud": "Judas", "judas": "Judas", "offb": "Offenbarung", "off": "Offenbarung", "offenbarung": "Offenbarung",
}
_NUMMERIERT = {"Mose", "Samuel", "Könige", "Chronik", "Korinther", "Thessalonicher", "Timotheus", "Petrus", "Johannes"}
_ORDINAL = {"1": "erster", "2": "zweiter", "3": "dritter", "4": "vierter", "5": "fünfter"}
_BUCH_RE = "|".join(sorted((re.escape(k) for k in _BUECHER), key=len, reverse=True))
# z. B. "Mt 11,28" · "Joh 6,37-40" · "1 Pet 2,11-23" · "1. Petr. 2, 11.12" · "Ps 23" · "Röm 8,28ff"
_STELLE = re.compile(
    r"(?<![\wäöüÄÖÜß])(?:(?P<nr>[1-5])\.?\s*)?(?P<buch>" + _BUCH_RE + r")\.?\s+(?P<kap>\d{1,3})"
    r"(?:\s*,\s*(?P<verse>\d{1,3}[a-c]?(?:\s*[-–]\s*\d{1,3}[a-c]?)?(?:\s*[.;]\s*\d{1,3}(?:\s*[-–]\s*\d{1,3})?)*)"
    r"(?P<f>\s*ff?\.?)?)?(?!\d|,\s*\d)",
    re.IGNORECASE)


def _stelle_sprechen(m):
    buch = _BUECHER[m.group("buch").lower()]
    nr = m.group("nr")
    if nr and buch == "Mose":
        buch = {"1": "erstes", "2": "zweites", "3": "drittes", "4": "viertes", "5": "fünftes"}[nr] + " Buch Mose"
    elif nr and buch in _NUMMERIERT:
        buch = f"{_ORDINAL[nr]} {buch}"
    elif nr:
        return m.group(0)                       # Nummer passt nicht zum Buch -> lieber unverändert lassen
    elif buch in ("Mose", "Samuel", "Könige", "Chronik", "Korinther", "Thessalonicher", "Timotheus", "Petrus") \
            and m.group("buch").lower() not in ("mose", "petrus"):
        return m.group(0)                       # z. B. "Kor 3" ohne Nummer: unklar -> unverändert
    kap, verse = m.group("kap"), m.group("verse")
    if verse is None:                           # nur Kapitel: Kurzformen ohne Vers nur bei eindeutigen Büchern
        if len(m.group("buch")) <= 2 and m.group("buch").lower() not in ("ps", "mt", "mk", "lk"):
            return m.group(0)                   # "Am 5", "Mi 3" … könnten normale Wörter sein
        return f"{buch} {kap}"
    teile = re.split(r"\s*[.;]\s*", verse.strip())
    teile = [re.sub(r"\s*[-–]\s*", " bis ", t) for t in teile]
    v = teile[0] if len(teile) == 1 else ", ".join(teile[:-1]) + " und " + teile[-1]
    mehrere = len(teile) > 1 or " bis " in teile[0]
    text = f"{buch} {kap}, {'Verse' if mehrere else 'Vers'} {v}"   # Komma = kleine Sprechpause
    f = (m.group("f") or "").strip().rstrip(".")
    if f:
        text += " und folgende"
    return text


def vorlesbar(text):
    """Macht Text fürs Vorlesen schön: Tabellen-Trennlinien weg, Zellen mit Pausen, Bibelstellen ausgeschrieben."""
    zeilen = []
    for z in text.splitlines():
        if re.fullmatch(r"\s*\|?[\s|:\-–—=+]*\|?\s*", z) and re.search(r"[-–—=]{3,}", z):
            continue                            # |-------|------| oder ----- : gar nicht aussprechen
        if z.strip().startswith("|"):           # Tabellenzeile: Zellen mit kurzer Pause, Zeile als Satz
            zellen = [c.strip() for c in z.strip().strip("|").split("|") if c.strip()]
            z = ", ".join(zellen) + "."
        zeilen.append(z)
    text = "\n".join(zeilen)
    text = re.sub(r"[-–—=_~]{3,}", " ", text)   # sonstige Trennstriche
    text = _STELLE.sub(_stelle_sprechen, text)
    # Kapitelbereiche wie "Matthäus 5-7" -> "Matthäus 5 bis 7"
    namen = "|".join(sorted({re.escape(v.split()[-1]) for v in _BUECHER.values()}, key=len, reverse=True))
    return re.sub(r"\b(" + namen + r")\s+(\d{1,3})\s*[-–]\s*(\d{1,3})\b(?!\s*,\s*\d)", r"\1 \2 bis \3", text)


SPRECHTEMPO = 0.9   # 1.0 = Originaltempo, 0.9 = 10 % langsamer (Tonhöhe bleibt gleich)


def _langsamer(audio, rate, tempo=None):
    """Sprache langsamer machen, ohne dass die Stimme tiefer wird (ffmpeg-Filter „atempo“ über PyAV).
    Klappt etwas nicht, bleibt die Aufnahme einfach unverändert."""
    tempo = SPRECHTEMPO if tempo is None else tempo
    if not len(audio) or abs(tempo - 1.0) < 0.01:
        return audio
    try:
        import av
        from av.audio.frame import AudioFrame
        g = av.filter.Graph()
        src = g.add_abuffer(format="s16", sample_rate=rate, layout="mono")
        at = g.add("atempo", str(max(0.5, min(2.0, tempo))))
        sink = g.add("abuffersink")
        src.link_to(at); at.link_to(sink); g.configure()
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).reshape(1, -1)
        fr = AudioFrame.from_ndarray(pcm, format="s16", layout="mono")
        fr.sample_rate = rate; fr.pts = 0
        g.push(fr); g.push(None)
        teile = []
        while True:
            try:
                f = g.pull()
            except Exception:
                break
            teile.append(f.to_ndarray().reshape(-1))
        if not teile:
            return audio
        return np.concatenate(teile).astype(np.float32) / 32768.0
    except Exception:
        return audio


class Mund:
    """Spricht Text Satz für Satz; der nächste Satz wird schon vorbereitet, während der erste läuft."""

    def __init__(self):
        self.voice_name, self.voice = None, None
        self.q = queue.Queue()
        self.speaking = threading.Event()
        self.fertig_um = 0.0              # wann zuletzt fertig gesprochen (Nachhall nicht als Frage hören)
        self.generation = 0
        self.on_done = None
        threading.Thread(target=self._worker, daemon=True).start()

    def _load(self, name):
        if self.voice_name != name or self.voice is None:
            from piper import PiperVoice
            pfad = VOICES.get(name)
            if pfad is None and name.startswith("piper:"):        # vom Installer geladene Stimme, z. B. piper:nl_NL-mls-medium
                p = pfade.STIMMEN / (re.sub(r"[^\w.\-]", "", name[6:]) + ".onnx")
                pfad = p if p.exists() else None
            self.voice = PiperVoice.load(str(pfad or VOICES["thorsten"]))
            self.voice_name = name
        return self.voice

    @staticmethod
    def _synth_voicestudio(text, profil):
        """Eigene geklonte Stimme über VoiceStudios lokale Schnittstelle (nur 127.0.0.1, nichts geht ins Internet)."""
        import json, urllib.request
        body = json.dumps({"model": "omnivoice", "input": text, "voice": profil, "language": "de",
                           "response_format": "wav", "speed": VS_SPEED, "num_step": VS_STEPS}).encode()
        req = urllib.request.Request(VS_URL, data=body, headers={"Content-Type": "application/json"})
        data = urllib.request.urlopen(req, timeout=600).read()
        with wave.open(BytesIO(data)) as w:
            rate = w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0, rate

    _ov_proc = None
    _ov_lock = threading.Lock()

    @staticmethod
    def _ov_get(path, timeout=3):
        import json, urllib.request
        return json.loads(urllib.request.urlopen(OV_URL + path, timeout=timeout).read() or b"null")

    _ov_geprueft = False

    @classmethod
    def _ov_schritte_pruefen(cls):
        """Läuft noch ein Sprachserver mit alten Einstellungen (z. B. 8 Schritte), wird er einmal beendet,
        damit er gleich mit den neuen Einstellungen neu startet."""
        import subprocess
        if cls._ov_geprueft:
            return
        cls._ov_geprueft = True
        try:
            alt = OV_STEPS_DATEI.read_text(encoding="utf-8").strip()
        except Exception:
            alt = ""
        if alt == str(OV_STEPS):
            return
        try:
            cls._ov_get("/health", timeout=2)          # läuft überhaupt einer?
        except Exception:
            alt = None
        if alt is not None:
            try:
                subprocess.run(["wsl.exe", "-d", OV_DISTRO, "-u", "root", "--", "pkill", "-f", "build/tts-server"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=20, creationflags=0x08000000)
                time.sleep(2)
            except Exception:
                pass
        cls._ov_proc = None
        try:
            OV_STEPS_DATEI.write_text(str(OV_STEPS), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def _ov_bereit(cls):
        """Startet den Sprachserver in WSL (falls nötig) und meldet die eigene Stimme an."""
        import base64, json, subprocess, urllib.request
        with cls._ov_lock:
            cls._ov_schritte_pruefen()
            try:
                stimmen = cls._ov_get("/v1/audio/voices")
                if OV_VOICE in json.dumps(stimmen):
                    return True
            except Exception:
                if cls._ov_proc is None or cls._ov_proc.poll() is not None:
                    cls._ov_proc = subprocess.Popen(OV_CMD, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                    stderr=subprocess.DEVNULL, creationflags=0x08000000)  # kein Fenster
                for _ in range(90):                      # Modell laden dauert ein paar Sekunden
                    time.sleep(1)
                    try:
                        cls._ov_get("/health"); break
                    except Exception:
                        continue
                else:
                    return False
            wav = pfade.STIMMEN / "eigene-stimme.wav"
            txt = (pfade.STIMMEN / "eigene-stimme.txt").read_text(encoding="utf-8-sig").strip()
            body = json.dumps({"name": OV_VOICE, "ref_text": txt,
                               "wav_b64": base64.b64encode(wav.read_bytes()).decode()}).encode()
            req = urllib.request.Request(OV_URL + "/v1/audio/voices", data=body,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=120).read()
            return True

    @classmethod
    def _synth_omnivoice(cls, text):
        import json, urllib.request
        if not cls._ov_bereit():
            raise RuntimeError("Sprachserver startet nicht")
        body = json.dumps({"input": text, "voice": OV_VOICE, "language": "German",
                           "response_format": "wav"}).encode()
        req = urllib.request.Request(OV_URL + "/v1/audio/speech", data=body, headers={"Content-Type": "application/json"})
        data = urllib.request.urlopen(req, timeout=600).read()
        with wave.open(BytesIO(data)) as w:
            rate = w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0, rate

    def _synth(self, text, name):
        if name.startswith("kokoro:"):
            try:
                return self._synth_kokoro(text, name[7:])    # Tempo stellt Kokoro selbst ein
            except Exception:
                name = "thorsten"                            # Kokoro nicht installiert -> lieber Thorsten als gar nichts
        audio, rate = self._synth_roh(text, name)
        return _langsamer(audio, rate), rate

    _kokoro = None
    _kokoro_lock = threading.Lock()

    @classmethod
    def _synth_kokoro(cls, text, stimme="martin"):
        with cls._kokoro_lock:                               # ein Modell, nacheinander benutzt (Laptop + Handy)
            if cls._kokoro is None:
                from kokoro_onnx import Kokoro
                cls._kokoro = Kokoro(str(KOKORO_DIR / f"kokoro-{stimme}.onnx"), str(KOKORO_DIR / f"voices-{stimme}.npz"))
            audio, rate = cls._kokoro.create(text, voice=stimme, speed=KOKORO_TEMPO, lang="de")
        return np.asarray(audio, dtype=np.float32), rate

    def _synth_roh(self, text, name):
        if name.startswith("ov:"):
            fertig = _aus_vorrat(text)
            if fertig:
                with wave.open(str(fertig)) as w:
                    rate = w.getframerate()
                    pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                return pcm.astype(np.float32) / 32768.0, rate
            try:
                return self._synth_omnivoice(text)
            except Exception:
                name = "thorsten"          # Sprachserver nicht erreichbar -> lieber Thorsten als gar nichts
        if name.startswith("vs:"):
            try:
                return self._synth_voicestudio(text, name[3:])
            except Exception:
                name = "thorsten"          # VoiceStudio läuft nicht -> lieber Thorsten als gar nichts
        buf = BytesIO()
        with wave.open(buf, "wb") as w:
            self._load(name).synthesize_wav(text, w)
        buf.seek(0)
        with wave.open(buf) as w:
            rate = w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0, rate

    @staticmethod
    def _clean(text):
        text = vorlesbar(text)
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = re.sub(r"[*_#`>|]+", "", text)
        text = re.sub(r"https?://\S+", "Link", text)
        text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)   # Emojis nicht vorlesen
        return text

    def _stuecke(self, text, voice):
        """Text in Sätze zerlegen. Eigene Stimme: kurze Sätze zu Stücken bis ~160 Zeichen bündeln
        (jeder Aufruf rechnet die Stimmprobe mit; zu lange Stücke klingen gehetzt und undeutlich).
        Sätze aus dem Vorrat bleiben einzeln (kommen sofort und fehlerfrei)."""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?:;])\s+|\n+", self._clean(text)) if len(s.strip()) > 1]
        # Sehr lange Sätze an Kommas teilen, damit kein Stück zu lang wird
        kurz = []
        for s in sentences:
            while len(s) > 150 and "," in s[40:150]:
                i = s.rfind(",", 40, 150) + 1
                kurz.append(s[:i].strip()); s = s[i:].strip()
            kurz.append(s)
        sentences = kurz
        if not voice.startswith("ov:"):
            return sentences
        stuecke, offen = [], False
        for s in sentences:
            if _aus_vorrat(s):
                stuecke.append(s); offen = False
            elif offen and len(stuecke[-1]) + len(s) < 160:
                stuecke[-1] += " " + s
            else:
                stuecke.append(s); offen = True
        return stuecke

    def synth_ganz(self, text, voice="thorsten", pause=0.4):
        """Ganzen Text als EINE Aufnahme (z. B. fürs Handy) – Stück für Stück erzeugt, mit kurzer Atempause dazwischen."""
        teile, rate = [], None
        for st in self._stuecke(text, voice):
            try:
                audio, r = self._synth(st[:400], voice)
            except Exception:
                continue
            if rate is None:
                rate = r
            elif r != rate:   # andere Abtastrate (z. B. Vorrat) -> angleichen
                n = int(len(audio) * rate / r)
                audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
            if teile:
                teile.append(np.zeros(int(rate * pause), dtype=np.float32))
            teile.append(audio.astype(np.float32))
        if not teile:
            return self._synth("…", "thorsten")
        return np.concatenate(teile), rate

    def say(self, text, voice="thorsten", on_done=None):
        self.stop()
        gen = self.generation
        self.on_done = on_done
        sentences = self._stuecke(text, voice)
        if not sentences:                 # nichts Vorlesbares (z. B. nur Emojis) -> trotzdem „fertig“ melden
            self.on_done = None
            if on_done:
                threading.Thread(target=on_done, daemon=True).start()
            return
        self.speaking.set()
        # Sätze im Hintergrund vorbereiten, damit zwischen den Sätzen keine langen Pausen entstehen
        def prepare():
            for s in sentences:
                if gen != self.generation:
                    return
                try:
                    self.q.put((gen, self._synth(s[:400], voice)))
                except Exception:
                    pass
            self.q.put((gen, None))
        threading.Thread(target=prepare, daemon=True).start()

    def _worker(self):
        while True:
            gen, item = self.q.get()
            if gen != self.generation:
                continue
            if item is None:
                self.fertig_um = time.time()
                self.speaking.clear()
                cb, self.on_done = self.on_done, None
                if cb:
                    threading.Thread(target=cb, daemon=True).start()
                continue
            audio, rate = item
            sd.play(audio, rate)
            sd.wait()

    def stop(self):
        self.generation += 1
        sd.stop()
        with self.q.mutex:
            self.q.queue.clear()
        if self.speaking.is_set():
            self.fertig_um = time.time()
        self.speaking.clear()


class Ohren:
    """Hört zu, erkennt Sprache und das Aktivierungswort."""

    def __init__(self, mund: Mund):
        self.mund = mund
        self.model = None
        self.vad = webrtcvad.Vad(2)
        self.lock = threading.Lock()          # nur einer benutzt das Mikrofon gleichzeitig
        self.wake_on = False
        self.wake_thread = None
        self.on_command = None                # Funktion(text), wird bei erkanntem Befehl gerufen
        self.on_state = None                  # Funktion(text) für die Statusanzeige
        self.followup_until = 0.0
        self.whisper_lock = threading.Lock()  # Laptop und Handy teilen sich ein Whisper-Modell
        self.sprache = "de"                   # Sprache der Spracherkennung (aus den Einstellungen)
        # ---- Gesprächsmodus (wie bei Claude: dauerhaft zuhören, ohne „Hey Watson“) ----
        self.gespraech_an = False
        self.gespraech_stumm = False          # Mikrofon kurz stumm (Knopf), Gespräch bleibt offen
        self.wartet = threading.Event()       # gesetzt = Watson denkt/spricht, nicht zuhören
        self.wartet_seit = 0.0
        self.on_gespraech = None              # Funktion(phase, text): hoert / versteht / denkt / spricht / stumm / aus / fehler
        self.on_gespraech_befehl = None       # Funktion(text): erkannte Frage an Watson geben
        self.on_pegel = None                  # Funktion(0..1): Lautstärke fürs Leuchten der Kugel
        self._phase = None

    def _state(self, s):
        if self.on_state:
            try:
                self.on_state(s)
            except Exception:
                pass

    def _whisper(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel("small", device="cpu", compute_type="int8")
        return self.model

    def transcribe(self, audio, sicher=False):
        """Sprache -> Text. sicher=True (Gesprächsmodus): Rauschen und erfundene Untertitel-Sätze ergeben ""."""
        if sicher:
            a = np.asarray(audio, dtype=np.float32)
            if not len(a) or float(np.sqrt(np.mean(a ** 2))) < LEISE_GRENZE:   # nur Rauschen, niemand spricht
                return ""
        with self.whisper_lock:
            segs, _ = self._whisper().transcribe(audio, language=self.sprache, beam_size=1, hotwords="Watson",
                                                 condition_on_previous_text=False, vad_filter=False)
            segs = list(segs)
        if sicher:
            segs = [s for s in segs if not (s.no_speech_prob > 0.6 and s.avg_logprob < -0.7)]
        text = " ".join(s.text.strip() for s in segs).strip()
        if sicher:
            if HALLU_RE.search(text) or len(re.sub(r"\W", "", text)) < 2:
                return ""
            # typische Fantasie-Sätze nur annehmen, wenn Whisper sich sicher ist, dass gesprochen wurde
            if _schluessel(text) in HALLU_KURZ and max((s.no_speech_prob for s in segs), default=1) > 0.15:
                return ""
        return text

    def _record(self, stream, wait_seconds=None, stop_flag=None, pegel=None, stille_ms=None):
        """Wartet auf Sprache und nimmt bis ~0,8 s Stille auf. None, wenn niemand spricht."""
        pre, voiced, silence, started = deque(maxlen=10), [], 0, False
        t0 = time.time()
        n = 0
        while True:
            if stop_flag and stop_flag():
                return None
            if wait_seconds and not started and time.time() - t0 > wait_seconds:
                return None
            data, _ = stream.read(FRAME)
            frame = bytes(data)
            n += 1
            if pegel and n % 4 == 0:                  # ~8× pro Sekunde die Lautstärke melden
                try:
                    rms = float(np.sqrt(np.mean(np.frombuffer(frame, dtype=np.int16).astype(np.float32) ** 2))) / 32768
                    pegel(min(1.0, rms * 12))
                except Exception:
                    pass
            if self.mund.speaking.is_set() or time.time() - self.mund.fertig_um < 0.4:   # nicht sich selbst zuhören
                pre.clear(); voiced, silence, started = [], 0, False
                continue
            speech = self.vad.is_speech(frame, RATE)
            if not started:
                pre.append(frame)
                if speech and sum(self.vad.is_speech(f, RATE) for f in pre) >= 4:
                    started, voiced = True, list(pre)
            else:
                voiced.append(frame)
                silence = 0 if speech else silence + 1
                if silence * 30 > (stille_ms or 800) or len(voiced) * 30 > 30000:
                    pcm = np.frombuffer(b"".join(voiced), dtype=np.int16)
                    if len(pcm) < RATE * 0.4:
                        pre.clear(); voiced, silence, started = [], 0, False
                        continue
                    return pcm.astype(np.float32) / 32768.0

    def listen_once(self, wait_seconds=8):
        """Für den Mikrofon-Knopf: einmal zuhören und den Text zurückgeben."""
        with self.lock:
            self._state("🎙 Ich höre zu …")
            _beep(660)
            with sd.RawInputStream(samplerate=RATE, blocksize=FRAME, channels=1, dtype="int16") as s:
                audio = self._record(s, wait_seconds)
            if audio is None:
                self._state("Bereit")
                return ""
            self._state("Ich verstehe …")
            text = self.transcribe(audio)
            self._state("Bereit")
            return text

    # ---------- "Hey Watson" ----------
    def set_wake(self, on):
        self.wake_on = on
        if on and not (self.wake_thread and self.wake_thread.is_alive()):
            self.wake_thread = threading.Thread(target=self._wake_loop, daemon=True)
            self.wake_thread.start()
        if not on:
            self._state("Bereit")

    def _wake_loop(self):
        try:
            self._whisper()
        except Exception as e:
            self._state(f"Spracherkennung fehlt: {e}")
            return
        while self.wake_on:
            if self.gespraech_an:                     # Gesprächsmodus hat das Mikrofon
                time.sleep(0.5)
                continue
            if not self.lock.acquire(timeout=1):
                continue
            try:
                with sd.RawInputStream(samplerate=RATE, blocksize=FRAME, channels=1, dtype="int16") as s:
                    in_followup = time.time() < self.followup_until
                    self._state("🎙 Folgefrage? Ich höre …" if in_followup else "🎙 Sag „Hey Watson …“")
                    audio = self._record(s, wait_seconds=(self.followup_until - time.time()) if in_followup else None,
                                         stop_flag=lambda: not self.wake_on)
            except Exception as e:
                self._state(f"Mikrofon-Problem: {e}")
                time.sleep(3)
                continue
            finally:
                self.lock.release()
            if audio is None:
                self.followup_until = 0.0
                continue
            text = self.transcribe(audio)
            if not text:
                continue
            if STOP_RE.match(text):
                self.mund.stop()
                continue
            wake = WAKE_RE.search(text)
            if not wake and not in_followup:
                continue
            # nur was NACH „Watson“ kommt, ist der Befehl (Wortreste davor ignorieren)
            command = text[wake.end():].strip(" ,.!?") if wake else text
            if wake and len(command) < 2:              # nur „Hey Watson“ -> Piepton, dann Frage
                _beep()
                self._state("🎙 Ja? Ich höre …")
                with self.lock, sd.RawInputStream(samplerate=RATE, blocksize=FRAME, channels=1, dtype="int16") as s:
                    audio = self._record(s, wait_seconds=7)
                if audio is None:
                    continue
                command = self.transcribe(audio)
                if not command:
                    continue
            self.followup_until = 0.0
            if self.on_command:
                self._state("Watson denkt nach …")
                self.on_command(command)

    def start_followup(self):
        """Nach einer gesprochenen Antwort: kurz ohne „Hey Watson“ weiter zuhören."""
        if self.wake_on:
            self.followup_until = time.time() + FOLLOWUP_SECONDS

    # ---------- Gesprächsmodus (dauerhaft zuhören, wie bei Claude) ----------
    def _g(self, phase, text=""):
        """Meldet der Oberfläche, was gerade passiert. Gleiche Phase ohne neuen Text nur einmal."""
        if phase == self._phase and not text:
            return
        self._phase = phase
        if self.on_gespraech:
            try:
                self.on_gespraech(phase, text)
            except Exception:
                pass

    def gespraech_start(self):
        if self.gespraech_an:
            return {"an": True}
        self.mund.stop()
        self.gespraech_an, self.gespraech_stumm, self._phase = True, False, None
        self.wartet.clear()
        threading.Thread(target=self._gespraech_loop, daemon=True).start()
        return {"an": True}

    def gespraech_stop(self):
        war_an = self.gespraech_an
        self.gespraech_an = False
        self.wartet.clear()
        self.mund.stop()
        if war_an:
            self._g("aus")
        return {"an": False}

    def gespraech_stumm_setzen(self, stumm):
        self.gespraech_stumm = bool(stumm)
        return {"stumm": self.gespraech_stumm}

    def antwort_fertig(self):
        """Watson hat fertig geantwortet (oder es kam keine Antwort) -> wieder zuhören."""
        self.wartet.clear()

    def unterbrechen(self):
        """Wie bei Claude auf die Kugel tippen: Watson hört sofort auf zu reden und hört wieder zu."""
        self.mund.stop()
        self.wartet.clear()
        return {"ok": True}

    def _gespraech_loop(self):
        try:
            self._whisper()
        except Exception as e:
            self._g("fehler", f"Spracherkennung fehlt: {e}")
            self.gespraech_an = False
            return
        while self.gespraech_an:
            if self.wartet.is_set() or self.mund.speaking.is_set():
                if self.mund.speaking.is_set():
                    self._g("spricht")
                elif time.time() - self.wartet_seit > 600:    # Sicherheitsnetz: nie ewig hängen bleiben
                    self.wartet.clear()
                time.sleep(0.1)
                continue
            if self.gespraech_stumm:
                self._g("stumm")
                time.sleep(0.2)
                continue
            if not self.lock.acquire(timeout=1):
                continue
            try:
                with sd.RawInputStream(samplerate=RATE, blocksize=FRAME, channels=1, dtype="int16") as s:
                    self._g("hoert")
                    audio = self._record(s, stop_flag=lambda: (not self.gespraech_an or self.gespraech_stumm
                                                               or self.wartet.is_set() or self.mund.speaking.is_set()),
                                         pegel=self.on_pegel, stille_ms=1000)
            except Exception as e:
                self._g("fehler", f"Mikrofon-Problem: {e}")
                time.sleep(2)
                continue
            finally:
                self.lock.release()
            if audio is None or not self.gespraech_an:
                continue
            self._g("versteht")
            try:
                text = self.transcribe(audio, sicher=True)
            except Exception as e:
                self._g("fehler", f"Spracherkennung: {e}")
                continue
            if not self.gespraech_an:
                break
            if not text:
                self._g("hoert")
                continue
            if GESPRAECH_ENDE_RE.match(text):
                self.gespraech_stop()
                break
            if STOP_RE.match(text):
                self.mund.stop()
                continue
            self.wartet_seit = time.time()
            self.wartet.set()
            self._g("denkt", text)
            if self.on_gespraech_befehl:
                try:
                    self.on_gespraech_befehl(text)
                except Exception:
                    self.wartet.clear()
            else:
                self.wartet.clear()
