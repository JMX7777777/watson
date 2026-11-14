"""
Watsons Video-Studio: Videos bearbeiten und für viele Kanäle (YouTube, Instagram, TikTok, …) passend vorbereiten.

- FFmpeg (freies Video-Werkzeug, GPL) wird beim ersten Benutzen aus der bekannten Quelle für Windows-Versionen geladen
  (github.com/BtbN/FFmpeg-Builds, mit Prüfsumme) und nach <Daten>\\werkzeuge\\ffmpeg gelegt.
- Ablauf: 1) Schnitt (Clips kürzen und zusammenfügen) -> 2) Untertitel (Whisper, optional) -> 3) pro Kanal: Format
  (hochkant/quer/quadratisch), Text-Einblendung, Logo, Musik, Lautstärke, Dateigröße -> 4) Titel/Text/Hashtags pro Kanal.
- Kanäle: feste Liste + eigene Kanäle. Pro Kanal wählt der Nutzer den Weg zum Hochladen:
    assistent    – Watson legt Video + Text bereit und öffnet die Upload-Seite; der Nutzer lädt hoch und postet (Stufe 1)
    schnittstelle – offizielle Schnittstelle des Kanals (Stufe 2, kommt)
    dienst       – bezahlter Dienst wie Buffer/Metricool (Stufe 3, kommt)
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

import pfade

H = {}                       # Helfer aus watson_studio: frage, stark, schnell, whisper, whisper_lock, sprache, system
FF_ORDNER = pfade.DATEN / "werkzeuge" / "ffmpeg"
KANAL_DATEI = pfade.DATEN / "kanaele.json"
AUSGABE = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Videos" / "Watson"
OHNE_FENSTER = 0x08000000
JOBS = {}

# ---------------- KI-Video-Plattformen (Übersicht für Menschen, die nicht wissen, was es gibt) ----------------
# Nur Links zum Öffnen – Watson meldet nirgends an und bezahlt nichts. Keine Werbe-/Partner-Links.
# Bewusst ohne genaue Preise: Gratis-Mengen und Preise ändern sich ständig. Stand der Liste:
PLATTFORMEN_STAND = "November 2026"
PLATTFORMEN = [
    {"name": "Kling AI", "url": "https://klingai.com", "art": "gratis", "kategorie": "Text oder Bild → Video",
     "text": "Täglich neue Gratis-Guthaben für kurze Clips (mit Wasserzeichen). Sehr gute Bewegungen. Mehr gegen Abo."},
    {"name": "Hailuo (MiniMax)", "url": "https://hailuoai.video", "art": "gratis", "kategorie": "Text oder Bild → Video",
     "text": "Einige Gratis-Clips pro Tag, sehr echt wirkende Bilder. Gratis mit Wasserzeichen."},
    {"name": "Google Flow (Veo)", "url": "https://labs.google/flow", "art": "gratis", "kategorie": "Text oder Bild → Video",
     "text": "Googles Video-Werkstatt mit täglichem Gratis-Guthaben; das stärkste Modell (Veo) voll nur mit Google-Abo."},
    {"name": "Pika", "url": "https://pika.art", "art": "gratis", "kategorie": "Text oder Bild → Video",
     "text": "Monatliches Gratis-Guthaben, einfach zu bedienen, lustige Effekte. Gratis nur kleine Auflösung."},
    {"name": "Dreamina (CapCut)", "url": "https://dreamina.capcut.com", "art": "gratis", "kategorie": "Text oder Bild → Video",
     "text": "Von den CapCut-Machern: regelmäßig Gratis-Guthaben für Bilder und kurze Videos."},
    {"name": "Runway", "url": "https://runwayml.com", "art": "test", "kategorie": "Text oder Bild → Video",
     "text": "Profi-Werkzeug. Einmaliges Gratis-Guthaben zum Ausprobieren, danach nur mit Abo."},
    {"name": "Luma Dream Machine", "url": "https://lumalabs.ai/dream-machine", "art": "bezahlt", "kategorie": "Text oder Bild → Video",
     "text": "Hochwertige, filmische Clips. Nur mit Abo."},
    {"name": "HeyGen", "url": "https://www.heygen.com", "art": "gratis", "kategorie": "Sprechende Person (Avatar)",
     "text": "Eine KI-Person spricht deinen Text – auch in vielen Sprachen. Gratis wenige kurze Videos im Monat, mit Wasserzeichen."},
    {"name": "CapCut", "url": "https://www.capcut.com", "art": "gratis", "kategorie": "Bearbeiten mit KI-Hilfe",
     "text": "Kostenloser Video-Schnitt mit KI-Werkzeugen (Untertitel, Hintergrund entfernen …). Erzeugt keine Videos aus Text."},
    {"name": "Canva", "url": "https://www.canva.com", "art": "gratis", "kategorie": "Bearbeiten mit KI-Hilfe",
     "text": "Vorlagen für Kurzvideos und Beiträge, einfache KI-Werkzeuge. Gratis-Plan, mehr mit Abo."},
]
PLATTFORMEN_HINWEISE = [
    "„Gratis“ heißt fast immer: wenige, kurze Clips, oft mit Wasserzeichen und nicht für gewerbliche Nutzung. Prüfe Preise und Bedingungen auf der Seite selbst – sie ändern sich oft.",
    "Für fast alle brauchst du ein Konto. Watson meldet dich nirgends an und bezahlt nichts.",
    "Kennzeichne KI-Videos ehrlich: YouTube, TikTok und Instagram verlangen das bei echt wirkenden KI-Inhalten.",
    "Mach keine echten Menschen ohne deren Erlaubnis nach und täusche niemanden – sei ehrlich.",
    "Tipp: Fertiges KI-Video herunterladen und dann hier im Video-Studio für alle Kanäle aufbereiten.",
]


def plattformen():
    return {"liste": PLATTFORMEN, "hinweise": PLATTFORMEN_HINWEISE, "stand": PLATTFORMEN_STAND}


FORMATE = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350), "2:3": (1000, 1500)}

# Richtwerte (Stand 2026, können sich ändern – jeder Kanal ist in Watson änderbar)
KANAELE_STANDARD = [
    {"id": "youtube", "name": "YouTube (Video)", "format": "16:9", "max_sek": 43200, "max_mb": 0, "titel_max": 100, "text_max": 5000, "url": "https://studio.youtube.com/"},
    {"id": "youtube_shorts", "name": "YouTube Shorts", "format": "9:16", "max_sek": 180, "max_mb": 0, "titel_max": 100, "text_max": 5000, "url": "https://studio.youtube.com/"},
    {"id": "instagram_reels", "name": "Instagram Reels", "format": "9:16", "max_sek": 180, "max_mb": 0, "titel_max": 0, "text_max": 2200, "url": "https://www.instagram.com/"},
    {"id": "instagram_feed", "name": "Instagram Beitrag", "format": "4:5", "max_sek": 60, "max_mb": 0, "titel_max": 0, "text_max": 2200, "url": "https://www.instagram.com/"},
    {"id": "tiktok", "name": "TikTok", "format": "9:16", "max_sek": 600, "max_mb": 0, "titel_max": 0, "text_max": 2200, "url": "https://www.tiktok.com/tiktokstudio/upload"},
    {"id": "facebook", "name": "Facebook", "format": "16:9", "max_sek": 14400, "max_mb": 0, "titel_max": 255, "text_max": 5000, "url": "https://www.facebook.com/"},
    {"id": "facebook_reels", "name": "Facebook Reels", "format": "9:16", "max_sek": 90, "max_mb": 0, "titel_max": 0, "text_max": 2200, "url": "https://www.facebook.com/reels/create"},
    {"id": "x", "name": "X (Twitter)", "format": "16:9", "max_sek": 140, "max_mb": 512, "titel_max": 0, "text_max": 280, "url": "https://x.com/compose/post"},
    {"id": "linkedin", "name": "LinkedIn", "format": "1:1", "max_sek": 600, "max_mb": 0, "titel_max": 0, "text_max": 3000, "url": "https://www.linkedin.com/feed/"},
    {"id": "threads", "name": "Threads", "format": "9:16", "max_sek": 300, "max_mb": 0, "titel_max": 0, "text_max": 500, "url": "https://www.threads.net/"},
    {"id": "pinterest", "name": "Pinterest", "format": "2:3", "max_sek": 900, "max_mb": 0, "titel_max": 100, "text_max": 500, "url": "https://www.pinterest.com/pin-creation-tool/"},
    {"id": "snapchat", "name": "Snapchat Spotlight", "format": "9:16", "max_sek": 60, "max_mb": 0, "titel_max": 0, "text_max": 160, "url": "https://my.snapchat.com/"},
    {"id": "vimeo", "name": "Vimeo", "format": "16:9", "max_sek": 0, "max_mb": 0, "titel_max": 128, "text_max": 5000, "url": "https://vimeo.com/upload"},
    {"id": "rumble", "name": "Rumble", "format": "16:9", "max_sek": 0, "max_mb": 0, "titel_max": 100, "text_max": 5000, "url": "https://rumble.com/upload.php"},
]
# Zugangsdaten pro Kanal (für die offiziellen Schnittstellen). Die WERTE liegen nur im Windows-Tresor (tresor.py),
# Kennung „kanal_<kanal>_<feld>“ – nie in kanaele.json, nie in Sicherungen, nie beim KI-Gehirn.
_META = [("app_id", "App-ID (Meta)"), ("app_secret", "App-Secret (Meta)"), ("token", "Zugriffs-Token")]
ZUGANG = {
    "youtube": [("client_id", "Client-ID (Google Cloud)"), ("client_secret", "Client-Secret (Google Cloud)")],
    "youtube_shorts": [("client_id", "Client-ID (Google Cloud)"), ("client_secret", "Client-Secret (Google Cloud)")],
    "instagram_reels": _META, "instagram_feed": _META, "facebook": _META, "facebook_reels": _META, "threads": _META,
    "tiktok": [("client_key", "Client-Key (TikTok)"), ("client_secret", "Client-Secret (TikTok)")],
    "x": [("api_key", "API-Key"), ("api_secret", "API-Secret"), ("access_token", "Access-Token"), ("access_secret", "Access-Token-Secret")],
    "linkedin": [("client_id", "Client-ID"), ("client_secret", "Client-Secret")],
    "pinterest": [("app_id", "App-ID"), ("app_secret", "App-Secret"), ("token", "Zugriffs-Token")],
    "snapchat": [("client_id", "Client-ID"), ("client_secret", "Client-Secret")],
    "vimeo": [("token", "Zugriffs-Token (Vimeo)")], "rumble": [("api_key", "API-Schlüssel")],
}
ZUGANG_IMMER = [("konto", "Benutzername / E-Mail des Kontos")]


def zugang_kennung(kid, feld):
    return ("kanal_" + re.sub(r"[^a-z0-9_]", "", str(kid).lower())[:30] + "_" + re.sub(r"[^a-z0-9_]", "", str(feld).lower())[:24])[:64]


def zugang_felder(kid, eigene_felder=()):
    """Welche Zugangsdaten es für einen Kanal gibt – mit „gespeichert ja/nein“, NIE mit den Werten."""
    import tresor
    felder = list(ZUGANG_IMMER) + list(ZUGANG.get(kid, [("api_key", "API-Schlüssel")]))
    bekannt = {f for f, _ in felder}
    felder += [(f, n) for f, n in eigene_felder if f not in bekannt]
    return [{"feld": f, "name": n, "kennung": zugang_kennung(kid, f), "gespeichert": tresor.vorhanden(zugang_kennung(kid, f))}
            for f, n in felder]


WEGE = {"assistent": "Watson legt alles bereit – ich lade hoch und poste selbst",
        "schnittstelle": "Offizielle Schnittstelle des Kanals (kommt in Stufe 2)",
        "dienst": "Bezahlter Dienst wie Buffer oder Metricool (kommt in Stufe 3)"}


def init(**helfer):
    H.update(helfer)


# ---------------- Kanäle ----------------
def kanaele():
    try:
        d = json.loads(KANAL_DATEI.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    eigene = {k["id"]: k for k in d.get("kanaele", [])}
    out = []
    for k in KANAELE_STANDARD:                      # Standard-Kanäle + Änderungen des Nutzers
        x = dict(k, weg="assistent", aktiv=False, eigener=False)
        x.update({kk: v for kk, v in eigene.pop(k["id"], {}).items() if kk not in ("id", "eigener")})
        out.append(x)
    for k in eigene.values():                       # selbst eingetragene Kanäle
        out.append(dict({"weg": "assistent", "aktiv": True, "format": "9:16", "max_sek": 0, "max_mb": 0,
                         "titel_max": 0, "text_max": 2000, "url": ""}, **k, eigener=True))
    return out


def kanal_speichern(k):
    """Einen Kanal ändern oder neu anlegen (eigener Kanal)."""
    try:
        d = json.loads(KANAL_DATEI.read_text(encoding="utf-8"))
    except Exception:
        d = {"kanaele": []}
    name = str(k.get("name") or "").strip()[:60]
    kid = re.sub(r"[^a-z0-9_]", "", str(k.get("id") or "").lower())[:40] or \
        ("eigen_" + re.sub(r"[^a-z0-9]", "", name.lower())[:14] + "_" + uuid.uuid4().hex[:5])   # immer eindeutig
    url = str(k.get("url") or "").strip()[:300]
    if url and not url.startswith("https://"):
        return {"error": "Die Upload-Adresse muss mit https:// beginnen."}
    neu = {"id": kid}
    for f in ("name", "format", "weg", "url"):
        if f in k:
            neu[f] = str(k[f]).strip()[:300]
    for f in ("max_sek", "max_mb", "titel_max", "text_max"):
        if f in k:
            try:
                neu[f] = max(0, int(float(k[f] or 0)))
            except ValueError:
                pass
    if "aktiv" in k:
        neu["aktiv"] = bool(k["aktiv"])
    if neu.get("format") and neu["format"] not in FORMATE and neu["format"] != "original":
        neu["format"] = "9:16"
    if neu.get("weg") and neu["weg"] not in WEGE:
        neu["weg"] = "assistent"
    liste = [x for x in d.get("kanaele", []) if x.get("id") != kid]
    alt = next((x for x in d.get("kanaele", []) if x.get("id") == kid), {})
    liste.append(dict(alt, **neu))
    d["kanaele"] = liste
    KANAL_DATEI.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "id": kid}


def kanal_loeschen(kid):
    try:
        d = json.loads(KANAL_DATEI.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": True}
    d["kanaele"] = [x for x in d.get("kanaele", []) if x.get("id") != kid]
    KANAL_DATEI.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}


# ---------------- FFmpeg holen ----------------
def _einstellung(name, standard=None):
    try:
        return (H["einstellungen"]() or {}).get(name, standard) if "einstellungen" in H else standard
    except Exception:
        return standard


def ffmpeg_pfad():
    eigen = _einstellung("video_ffmpeg_pfad", "")             # vom Nutzer gewähltes, vorhandenes FFmpeg
    if eigen and (Path(eigen) / "ffmpeg.exe").exists() and (Path(eigen) / "ffprobe.exe").exists():
        return Path(eigen)
    if (FF_ORDNER / "ffmpeg.exe").exists() and (FF_ORDNER / "ffprobe.exe").exists():
        return FF_ORDNER
    w = shutil.which("ffmpeg")
    if w and (Path(w).parent / "ffprobe.exe").exists():
        return Path(w).parent
    return None


def ffmpeg_status():
    p = ffmpeg_pfad()
    return {"da": bool(p), "ordner": str(p) if p else "", "auto": bool(_einstellung("video_ffmpeg_auto", False)),
            "eigen": _einstellung("video_ffmpeg_pfad", "") or ""}


def eigenes_ffmpeg_pruefen(datei):
    """Der Nutzer wählt eine vorhandene ffmpeg.exe – ffprobe.exe muss im selben Ordner liegen."""
    p = Path(datei)
    ordner = p.parent if p.suffix.lower() == ".exe" else p
    if not (ordner / "ffmpeg.exe").exists() or not (ordner / "ffprobe.exe").exists():
        return {"error": "Im gewählten Ordner müssen ffmpeg.exe UND ffprobe.exe liegen."}
    try:
        r = subprocess.run([str(ordner / "ffmpeg.exe"), "-version"], capture_output=True, text=True, timeout=20,
                           creationflags=OHNE_FENSTER)
        zeile = (r.stdout or "").splitlines()[0] if r.stdout else ""
    except Exception as e:
        return {"error": f"Diese ffmpeg.exe lässt sich nicht starten: {e}"}
    if "ffmpeg version" not in zeile:
        return {"error": "Das scheint keine ffmpeg.exe zu sein."}
    return {"ok": True, "ordner": str(ordner), "version": zeile[:80]}


def _echter_prozessor_arm():
    """True auf ARM-Computern – auch wenn Watsons Python als x64 emuliert läuft (dann meldet die Umgebung „AMD64“)."""
    try:
        import ctypes
        prozess, nativ = ctypes.c_ushort(0), ctypes.c_ushort(0)
        k32 = ctypes.windll.kernel32
        if k32.IsWow64Process2(k32.GetCurrentProcess(), ctypes.byref(prozess), ctypes.byref(nativ)):
            return nativ.value == 0xAA64                       # IMAGE_FILE_MACHINE_ARM64
    except Exception:
        pass
    return "ARM" in (os.environ.get("PROCESSOR_IDENTIFIER", "") + os.environ.get("PROCESSOR_ARCHITECTURE", "")).upper()


def ffmpeg_holen(fortschritt=None):
    """Lädt FFmpeg (GPL-Version) passend zum Prozessor, prüft die Prüfsumme und packt nur ffmpeg/ffprobe aus."""
    if ffmpeg_pfad():
        return {"ok": True}
    arm = _echter_prozessor_arm()
    kopf = {"User-Agent": "Watson-Video-Studio", "Accept": "application/vnd.github+json"}
    with urllib.request.urlopen(urllib.request.Request("https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest", headers=kopf), timeout=30) as r:
        rel = json.load(r)
    assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
    endung = "winarm64-gpl" if arm else "win64-gpl"
    stabil = sorted((n for n in assets if re.match(rf"ffmpeg-n\d+\.\d+-latest-{endung}-\d+\.\d+\.zip$", n)), reverse=True)
    name = stabil[0] if stabil else f"ffmpeg-master-latest-{endung}.zip"
    if name not in assets or "checksums.sha256" not in assets:
        raise RuntimeError("FFmpeg-Download nicht gefunden.")
    with urllib.request.urlopen(urllib.request.Request(assets["checksums.sha256"], headers=kopf), timeout=30) as r:
        summen = r.read().decode()
    soll = next((z.split()[0] for z in summen.splitlines() if z.strip().endswith(name)), None)
    ziel = pfade.DATEN / "werkzeuge" / name
    ziel.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(assets[name], headers=kopf), timeout=60) as r, open(ziel, "wb") as f:
        gesamt = int(r.headers.get("Content-Length") or 0)
        geladen = 0
        while True:
            stueck = r.read(1 << 20)
            if not stueck:
                break
            f.write(stueck); h.update(stueck); geladen += len(stueck)
            if fortschritt and gesamt:
                fortschritt(geladen / gesamt)
    if not soll or h.hexdigest() != soll:
        ziel.unlink(missing_ok=True)
        raise RuntimeError("Prüfsumme von FFmpeg stimmt nicht – Download verworfen.")
    FF_ORDNER.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ziel) as z:
        for n in z.namelist():
            if n.endswith(("/bin/ffmpeg.exe", "/bin/ffprobe.exe")):
                with z.open(n) as q, open(FF_ORDNER / Path(n).name, "wb") as zf:
                    shutil.copyfileobj(q, zf)
            if n.endswith("/LICENSE.txt"):
                with z.open(n) as q, open(FF_ORDNER / "LICENSE.txt", "wb") as zf:
                    shutil.copyfileobj(q, zf)
    ziel.unlink(missing_ok=True)
    return {"ok": True, "datei": name}


def _ff(name):
    p = ffmpeg_pfad()
    if not p:
        raise RuntimeError("FFmpeg fehlt noch – bitte im Video-Studio auf „Video-Werkzeug laden“ klicken.")
    return str(p / f"{name}.exe")


def info(pfad):
    """Länge, Größe und ob Ton dabei ist."""
    r = subprocess.run([_ff("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(pfad)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=OHNE_FENSTER, timeout=60)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
    breite, hoehe = int(v.get("width") or 0), int(v.get("height") or 0)
    if str((v.get("tags") or {}).get("rotate", "0")) in ("90", "270") or any(
            abs(int(sd.get("rotation", 0) or 0)) == 90 for sd in v.get("side_data_list", []) or []):
        breite, hoehe = hoehe, breite
    return {"dauer": float((d.get("format") or {}).get("duration") or 0), "breite": breite, "hoehe": hoehe,
            "ton": a, "mb": round(int((d.get("format") or {}).get("size") or 0) / 1e6, 1), "name": Path(pfad).name}


# ---------------- FFmpeg ausführen (mit Fortschritt) ----------------
def _laufen(args, dauer, job, anteil_von, anteil_bis, schritt, cwd=None):
    job["schritt"] = schritt
    p = subprocess.Popen([_ff("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + args,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                         creationflags=OHNE_FENSTER, cwd=cwd)
    job["_proc"] = p
    fehler = []
    threading.Thread(target=lambda: fehler.extend(p.stderr.readlines()), daemon=True).start()
    for zeile in p.stdout:
        if job.get("abbrechen"):
            p.kill()
            raise RuntimeError("abgebrochen")
        m = re.match(r"out_time_(?:us|ms)=(\d+)", zeile.strip())
        if m and dauer > 0:
            t = int(m.group(1)) / 1e6
            job["prozent"] = round(anteil_von + (anteil_bis - anteil_von) * min(1.0, t / dauer), 1)
    p.wait()
    if job.get("abbrechen"):
        raise RuntimeError("abgebrochen")
    if p.returncode != 0:
        raise RuntimeError("FFmpeg-Fehler: " + "".join(fehler)[-600:])
    job["prozent"] = anteil_bis


def _pfad_filter(p):
    """Windows-Pfad für FFmpeg-Filter (subtitles=, movie=) sicher schreiben."""
    return str(Path(p)).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _text_filter(t):
    return str(t).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")


# ---------------- Schritt 1: Schnitt ----------------
def _schnitt(clips, ziel, job):
    """Clips kürzen und zu einem Video zusammenfügen (1920 px, Seitenverhältnis des ersten Clips, mit Rand)."""
    infos = [info(c["datei"]) for c in clips]
    b0, h0 = infos[0]["breite"] or 1920, infos[0]["hoehe"] or 1080
    s = 1920 / max(b0, h0)
    W, Hh = int(b0 * s) // 2 * 2, int(h0 * s) // 2 * 2
    args, filt, teile, dauer = [], [], [], 0.0
    for i, (c, inf) in enumerate(zip(clips, infos)):
        von = max(0.0, float(c.get("von") or 0))
        bis = float(c.get("bis") or 0) or inf["dauer"]
        bis = min(bis, inf["dauer"] or bis)
        if bis - von < 0.2:
            raise RuntimeError(f"Clip „{inf['name']}“: Ende muss nach dem Anfang liegen.")
        dauer += bis - von
        args += ["-ss", f"{von:.3f}", "-to", f"{bis:.3f}", "-i", str(c["datei"])]
        filt.append(f"[{i}:v]scale={W}:{Hh}:force_original_aspect_ratio=decrease,pad={W}:{Hh}:(ow-iw)/2:(oh-ih)/2:color=black,"
                    f"fps=30,setsar=1,format=yuv420p[v{i}]")
        if inf["ton"]:
            filt.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            filt.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{bis - von:.3f}[a{i}]")
        teile.append(f"[v{i}][a{i}]")
    filt.append("".join(teile) + f"concat=n={len(clips)}:v=1:a=1[v][a]")
    _laufen(args + ["-filter_complex", ";".join(filt), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(ziel)], dauer, job, 2, 25, "Schneiden und zusammenfügen")
    return dauer


# ---------------- Schritt 2: Untertitel (Whisper) ----------------
def _zeit(t):
    h, r = divmod(max(0.0, t), 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s - int(s)) * 1000):03}"


def _untertitel(video, srt, job):
    if not H.get("whisper") or not H.get("whisper_lock"):
        job["hinweis"] = "Untertitel übersprungen – die Spracherkennung ist auf diesem Computer nicht verfügbar."
        srt.write_text("", encoding="utf-8")
        return ""
    job["schritt"] = "Untertitel erkennen (Whisper)"
    wav = srt.with_suffix(".wav")
    subprocess.run([_ff("ffmpeg"), "-y", "-loglevel", "error", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)],
                   check=True, creationflags=OHNE_FENSTER, timeout=1800)
    import wave
    import numpy as np
    with wave.open(str(wav)) as w:                 # selbst einlesen (der eingebaute Audio-Leser passt nicht zu jeder PyAV-Version)
        ton = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    modell = H["whisper"]()
    with H["whisper_lock"]:
        segs, _ = modell.transcribe(ton, language=H.get("sprache", lambda: "de")(), beam_size=1, vad_filter=True,
                                    condition_on_previous_text=False)
        segs = list(segs)
    wav.unlink(missing_ok=True)
    zeilen = []
    for i, s in enumerate(segs, 1):
        text = s.text.strip()
        if not text:
            continue
        # lange Sätze in zwei Zeilen teilen (besser lesbar, auch hochkant)
        if len(text) > 42:
            mitte = text.rfind(" ", 0, len(text) // 2 + 10)
            if mitte > 10:
                text = text[:mitte] + "\n" + text[mitte + 1:]
        zeilen.append(f"{len(zeilen) + 1}\n{_zeit(s.start)} --> {_zeit(s.end)}\n{text}\n")
    srt.write_text("\n".join(zeilen), encoding="utf-8")
    job["prozent"] = 35
    return " ".join(s.text.strip() for s in segs)


# ---------------- Schritt 3: pro Kanal fertig machen ----------------
def _kanal_video(basis, dauer, kanal, opt, srt, ziel, job, von, bis):
    fmt = kanal.get("format") or "9:16"
    infos = info(basis)
    W, Hh = FORMATE.get(fmt, (infos["breite"] // 2 * 2, infos["hoehe"] // 2 * 2))
    max_sek = int(kanal.get("max_sek") or 0)
    laenge = min(dauer, max_sek) if max_sek else dauer
    args = ["-i", str(basis)]
    n = 1
    musik = (opt.get("musik") or {}).get("datei")
    logo = (opt.get("logo") or {}).get("datei")
    if musik:
        args += ["-stream_loop", "-1", "-i", str(musik)]; m_idx = n; n += 1
    if logo:
        args += ["-i", str(logo)]; l_idx = n; n += 1
    f = []
    if opt.get("zuschnitt") == "einpassen":            # ganzes Bild sichtbar, Rand mit unscharfem Hintergrund
        f.append(f"[0:v]split[g][h];[h]scale={W}:{Hh}:force_original_aspect_ratio=increase,crop={W}:{Hh},boxblur=24:4[hg];"
                 f"[g]scale={W}:{Hh}:force_original_aspect_ratio=decrease[vg];[hg][vg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")
    else:                                              # Bild füllt alles, Ränder werden abgeschnitten
        f.append(f"[0:v]scale={W}:{Hh}:force_original_aspect_ratio=increase,crop={W}:{Hh},setsar=1[v0]")
    akt = "v0"
    if srt and srt.exists() and srt.stat().st_size > 0:
        groesse = 9 if W < Hh else 15            # Schriftgröße bezogen auf die Untertitel-Bildhöhe (288)
        # FFmpeg läuft im Arbeitsordner -> nur der Dateiname (keine Sonderzeichen wie ' aus Ordnernamen im Filter)
        f.append(f"[{akt}]subtitles={srt.name}:force_style='FontName=Arial,FontSize={groesse},Bold=1,"
                 f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,MarginV={60 if W < Hh else 40}'[vs]")
        akt = "vs"
    t = opt.get("text") or {}
    if (t.get("inhalt") or "").strip():
        y = {"oben": "h*0.08", "mitte": "(h-text_h)/2", "unten": "h*0.80"}.get(t.get("position"), "h*0.08")
        zeit = ""
        if float(t.get("bis") or 0) > 0:
            zeit = f":enable='between(t,{float(t.get('von') or 0):.2f},{float(t['bis']):.2f})'"
        font = _pfad_filter(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf")
        f.append(f"[{akt}]drawtext=fontfile='{font}':text='{_text_filter(t['inhalt'][:120])}':fontsize={int(W * 0.06)}:"
                 f"fontcolor=white:borderw=4:bordercolor=black@0.85:x=(w-text_w)/2:y={y}{zeit}[vt]")
        akt = "vt"
    if logo:
        ecke = {"oben_links": "20:20", "oben_rechts": "W-w-20:20", "unten_links": "20:H-h-20"}.get(
            (opt.get("logo") or {}).get("ecke"), "W-w-20:H-h-20")
        f.append(f"[{l_idx}:v]scale={int(W * 0.16)}:-1,format=rgba,colorchannelmixer=aa=0.85[lg];[{akt}][lg]overlay={ecke}[vl]")
        akt = "vl"
    f.append(f"[{akt}]format=yuv420p[vout]")
    a = "[0:a]"
    if opt.get("lautstaerke_angleichen", True):
        f.append(f"{a}loudnorm=I=-14:TP=-1.5:LRA=11[an]"); a = "[an]"
    if musik:
        vol = max(0.02, min(1.0, float((opt.get("musik") or {}).get("lautstaerke") or 0.15)))
        f.append(f"[{m_idx}:a]volume={vol:.2f},aresample=48000[mu];{a}[mu]amix=inputs=2:duration=first:dropout_transition=2[am]")
        a = "[am]"
    f.append(f"{a}aformat=channel_layouts=stereo[aout]")
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    max_mb = int(kanal.get("max_mb") or 0)
    if max_mb and laenge > 0:                          # Dateigröße einhalten
        kbit = int(max_mb * 8000 * 0.92 / laenge) - 160
        if kbit < 8000:
            enc = ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{max(300, kbit)}k", "-maxrate", f"{max(300, kbit)}k",
                   "-bufsize", f"{max(600, kbit * 2)}k", "-pix_fmt", "yuv420p"]
    _laufen(args + ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]", "-t", f"{laenge:.3f}", "-r", "30"] + enc +
            ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(ziel)],
            laenge, job, von, bis, f"Video für {kanal['name']} ({fmt})", cwd=str(srt.parent) if srt else None)
    return laenge


# ---------------- Schritt 4: Titel, Text, Hashtags pro Kanal ----------------
def _texte(thema, gesprochen, gewaehlt):
    if "frage" not in H:
        return {}
    beschreibung = "\n".join(f"- {k['id']}: {k['name']} (Titel bis {k.get('titel_max') or 'keiner'} Zeichen, Text bis "
                             f"{k.get('text_max') or 2000} Zeichen)" for k in gewaehlt)
    system = (H["system"]() if "system" in H else "") + (
        "\n\nDU SCHREIBST JETZT TEXTE FÜR EIN VIDEO, das der Nutzer auf mehreren Kanälen veröffentlichen will. Schreib für "
        "jeden Kanal passend zu seiner Art (YouTube ausführlicher, TikTok/Reels kurz und lebendig, X sehr kurz). Ehrlich, "
        "nichts übertreiben, keine Klick-Fallen, keine erfundenen Tatsachen. Hashtags passend und sparsam (3–8). Antworte NUR "
        "als JSON: {\"<kanal-id>\": {\"titel\": \"…\", \"text\": \"…\", \"hashtags\": [\"#…\"]}}")
    roh, _ = H["frage"]([{"role": "system", "content": system},
                         {"role": "user", "content": f"Worum geht es (vom Nutzer): {thema or '(nicht angegeben)'}\n\n"
                          f"Was im Video gesprochen wird (Auszug): {(gesprochen or '(kein Ton erkannt)')[:3000]}\n\n"
                          f"Kanäle:\n{beschreibung}"}], H.get("stark") or H.get("schnell"))
    m = re.search(r"\{[\s\S]*\}", roh or "")
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    out = {}
    for k in gewaehlt:
        x = d.get(k["id"]) or {}
        titel = str(x.get("titel") or "")[: int(k["titel_max"])] if k.get("titel_max") else ""
        roh_tags = x.get("hashtags") or []
        if isinstance(roh_tags, str):
            roh_tags = re.split(r"[\s,]+", roh_tags)
        tags = " ".join(str(h) if str(h).startswith("#") else "#" + str(h) for h in roh_tags if str(h).strip("# "))
        tags = " ".join(tags.split()[:8])
        text = str(x.get("text") or "").strip()
        limit = int(k.get("text_max") or 2000)
        if len(text) + len(tags) + 2 > limit:
            text = text[: max(0, limit - len(tags) - 3)].rstrip() + "…"
        out[k["id"]] = {"titel": titel, "text": text, "hashtags": tags}
    return out


# ---------------- Ganzer Auftrag ----------------
def starten(auftrag):
    """auftrag = {clips:[{datei,von,bis}], kanaele:[ids], untertitel, zuschnitt, text, musik, logo, lautstaerke_angleichen, thema, name}"""
    clips = [c for c in (auftrag.get("clips") or []) if c.get("datei") and Path(c["datei"]).exists()]
    if not clips:
        return {"error": "Bitte zuerst mindestens ein Video hinzufügen."}
    alle = {k["id"]: k for k in kanaele()}
    gewaehlt = [alle[i] for i in (auftrag.get("kanaele") or []) if i in alle]
    if not gewaehlt:
        return {"error": "Bitte mindestens einen Kanal auswählen."}
    auto_laden = False
    if not ffmpeg_pfad():
        if not _einstellung("video_ffmpeg_auto", False):
            return {"error": "Das Video-Werkzeug (FFmpeg) fehlt noch. Bitte oben „Video-Werkzeug laden“ klicken, ein "
                             "eigenes FFmpeg wählen oder das automatische Laden erlauben."}
        auto_laden = True                                     # der Nutzer hat erlaubt, dass Watson es bei Bedarf lädt
    jid = uuid.uuid4().hex[:8]
    name = re.sub(r'[\\/:*?"<>|]+', "_", str(auftrag.get("name") or "").strip())[:60] or time.strftime("Video_%Y-%m-%d_%H%M")
    ordner = AUSGABE / name
    n = 2
    while ordner.exists() or any(j.get("ordner") == str(ordner) and not j.get("fertig") for j in JOBS.values()):
        ordner = AUSGABE / f"{name}_{n}"; n += 1                  # nichts Fertiges überschreiben
    job = {"id": jid, "prozent": 0, "schritt": "Startet …", "fertig": False, "fehler": "", "ordner": str(ordner), "ergebnisse": []}
    JOBS[jid] = job

    def arbeit():
        try:
            if auto_laden:
                job["schritt"] = "Video-Werkzeug (FFmpeg) wird geladen – einmalig"
                ffmpeg_holen(lambda a: job.update(prozent=round(a * 2, 1)))
            ordner.mkdir(parents=True, exist_ok=True)
            arbeits = ordner / f"_arbeit_{jid}"
            arbeits.mkdir(exist_ok=True)
            basis = arbeits / "schnitt.mp4"
            dauer = _schnitt(clips, basis, job)
            srt, gesprochen = None, ""
            if auftrag.get("untertitel"):
                srt = arbeits / "untertitel.srt"
                gesprochen = _untertitel(basis, srt, job)
                if auftrag.get("untertitel_pruefen", True) and srt.stat().st_size > 0:
                    # Der Nutzer sieht die erkannten Untertitel und kann Fehler verbessern, bevor die Videos entstehen
                    job.update(schritt="Bitte Untertitel prüfen und bestätigen", srt_text=srt.read_text(encoding="utf-8"),
                               warte_auf_untertitel=True)
                    while job.get("warte_auf_untertitel") and not job.get("abbrechen"):
                        time.sleep(0.3)
                    if job.get("abbrechen"):
                        raise RuntimeError("abgebrochen")
                    if job.get("srt_neu") is not None:
                        srt.write_text(job["srt_neu"], encoding="utf-8")
                        gesprochen = " ".join(z for z in job["srt_neu"].splitlines()
                                              if z.strip() and "-->" not in z and not z.strip().isdigit())
                shutil.copy(srt, ordner / "untertitel.srt")
            job["schritt"] = "Titel und Texte schreiben"
            try:
                texte = _texte(auftrag.get("thema", ""), gesprochen, gewaehlt)
            except Exception as e:
                texte = {}
                job["hinweis"] = f"Texte konnten nicht geschrieben werden: {e}"
            # Kanäle mit gleichem Format teilen sich ein Video (spart Zeit)
            fertig_fmt = {}
            schritt = 55.0 / max(1, len({(k.get('format'), k.get('max_sek'), k.get('max_mb')) for k in gewaehlt}))
            p = 40.0
            for k in gewaehlt:
                schl = (k.get("format"), int(k.get("max_sek") or 0), int(k.get("max_mb") or 0))
                datei = ordner / f"{k['id']}.mp4"
                if schl in fertig_fmt:
                    shutil.copy(fertig_fmt[schl], datei)
                else:
                    _kanal_video(basis, dauer, k, auftrag, srt, datei, job, p, p + schritt)
                    fertig_fmt[schl] = datei
                    p += schritt
                t = texte.get(k["id"]) or {"titel": "", "text": "", "hashtags": ""}
                voll = "\n\n".join(x for x in (t["titel"], t["text"], t["hashtags"]) if x)
                (ordner / f"{k['id']}.txt").write_text(voll, encoding="utf-8")
                gekuerzt = bool(k.get("max_sek")) and dauer > int(k["max_sek"])
                job["ergebnisse"].append({"kanal": k["id"], "name": k["name"], "datei": str(datei), "url": k.get("url", ""),
                                          "weg": k.get("weg", "assistent"), "titel": t["titel"], "text": t["text"],
                                          "hashtags": t["hashtags"], "format": k.get("format"),
                                          "hinweis": (f"auf {k['max_sek']} s gekürzt (Grenze des Kanals)" if gekuerzt else ""),
                                          "mb": round(datei.stat().st_size / 1e6, 1)})
            shutil.rmtree(arbeits, ignore_errors=True)
            job["prozent"], job["schritt"], job["fertig"] = 100, "Fertig", True
        except Exception as e:
            job["fehler"] = str(e)[:800]
            job["fertig"] = True
            if "fehler_melden" in H and "abgebrochen" not in str(e):
                H["fehler_melden"]("Video-Studio", e)
        finally:
            job.pop("_proc", None)

    threading.Thread(target=arbeit, daemon=True).start()
    return {"id": jid}


def status(jid):
    j = JOBS.get(jid)
    if not j:
        return {"error": "Unbekannter Auftrag."}
    return {k: v for k, v in j.items() if not k.startswith("_")}


def untertitel_bestaetigen(jid, text=None):
    """Der Nutzer hat die Untertitel geprüft (und vielleicht verbessert) -> weiter."""
    j = JOBS.get(jid)
    if not j or not j.get("warte_auf_untertitel"):
        return {"error": "Es wartet gerade nichts auf die Untertitel."}
    if text is not None:
        t = str(text).replace("\r\n", "\n")
        if "-->" not in t:
            return {"error": "Die Zeitangaben (z. B. 00:00:01,000 --> 00:00:03,000) müssen erhalten bleiben."}
        j["srt_neu"] = t[:200000]
    j["warte_auf_untertitel"] = False
    j.pop("srt_text", None)
    return {"ok": True}


def abbrechen(jid):
    j = JOBS.get(jid)
    if j:
        j["abbrechen"] = True
        p = j.get("_proc")
        if p:
            try:
                p.kill()
            except Exception:
                pass
    return {"ok": True}
