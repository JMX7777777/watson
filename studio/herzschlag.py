"""Herzschlag: Watson schaut alle paar Minuten von selbst nach, ob alles in Ordnung ist und ob etwas zu tun ist.

Jeder Schlag ist kurz und kostet nichts (KEIN Gehirn, keine Gratis-Anfrage):
  - Termine in der nächsten halben Stunde (Kalender)
  - Sicherung fällig? -> sichert selbst (vorher lief sie nur beim Start)
  - Speicherplatz auf C:
  - Internet / OpenRouter erreichbar (Watsons Gehirne)
  - n8n (Abläufe) abgestürzt? -> startet es neu
  - hängende Hintergrund-Aufträge
  - neue Fehler seit dem letzten Schlag
  - Abendrunde lange nicht gelaufen
  - Tat-Prüfung: unbelegte Behauptungen
Wichtiges meldet Watson von selbst (Meldung + Nachricht im Gespräch „💓 Herzschlag“, am Handy, wenn der Nutzer dort ist).
Nachts (22–7 Uhr) bleibt alles still: Meldungen werden gesammelt und morgens beim ersten Schlag gezeigt.
Gleiche Meldung höchstens alle 6 Stunden. Alles steht im Puls-Tagebuch (herzschlag.json).
"""
import json
import shutil
import threading
import time
import urllib.request

import pfade

DATEI = pfade.DATEN / "herzschlag.json"
H = {}                     # Helfer aus watson_studio (init)
_lock = threading.Lock()
_laeuft = threading.Event()
WIEDERHOLEN_NACH = 6 * 3600


def init(**helfer):
    H.update(helfer)


def _laden():
    try:
        d = json.loads(DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("schlaege", [])          # Puls-Tagebuch (letzte 200)
    d.setdefault("gemeldet", {})          # schlüssel -> Zeit (gegen Wiederholung)
    d.setdefault("nachts_gesammelt", [])
    d.setdefault("anzahl", 0)
    d.setdefault("netz_fehler", 0)
    return d


def _speichern(d):
    d["schlaege"] = d["schlaege"][-200:]
    jetzt = time.time()
    d["gemeldet"] = {k: v for k, v in d["gemeldet"].items() if jetzt - v < 2 * 86400}
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def _cfg():
    try:
        return H["load_config"]()
    except Exception:
        return {}


def an(cfg=None):
    return (cfg or _cfg()).get("herzschlag", True)


def minuten(cfg=None):
    return max(5, min(120, int((cfg or _cfg()).get("herzschlag_minuten", 20) or 20)))


def nachtruhe(t=None):
    h = time.localtime(t).tm_hour
    return h >= 22 or h < 7


# ---------------- Die einzelnen Prüfungen ----------------
# Jede gibt eine Liste von Befunden zurück: {"art", "text", "stufe": ok|info|wichtig, "schluessel"}

def _b(art, text, stufe="info", schluessel=None):
    return {"art": art, "text": text, "stufe": stufe, "schluessel": schluessel or (art + ":" + text[:60])}


def pruef_termine(d):
    f = H.get("kalender")
    if not f:
        return []
    r = f() or {}
    out = []
    jetzt = time.time()
    for t in r.get("termine", []):
        start = _zeit_aus(t.get("start", ""), r.get("quelle", ""))
        if start and 0 <= start - jetzt <= 35 * 60:
            minuten_bis = max(1, round((start - jetzt) / 60))
            out.append(_b("termin", f"In {minuten_bis} Min.: {t.get('titel') or 'Termin'}"
                          + (f" ({t['ort']})" if t.get("ort") else ""), "wichtig",
                          "termin:" + str(t.get("titel")) + str(t.get("start"))))
    return out


def _zeit_aus(s, quelle=""):
    """Text -> Sekunden. Outlook liefert Ortszeit (mit falschem „+00:00“), der Windows-Kalender echte UTC-Zeit."""
    import datetime
    try:
        dt = datetime.datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None and quelle != "Outlook":
        return dt.timestamp()
    return time.mktime(dt.replace(tzinfo=None).timetuple())


def pruef_sicherung(d):
    s = H.get("sicherung")
    if not s or not s.faellig(24):
        return []
    try:
        s.sichern(n8n_export=H.get("n8n_export"))
        return [_b("sicherung", "Tägliche Sicherung gemacht (war fällig)", "ok")]
    except Exception as e:
        return [_b("sicherung", f"Sicherung hat nicht geklappt: {str(e)[:120]}", "wichtig", "sicherung:fehler")]


def pruef_speicher(d):
    frei = shutil.disk_usage("C:\\").free / 1e9
    if frei < 5:
        return [_b("speicher", f"Nur noch {frei:.1f} GB frei auf C: – bitte bald aufräumen", "wichtig", "speicher:knapp")]
    if frei < 15:
        return [_b("speicher", f"{frei:.0f} GB frei auf C:", "info", "speicher:wenig")]
    return []


def pruef_netz(d):
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/models?limit=1", headers={"User-Agent": "Watson"})
        with urllib.request.urlopen(req, timeout=12) as r:
            r.read(200)
        if d.get("netz_fehler", 0) >= 2:
            d["netz_fehler"] = 0
            return [_b("netz", "Internet und Gehirne sind wieder erreichbar", "info", "netz:wieder")]
        d["netz_fehler"] = 0
        return []
    except Exception as e:
        d["netz_fehler"] = d.get("netz_fehler", 0) + 1
        if d["netz_fehler"] >= 2:         # erst beim 2. Mal hintereinander melden (kurze Aussetzer sind normal)
            return [_b("netz", "Ich erreiche meine Gehirne (OpenRouter) nicht – Internet weg? Ich kann gerade "
                       "nicht richtig denken.", "wichtig", "netz:weg")]
        return [_b("netz", f"Gehirne kurz nicht erreichbar ({str(e)[:60]})", "info", "netz:kurz")]


def pruef_n8n(d):
    n = H.get("n8n_hub")
    if not n or not _cfg().get("use_n8n", True) or not n.installed() or n.running():
        return []
    try:
        n.start()
        ok = n.running()
    except Exception:
        ok = False
    if ok:
        return [_b("n8n", "Abläufe (n8n) waren aus – wieder gestartet", "ok")]
    return [_b("n8n", "Abläufe (n8n) laufen nicht und starten nicht neu", "wichtig", "n8n:aus")]


def pruef_auftraege(d):
    a = H.get("auftraege")
    if not a:
        return []
    out = []
    for x in a.alle(nur_offene=True):
        seit = x.get("gestartet") or 0
        if x["status"] == "läuft" and seit and time.time() - seit > 45 * 60:
            out.append(_b("auftrag", f"Hintergrund-Auftrag „{x['titel']}“ läuft schon "
                          f"{round((time.time() - seit) / 60)} Min. – hängt er?", "wichtig", f"auftrag:{x['id']}"))
    return out


def pruef_fehler(d):
    datei = pfade.DATEN / "fehler.jsonl"
    seit = d.get("letzter_schlag") or (time.time() - 3600)
    orte = []
    try:
        for z in datei.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]:
            try:
                e = json.loads(z)
            except ValueError:
                continue
            t = _zeit_aus(e.get("zeit", ""))
            if t and t > seit:
                orte.append(str(e.get("ort", "?")))
    except OSError:
        return []
    if not orte:
        return []
    haeufig = max(set(orte), key=orte.count)
    stufe = "wichtig" if len(orte) >= 3 else "info"
    return [_b("fehler", f"{len(orte)} neue(r) Fehler seit dem letzten Schlag (meist: {haeufig})", stufe,
               "fehler:" + haeufig)]


def pruef_abendrunde(d):
    w = H.get("wachstum")
    if not w:
        return []
    try:
        letzte = w._laden().get("letzte_runde")
    except Exception:
        return []
    if letzte and time.time() - letzte > 36 * 3600:
        return [_b("abendrunde", f"Meine Abendrunde (nachts lernen) ist {round((time.time() - letzte) / 3600)} Std. her",
                   "info", "abendrunde:alt")]
    return []


def pruef_tatpruefung(d):
    try:
        import tatpruefung
        seit = d.get("letzter_schlag") or (time.time() - 3600)
        n = 0
        for z in tatpruefung.DATEI.read_text(encoding="utf-8").splitlines()[-100:]:
            e = json.loads(z)
            t = time.mktime(time.strptime(e["zeit"], "%d.%m.%Y %H:%M:%S"))
            if t > seit and e.get("ergebnis") == "falsch_geblieben":
                n += 1
        if n:
            return [_b("ehrlichkeit", f"{n}× habe ich etwas behauptet, das nicht in meinem Protokoll steht", "info")]
    except Exception:
        pass
    return []


# ---------------- Windows-Updates: nur, wenn der Besitzer am Laptop ist (Wächter: werkzeuge\update_waechter.ps1) ----------------
import os
UPDATE_ORDNER = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Watson", "austausch")
UPDATE_STATUS = os.path.join(UPDATE_ORDNER, "updates_status.json")
UPDATE_WUNSCH = os.path.join(UPDATE_ORDNER, "updates_wunsch.txt")


def updates_info():
    """Was der Update-Wächter zuletzt aufgeschrieben hat (None = nicht eingerichtet)."""
    try:
        with open(UPDATE_STATUS, encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    offen = d.get("offen") or []
    if isinstance(offen, str):
        offen = [offen]
    try:
        alter = time.time() - time.mktime(time.strptime(str(d.get("stand", ""))[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        alter = 1e9
    return {"zustand": d.get("zustand", ""), "offen": offen, "neustart": bool(d.get("neustart_noetig")),
            "letzte_suche": str(d.get("letzte_suche", ""))[:16].replace("T", " "), "waechter_alt": alter > 30 * 60}


def updates_wunsch(wort):
    """Watson hinterlegt nur „jetzt“ oder „pause“ – der Wächter liest nur genau diese Wörter."""
    if wort not in ("jetzt", "pause"):
        raise ValueError("unbekannter Wunsch")
    with open(UPDATE_WUNSCH, "w", encoding="utf-8") as f:
        f.write(wort)


def pruef_updates(d):
    u = updates_info()
    if u is None:
        return []                                   # nicht eingerichtet
    if u["waechter_alt"]:
        return [_b("updates", "Der Update-Wächter hat sich seit über 30 Minuten nicht gemeldet", "info", "updates:waechter")]
    if nachtruhe() or _handy_still():
        return []                                   # nie nachts, nie wenn der Besitzer am Handy ist – nur am Laptop erinnern
    out = []
    if u["neustart"]:
        out.append(_b("updates", "Windows möchte für Updates neu starten – mach es, wenn es dir gerade passt",
                      "wichtig", "updates:neustart"))
    elif u["offen"] and u["zustand"] == "pausiert":
        out.append(_b("updates", f"{len(u['offen'])} Windows-Update(s) warten. Wenn du gerade Zeit hast: im Herz-Fenster "
                      "„Updates jetzt machen“ drücken", "wichtig", f"updates:offen:{len(u['offen'])}"))
    elif u["zustand"] == "freigegeben":
        out.append(_b("updates", "Windows-Updates sind gerade freigegeben und laufen", "info", "updates:laufen"))
    return out


def pruef_werkzeug_wuensche(d):
    """Neue Werkzeug-Wünsche von Watson vorlegen (nachts gesammelt, morgens gemeldet – über die normale Melde-Regel)."""
    try:
        import werkzeug_wahl
        offen = werkzeug_wahl.offene()
    except Exception:
        return []
    return [_b("werkzeug", f"🔌 Ich wünsche mir ein neues Werkzeug: „{w['titel']}“ – {w['warum'][:200]} "
               "Sag Ja oder Nein unter „Skills“ (Laptop oder Handy).", "wichtig", f"werkzeug:{w['id']}") for w in offen[:3]]


def pruef_ideen(d):
    """Gute neue Ideen aus der Erfinder-Zeit einmal vorlegen (nachts gesammelt, morgens gemeldet)."""
    try:
        import erfinder
        neu = erfinder.neue_ungezeigt()
    except Exception:
        return []
    if not neu:
        return []
    namen = ", ".join(f"„{i['titel']}“" for i in neu[:3])
    return [_b("ideen", f"💡 Erfinder-Zeit: Ich habe mir {'eine neue Idee' if len(neu) == 1 else f'{len(neu)} neue Ideen'} "
               f"ausgedacht: {namen}. Schau sie dir unter „Wachstum“ → Ideenbuch an (Laptop oder Handy) und sag mir, "
               "wie du sie findest.", "wichtig", f"ideen:{max(i['id'] for i in neu)}")]


def pruef_wartung(d):
    """Reparatur-Vorschläge, denen der Code-Rat zugestimmt hat, dem Besitzer vorlegen (Ja/Nein)."""
    try:
        import wartung
        offen = [v for v in wartung._laden()["vorschlaege"] if v["status"] == "vorgeschlagen"
                 and wartung.zustimmung(v)[0] >= 2]
    except Exception:
        return []
    return [_b("wartung", f"🔧 Mein Wartungs-Team hat in „{v['datei']}“ etwas gefunden: {v.get('erklaerung', '')[:160]} "
               "Der Code-Rat stimmt zu. Sag Ja oder Nein unter „Wachstum“ (Laptop oder Handy).", "wichtig",
               f"wartung:{v['id']}") for v in offen[:2]]


PRUEFUNGEN = [("Termine", pruef_termine), ("Sicherung", pruef_sicherung), ("Speicher", pruef_speicher),
              ("Gehirne", pruef_netz), ("Abläufe", pruef_n8n), ("Aufträge", pruef_auftraege),
              ("Fehler", pruef_fehler), ("Abendrunde", pruef_abendrunde), ("Ehrlichkeit", pruef_tatpruefung),
              ("Updates", pruef_updates), ("Werkzeug-Wünsche", pruef_werkzeug_wuensche),
              ("Wartung", pruef_wartung), ("Ideen", pruef_ideen)]


# ---------------- Ein Schlag ----------------
def schlag(grund="Takt"):
    """Ein Herzschlag: alle Prüfungen, Tagebuch-Eintrag, Wichtiges melden. Gibt den Eintrag zurück."""
    if _laeuft.is_set():
        return {"fehler": "Ein Herzschlag läuft gerade."}
    _laeuft.set()
    t0 = time.time()
    try:
        with _lock:
            d = _laden()
        befunde = []
        for name, f in PRUEFUNGEN:
            try:
                befunde += f(d)
            except Exception as e:
                befunde.append(_b("pruefung", f"{name}: Prüfung ging nicht ({str(e)[:80]})", "info", "pruefung:" + name))
                if "fehler_melden" in H:
                    H["fehler_melden"]("Herzschlag/" + name, e)
        jetzt = time.time()
        neu_wichtig = [b for b in befunde if b["stufe"] == "wichtig"
                       and jetzt - d["gemeldet"].get(b["schluessel"], 0) > WIEDERHOLEN_NACH]
        for b in neu_wichtig:
            d["gemeldet"][b["schluessel"]] = jetzt
        still = nachtruhe() or _handy_still()
        zu_melden = []
        if nachtruhe():
            d["nachts_gesammelt"] = (d["nachts_gesammelt"] + [b["text"] for b in neu_wichtig])[-20:]
        else:
            zu_melden = d["nachts_gesammelt"] + [b["text"] for b in neu_wichtig]
            d["nachts_gesammelt"] = []
        zustand = "wichtig" if any(b["stufe"] == "wichtig" for b in befunde) else \
            "info" if any(b["stufe"] == "info" for b in befunde) else "ok"
        eintrag = {"zeit": time.strftime("%d.%m.%Y %H:%M"), "t": jetzt, "grund": grund, "zustand": zustand,
                   "befunde": [{k: b[k] for k in ("art", "text", "stufe")} for b in befunde],
                   "gemeldet": len(zu_melden), "still": still, "dauer": round(time.time() - t0, 1)}
        d["schlaege"].append(eintrag)
        d["anzahl"] += 1
        d["letzter_schlag"] = jetzt
        with _lock:
            alt = _laden()
            d["chat_id"] = d.get("chat_id") or alt.get("chat_id")
            _speichern(d)
        if zu_melden and "melden" in H:
            try:
                H["melden"](zu_melden, d)
            except Exception as e:
                if "fehler_melden" in H:
                    H["fehler_melden"]("Herzschlag/Melden", e)
        if "puls" in H:
            try:
                H["puls"](status())
            except Exception:
                pass
        return eintrag
    finally:
        _laeuft.clear()


def _handy_still():
    try:
        return bool(H["handy_still"]())
    except Exception:
        return False


def chat_merken(chat_id):
    with _lock:
        d = _laden()
        d["chat_id"] = chat_id
        _speichern(d)


def status():
    d = _laden()
    letzter = d["schlaege"][-1] if d["schlaege"] else None
    cfg = _cfg()
    return {"an": an(cfg), "minuten": minuten(cfg), "anzahl": d["anzahl"], "letzter": letzter,
            "naechster_in": max(0, round(((d.get("letzter_schlag") or time.time()) + minuten(cfg) * 60 - time.time()) / 60))
            if an(cfg) else None,
            "tagebuch": list(reversed(d["schlaege"][-30:])), "nachts_gesammelt": d["nachts_gesammelt"],
            "updates": updates_info()}


def schleife():
    """Läuft im Hintergrund, solange Watson an ist."""
    time.sleep(120)                       # nach dem Start erst Ruhe
    try:
        import pythoncom                  # Kalender (Outlook/COM) braucht das in eigenen Threads
        pythoncom.CoInitialize()
    except Exception:
        pass
    while True:
        try:
            cfg = _cfg()
            d = _laden()
            if an(cfg) and time.time() - (d.get("letzter_schlag") or 0) >= minuten(cfg) * 60 - 30:
                schlag()
        except Exception as e:
            if "fehler_melden" in H:
                H["fehler_melden"]("Herzschlag", e)
        time.sleep(60)
