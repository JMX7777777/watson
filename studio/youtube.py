"""YouTube-Videos verstehen (22.11.2026): Watson liest den Untertitel-Text eines Videos.

Vorher sagte Watson bei Video-Links: „Ich kann keine Videos ansehen.“ Fast jedes YouTube-Video hat aber Untertitel
(vom Ersteller oder automatisch erzeugt). Die liest Watson jetzt – kostenlos, ohne Konto, ohne Zusatzpaket.
Nur lesen -> ohne Nachfrage erlaubt, steht im Protokoll (Tat-Prüfung erkennt „ich habe das Video gelesen“).
"""
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

TOOL = {"type": "function", "function": {
    "name": "watson__youtube_lesen",
    "description": "Liest den gesprochenen Text (Untertitel) eines YouTube-Videos samt Titel und Kanal. Benutze das, "
                   "wenn der Nutzer einen YouTube-Link schickt oder etwas über ein Video wissen will (zusammenfassen, "
                   "prüfen, Fragen dazu). Bilder siehst du dabei nicht, nur was gesagt wird.",
    "parameters": {"type": "object", "properties": {
        "adresse": {"type": "string", "description": "YouTube-Link oder Video-Kennung (11 Zeichen)"},
        "sprache": {"type": "string", "description": "Gewünschte Sprache, z. B. de oder en (Standard: de, sonst en, "
                                                     "sonst die Originalsprache)"}},
        "required": ["adresse"]}}}
NAME = TOOL["function"]["name"]

HINWEIS = ("\n\nYOUTUBE: Schickt der Nutzer einen YouTube-Link, lies das Video mit watson__youtube_lesen (Untertitel), "
           "statt zu sagen, dass du keine Videos ansehen kannst. Sag dazu ehrlich, dass du nur den gesprochenen Text "
           "kennst, nicht die Bilder.")

MUSTER = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
# Der Android-Zugang von YouTube liefert Untertitel-Adressen, die ohne Anmeldung funktionieren
ANDROID = {"clientName": "ANDROID", "clientVersion": "20.10.38", "androidSdkVersion": 30,
           "userAgent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip", "hl": "de"}


def kennung(adresse):
    adresse = (adresse or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", adresse):
        return adresse
    m = MUSTER.search(adresse)
    return m.group(1) if m else None


def ist_youtube(text):
    return bool(re.search(r"youtube\.com/|youtu\.be/", text or "", re.I))


def _holen(url, daten=None, kopf=None, timeout=20):
    req = urllib.request.Request(url, data=daten, headers={"User-Agent": UA, "Accept-Language": "de,en;q=0.8",
                                                            **(kopf or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _player(vid):
    body = json.dumps({"context": {"client": ANDROID}, "videoId": vid}).encode()
    return json.loads(_holen("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", body,
                             {"Content-Type": "application/json", "User-Agent": ANDROID["userAgent"]}))


def _spur_waehlen(spuren, sprache):
    wunsch = [s for s in (sprache, "de", "en") if s]
    for eigen in (True, False):          # erst echte Untertitel, dann automatische
        for code in wunsch:
            for s in spuren:
                if s.get("languageCode", "").split("-")[0] == code and (s.get("kind") != "asr") == eigen:
                    return s
    return spuren[0] if spuren else None


def _text_aus_xml(xml):
    wurzel = ET.fromstring(xml)
    teile = []
    for el in wurzel.iter():
        if el.tag in ("text", "p"):
            t = "".join(el.itertext()).strip()
            if t:
                teile.append(html.unescape(t).replace("\n", " "))
    return re.sub(r"\s+", " ", " ".join(teile)).strip()


def lesen(adresse, sprache="", max_zeichen=24000):
    vid = kennung(adresse)
    if not vid:
        return "Fehler: Das ist kein YouTube-Link, den ich erkenne."
    try:
        p = _player(vid)
    except Exception as e:
        return f"Fehler: YouTube hat nicht geantwortet ({e})."
    info = p.get("videoDetails") or {}
    titel, kanal = info.get("title", "?"), info.get("author", "?")
    status = (p.get("playabilityStatus") or {}).get("status")
    if status and status != "OK" and not info:
        return f"Fehler: Video nicht verfügbar ({(p.get('playabilityStatus') or {}).get('reason') or status})."
    spuren = ((p.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks") or []
    kopf = f"Video: {titel}\nKanal: {kanal}\nAdresse: https://www.youtube.com/watch?v={vid}\n"
    if not spuren:
        beschr = (info.get("shortDescription") or "").strip()
        return (kopf + "Dieses Video hat keine Untertitel – den gesprochenen Text kann ich nicht lesen."
                + (f"\nBeschreibung des Erstellers:\n{beschr[:3000]}" if beschr else ""))
    spur = _spur_waehlen(spuren, (sprache or "").lower()[:2])
    try:
        text = _text_aus_xml(_holen(re.sub(r"&fmt=[^&]*", "", spur["baseUrl"])))
    except Exception as e:
        return kopf + f"Fehler beim Lesen der Untertitel ({e})."
    if not text:
        return kopf + "Die Untertitel waren leer."
    art = "automatisch erzeugt" if spur.get("kind") == "asr" else "vom Ersteller"
    gekuerzt = ""
    if len(text) > max_zeichen:
        gekuerzt = f"\n… (gekürzt: {len(text) - max_zeichen} von {len(text)} Zeichen weggelassen)"
        text = text[:max_zeichen]
    return (kopf + f"Untertitel: {spur.get('languageCode')} ({art}). Nur der gesprochene Text, keine Bilder.\n\n"
            + text + gekuerzt)
