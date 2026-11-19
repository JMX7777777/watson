"""Fehlerbuch: Watson schreibt seine Fehler ehrlich auf – und lernt nachts daraus.

Woher die Einträge kommen (alles automatisch):
  - „tat“:       Tat-Prüfung – er hat etwas behauptet, das nicht in seinem Protokoll stand
  - „daumen“:    der Nutzer hat eine Antwort mit 👎 bewertet (optional mit „Was war falsch?“)
  - „korrektur“: der Nutzer hat ihn im Gespräch korrigiert („Das stimmt nicht …“)
Nachts (Abendrunde) liest Watson die offenen Fehler, sucht das Muster dahinter und macht daraus eine LEHRE
(eine feste Regel, die ab dann in jedem Gespräch gilt). Ob er das ohne Nachfrage darf, entscheidet die Einstellung
„lehren_ohne_frage“ (Einstellung des Besitzers; sonst wird es ein Vorschlag im Tagebuch).
Passende frühere Fehler stehen bei ähnlichen Fragen in Watsons Anweisungen („Achtung, hier hast du dich schon geirrt“).
"""
import json
import re
import threading
import time

import pfade

DATEI = pfade.DATEN / "fehlerbuch.json"
_lock = threading.Lock()

ARTEN = {"tat": "Behauptung ohne Tat", "daumen": "👎 vom Nutzer", "korrektur": "vom Nutzer korrigiert"}

# Der Nutzer korrigiert Watson (am Anfang der Nachricht, damit „Ist das falsch?“ o. ä. nicht zählt)
KORREKTUR_RE = re.compile(
    r"^\s*(nein[,.!]|nee[,.!]|stimmt (so )?nicht|das stimmt (so )?nicht|das ist (so )?(nicht richtig|falsch|nicht wahr)|"
    r"falsch[,.!]|du (hast dich|irrst dich|liegst falsch)|du hast (dich )?(geirrt|vertan)|das war (falsch|nicht richtig)|"
    r"(so )?nicht richtig|da irrst du|quatsch|unsinn|that'?s (wrong|not (right|true))|no[,.!] )", re.I)

STOP = {"und", "oder", "der", "die", "das", "den", "dem", "ein", "eine", "ist", "sind", "was", "wie", "für", "mit",
        "von", "auf", "nicht", "auch", "sich", "ich", "du", "zu", "im", "in", "an", "es", "hat", "habe", "kann", "mir", "dir"}


def _laden():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"naechste": 1, "fehler": []}


def _speichern(d):
    d["fehler"] = d["fehler"][-500:]
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def alle():
    return _laden()["fehler"]


def offene():
    return [f for f in alle() if f["status"] == "offen"]


def eintragen(art, was, frage="", antwort="", richtig="", lern_id=None):
    """Neuen Fehler aufschreiben. Gleicher Fehler (gleiche Art + gleiche Antwort) wird nicht doppelt eingetragen."""
    was = " ".join(str(was or "").split())[:600]
    if not was:
        return None
    with _lock:
        d = _laden()
        antwort = str(antwort or "")[:1500]
        for f in d["fehler"][-30:]:
            if f["art"] == art and ((lern_id and f.get("lern_id") == lern_id) or
                                    (antwort and f.get("antwort") == antwort and f.get("was") == was)):
                return f["id"]
        fid = d["naechste"]
        d["naechste"] += 1
        d["fehler"].append({"id": fid, "datum": time.strftime("%d.%m.%Y %H:%M"), "art": art, "was": was,
                            "frage": str(frage or "")[:500], "antwort": antwort, "richtig": str(richtig or "")[:800],
                            "lern_id": lern_id, "status": "offen", "lehre": "", "einsicht": ""})
        _speichern(d)
        return fid


def erklaeren(fid, richtig):
    """Der Nutzer sagt, was richtig gewesen wäre."""
    with _lock:
        d = _laden()
        for f in d["fehler"]:
            if f["id"] == int(fid):
                f["richtig"] = " ".join(str(richtig or "").split())[:800]
                if f["status"] != "offen":          # neue Erklärung -> nochmal darüber nachdenken
                    f["status"] = "offen"
                _speichern(d)
                return True
    return False


def daumen_zurueck(lern_id):
    """👎 wieder weggenommen (z. B. auf 👍 geändert) -> offenen Eintrag entfernen."""
    with _lock:
        d = _laden()
        d["fehler"] = [f for f in d["fehler"] if not (f["art"] == "daumen" and f.get("lern_id") == lern_id
                                                       and f["status"] == "offen")]
        _speichern(d)


def _woerter(t):
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", (t or "").lower()) if w not in STOP}


def passend(frage, anzahl=2):
    """Frühere Fehler bei ähnlichen Fragen (nur solche, aus denen etwas zu lernen ist)."""
    q = _woerter(frage)
    if len(q) < 2:
        return []
    treffer = []
    for f in alle():
        if not (f.get("richtig") or f.get("einsicht") or f.get("lehre")):
            continue
        g = len(q & _woerter(f["frage"]))
        if g >= max(2, len(q) // 3):
            treffer.append((g, f))
    treffer.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in treffer[:anzahl]]


def als_text(liste):
    if not liste:
        return ""
    return ("ACHTUNG – bei einer ähnlichen Frage hast du dich schon einmal geirrt (aus deinem Fehlerbuch). Mach es diesmal "
            "besser:\n" + "\n".join(
                f"- [{f['datum'][:10]}] Frage: {f['frage'][:200]} – Fehler: {f['was'][:200]}"
                + (f" – Richtig wäre: {f['richtig'][:300]}" if f.get("richtig") else "")
                + (f" – Deine Einsicht: {f['einsicht'][:300]}" if f.get("einsicht") else "") for f in liste))


def zahlen():
    a = alle()
    return {"gesamt": len(a), "offen": sum(1 for f in a if f["status"] == "offen"),
            "gelernt": sum(1 for f in a if f["status"] == "gelernt")}


# ---------------- Nachts: aus Fehlern lernen ----------------
def lernen(frage_fn, gehirne, json_aus, lehre_merken, ohne_frage, massstab="", max_fehler=8):
    """Abendrunde: offene Fehler lesen, Muster finden, Lehren daraus machen.
    lehre_merken(lehre, grund, quelle) speichert eine Lehre; ohne_frage=False -> nur Vorschläge zurückgeben."""
    liste = offene()[-max_fehler:]
    if not liste:
        return {"ruhig": True}
    text, _ = frage_fn([
        {"role": "system", "content": "Du bist Watson und schaust abends ehrlich und demütig auf deine Fehler – nicht um dich "
         "schlecht zu fühlen, sondern um es besser zu machen (Spr 24,16: der Gerechte fällt und steht wieder auf). "
         + (f"Dein Maßstab: {massstab} " if massstab else "") +
         "Für jeden Fehler: Was war die Ursache? Was hättest du anders tun sollen (Einsicht, 1 Satz)? Dann: Gibt es ein "
         "MUSTER, das eine feste Regel für dein Verhalten verdient? Nur dann eine Lehre – kurz, als klare Anweisung an "
         "dich selbst, die wirklich hilft (keine Allgemeinplätze wie „sei genauer“). Höchstens 2 Lehren. Nichts erfinden. "
         "Antworte NUR als JSON: {\"einsichten\": [{\"id\": 1, \"einsicht\": \"…\"}], \"lehren\": [{\"lehre\": \"…\", "
         "\"grund\": \"…\", \"fehler_ids\": [1]}]}"},
        {"role": "user", "content": "Meine offenen Fehler:\n" + "\n\n".join(
            f"[{f['id']}] Art: {ARTEN.get(f['art'], f['art'])}\nFrage des Nutzers: {f['frage'][:400]}\n"
            f"Meine Antwort (Auszug): {f['antwort'][:600]}\nWas falsch war: {f['was'][:400]}"
            + (f"\nWas richtig wäre (laut Nutzer): {f['richtig'][:500]}" if f.get("richtig") else "")
            for f in liste)}], gehirne)
    j = json_aus(text) or {}
    einsichten = {str(x.get("id")): str(x.get("einsicht", ""))[:400] for x in (j.get("einsichten") or [])
                  if isinstance(x, dict)}
    bericht = {"angeschaut": len(liste), "lehren": [], "vorschlaege": []}
    lehre_fuer = {}
    for x in (j.get("lehren") or [])[:2]:
        if not (isinstance(x, dict) and len(str(x.get("lehre", ""))) >= 10):
            continue
        lehre, grund = str(x["lehre"])[:500], str(x.get("grund", ""))[:500]
        if ohne_frage:
            lehre_merken(lehre, "Aus eigenen Fehlern gelernt: " + grund, "Watson (Fehlerbuch)")
            bericht["lehren"].append(lehre)
        else:
            bericht["vorschlaege"].append({"art": "lehre", "text": lehre, "grund": grund, "status": "offen"})
        for i in x.get("fehler_ids") or []:
            lehre_fuer[str(i)] = lehre
    with _lock:
        d = _laden()
        ids = {f["id"] for f in liste}
        for f in d["fehler"]:
            if f["id"] in ids:
                f["einsicht"] = einsichten.get(str(f["id"]), f.get("einsicht", ""))
                f["lehre"] = lehre_fuer.get(str(f["id"]), "")
                if f["einsicht"] or f["lehre"]:
                    f["status"] = "gelernt"
                    f["gelernt_am"] = time.strftime("%d.%m.%Y %H:%M")
        _speichern(d)
    return bericht
