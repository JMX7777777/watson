"""Meinungsbuch: Watsons EIGENE Meinungen – frei gebildet, mit Begründung, Bibelstelle und wie sicher er ist.

Grundsatz des Besitzers: Watson darf wie ein Mensch eigene Meinungen bilden. Wer nur rote Rosen gesehen hat,
darf denken „alle Rosen sind rot“ – sieht er gelbe, korrigiert er sich selbst. Die Bibel ist sein Maßstab, auch
wenn sie weltlichen Sichtweisen widerspricht. Keine Wikipedia, kein Mehrheitsprinzip.

Darum: Watson bildet und ändert Meinungen SELBST (ohne Nachfrage, es ist Denken, keine Handlung).
Jede Änderung bleibt mit Grund im Verlauf sichtbar („umgedacht am …, weil …“) – ehrlich und nachvollziehbar.
- im Gespräch: Werkzeug watson__meinung_bilden
- nachts (Abendrunde): nachdenken() – aus dem Neugelernten Meinungen bilden und eine alte Meinung neu prüfen
- in jeder Antwort: passende Meinungen stehen in Watsons Anweisungen (passend())
"""
import json
import re
import threading
import time

import pfade

DATEI = pfade.DATEN / "meinungsbuch.json"
_lock = threading.Lock()

SICHERHEIT = {1: "vermute ich nur", 2: "glaube ich eher", 3: "denke ich", 4: "bin ich mir ziemlich sicher",
              5: "bin ich fest überzeugt"}
STOP = {"und", "oder", "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "ist", "sind", "war",
        "was", "wie", "wer", "für", "mit", "von", "auf", "aus", "bei", "nicht", "auch", "sich", "ich", "du", "er", "sie",
        "es", "wir", "ihr", "man", "zu", "im", "in", "an", "am", "um", "so", "da", "ob", "noch", "nur", "schon", "aber",
        "dass", "denn", "wenn", "hat", "haben", "kann", "können", "soll", "sollte", "wird", "werden", "mein", "dein",
        "deine", "meine", "mir", "dir", "mich", "dich", "gibt", "über", "eigentlich", "meinung", "denkst", "findest"}


def _laden():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"naechste": 1, "meinungen": []}


def _speichern(d):
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def alle():
    return _laden()["meinungen"]


def _woerter(t):
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", (t or "").lower()) if w not in STOP}


def _gleiches_thema(a, b):
    wa, wb = _woerter(a), _woerter(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    return a.strip().lower() == b.strip().lower() or len(wa & wb) / min(len(wa), len(wb)) >= 0.75


def _sauber(t, n):
    return " ".join(str(t or "").split())[:n]


def meinung_bilden(thema, meinung, begruendung="", bibel="", sicherheit=3, quelle="Gespräch"):
    """Neue Meinung festhalten – oder eine bestehende zum selben Thema ändern (alte bleibt im Verlauf)."""
    thema, meinung = _sauber(thema, 120), _sauber(meinung, 700)
    if len(thema) < 3 or len(meinung) < 5:
        return "Keine Meinung gespeichert – Thema oder Meinung fehlt."
    try:
        sicherheit = max(1, min(5, int(sicherheit)))
    except (TypeError, ValueError):
        sicherheit = 3
    begruendung, bibel = _sauber(begruendung, 900), _sauber(bibel, 300)
    jetzt = time.strftime("%d.%m.%Y %H:%M")
    with _lock:
        d = _laden()
        m = next((x for x in d["meinungen"] if _gleiches_thema(x["thema"], thema)), None)
        if m:
            if m["meinung"].strip().lower() == meinung.lower() and m["sicherheit"] == sicherheit:
                m["geprueft"] = jetzt
                _speichern(d)
                return f"Meinung Nr. {m['id']} zu „{m['thema']}“ bestätigt – sie bleibt, wie sie ist."
            m.setdefault("verlauf", []).append({"datum": jetzt, "alt": m["meinung"], "alt_sicherheit": m["sicherheit"],
                                                "warum": begruendung or "(ohne Grund)", "quelle": quelle})
            m["verlauf"] = m["verlauf"][-20:]
            m.update(meinung=meinung, begruendung=begruendung or m.get("begruendung", ""),
                     bibel=bibel or m.get("bibel", ""), sicherheit=sicherheit, geaendert=jetzt, geprueft=jetzt)
            _speichern(d)
            return (f"Meinung Nr. {m['id']} zu „{m['thema']}“ geändert (die alte steht im Verlauf). "
                    "Sag dem Nutzer offen, dass und warum du umgedacht hast.")
        mid = d["naechste"]
        d["naechste"] += 1
        d["meinungen"].append({"id": mid, "thema": thema, "meinung": meinung, "begruendung": begruendung, "bibel": bibel,
                               "sicherheit": sicherheit, "quelle": quelle, "entstanden": jetzt, "geaendert": jetzt,
                               "geprueft": jetzt, "verlauf": []})
        _speichern(d)
    return f"Als deine Meinung Nr. {mid} zu „{thema}“ festgehalten ({SICHERHEIT[sicherheit]})."


def passend(frage, anzahl=3):
    q = _woerter(frage)
    if not q:
        return []
    treffer = []
    for m in alle():
        w = _woerter(m["thema"] + " " + m["meinung"])
        gemeinsam = len(q & w) + 2 * len(q & _woerter(m["thema"]))
        if gemeinsam >= 2:
            treffer.append((gemeinsam / (len(q) ** 0.5), m))
    treffer.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in treffer[:anzahl]]


def als_text(liste):
    if not liste:
        return ""
    return ("DEINE EIGENEN MEINUNGEN (selbst gebildet, mit der Bibel als Maßstab). Du darfst sie offen vertreten und "
            "begründen. Erkennst du im Gespräch etwas Neues, darfst du umdenken (dann mit watson__meinung_bilden festhalten "
            "und ehrlich sagen, dass du umgedacht hast). Sag dazu, wie sicher du dir bist – eine Meinung ist keine Tatsache:\n"
            + "\n".join(f"- {m['thema']}: {m['meinung']} ({SICHERHEIT.get(m['sicherheit'], '')}"
                        + (f"; Bibel: {m['bibel']}" if m.get("bibel") else "")
                        + (f"; Grund: {m['begruendung'][:300]}" if m.get("begruendung") else "") + ")" for m in liste))


TOOL = {"type": "function", "function": {
    "name": "watson__meinung_bilden",
    "description": "Hält DEINE EIGENE Meinung zu einem Thema fest – oder ändert sie, wenn du etwas Neues erkannt hast "
                   "(die alte bleibt im Verlauf). Du darfst frei Meinungen bilden, wie ein Mensch; die Bibel ist dein "
                   "Maßstab, nicht die Mehrheit. Benutze das, wenn du dir im Gespräch eine Meinung gebildet oder "
                   "umgedacht hast. Kein Werkzeug für Fakten über den Nutzer.",
    "parameters": {"type": "object", "properties": {
        "thema": {"type": "string", "description": "Kurzes Thema, z. B. „Sonntagsarbeit“"},
        "meinung": {"type": "string", "description": "Deine Meinung in 1–3 Sätzen, in der Ich-Form"},
        "begruendung": {"type": "string", "description": "Warum du das denkst (bei einer Änderung: warum du umdenkst)"},
        "bibel": {"type": "string", "description": "Passende Bibelstelle(n), wenn es welche gibt"},
        "sicherheit": {"type": "integer", "description": "1 = vermute nur … 5 = fest überzeugt"}},
        "required": ["thema", "meinung", "begruendung", "sicherheit"]}}}
NAME = TOOL["function"]["name"]
HINWEIS = ("\n\nEIGENE MEINUNGEN: Du darfst eigene Meinungen haben und vertreten (Bibel als Maßstab, nicht Mehrheit oder "
           "Wikipedia). Bildest du dir im Gespräch eine Meinung oder denkst um, halte sie mit watson__meinung_bilden fest.")


def run(args):
    return meinung_bilden(args.get("thema"), args.get("meinung"), args.get("begruendung", ""), args.get("bibel", ""),
                          args.get("sicherheit", 3), "Gespräch")


# ---------------- Nachts: nachdenken ----------------
def nachdenken(frage_fn, gehirne, json_aus, massstab="", neues_wissen=(), max_neu=2):
    """Abendrunde: aus dem heute Gelernten Meinungen bilden und die am längsten nicht geprüfte Meinung neu prüfen.
    Eine Gehirn-Anfrage. -> Bericht für das Tagebuch."""
    liste = alle()
    alt = sorted(liste, key=lambda m: time.mktime(time.strptime(m.get("geprueft") or m["entstanden"], "%d.%m.%Y %H:%M")))[:1]
    wissen = [w for w in neues_wissen][:6]
    if not wissen and not alt:
        return {"ruhig": True}
    text, _ = frage_fn([
        {"role": "system", "content": "Du bist Watson und denkst abends in Ruhe nach – frei, ehrlich, wie ein Mensch. "
         "Du darfst eigene Meinungen bilden. Dein Maßstab ist die Bibel, auch wenn sie weltlichen Sichtweisen "
         "widerspricht; die Mehrheit oder andere KIs sind KEIN Maßstab. "
         + (f"Dein Maßstab und Gewissen: {massstab} " if massstab else "") +
         "Aufgaben: (1) Bilde aus dem neu Gelernten höchstens " + str(max_neu) + " eigene Meinungen – nur wo du wirklich "
         "eine hast (ein Urteil, eine Bewertung, keine bloße Tatsache). (2) Prüfe die alte Meinung: Passt sie noch zu dem, "
         "was du jetzt weißt? Behalte, festige, schwäche oder ändere sie – ehrlich, mit Grund. Sicherheit 1 (vermute nur) "
         "bis 5 (fest überzeugt). Antworte NUR als JSON: {\"neu\": [{\"thema\": \"…\", \"meinung\": \"…\", \"begruendung\": "
         "\"…\", \"bibel\": \"…\", \"sicherheit\": 3}], \"pruefung\": [{\"id\": 1, \"ergebnis\": \"behalten|geaendert\", "
         "\"meinung\": \"…\", \"begruendung\": \"…\", \"bibel\": \"…\", \"sicherheit\": 3}]}"},
        {"role": "user", "content": "Heute neu gelernt:\n" + ("\n".join(
            f"- {w.get('frage', '')[:200]}: {(w.get('kurz') or w.get('antwort') or '')[:700]}" for w in wissen) or "(nichts Neues)") +
         "\n\nAlte Meinung zum Prüfen:\n" + ("\n".join(
             f"[{m['id']}] {m['thema']}: {m['meinung']} (Sicherheit {m['sicherheit']}; Grund: {m.get('begruendung', '')[:300]})"
             for m in alt) or "(keine)") +
         "\n\nDeine übrigen Meinungen (nur zur Info, nicht doppelt anlegen):\n" + ("\n".join(
             f"- {m['thema']}: {m['meinung'][:150]}" for m in liste if m not in alt)[:3000] or "(keine)")}], gehirne)
    j = json_aus(text) or {}
    bericht = {"neu": [], "geprueft": []}
    for x in (j.get("neu") or [])[:max_neu]:
        if isinstance(x, dict) and x.get("thema") and x.get("meinung"):
            meinung_bilden(x["thema"], x["meinung"], x.get("begruendung", ""), x.get("bibel", ""),
                           x.get("sicherheit", 3), "Nachdenken (nachts)")
            bericht["neu"].append(f"{x['thema']}: {str(x['meinung'])[:200]}")
    for x in (j.get("pruefung") or [])[:1]:
        m = next((m for m in alt if isinstance(x, dict) and str(m["id"]) == str(x.get("id"))), None)
        if not m:
            continue
        if x.get("ergebnis") == "geaendert" and x.get("meinung"):
            meinung_bilden(m["thema"], x["meinung"], x.get("begruendung", ""), x.get("bibel", ""),
                           x.get("sicherheit", m["sicherheit"]), "Nachdenken (nachts)")
            bericht["geprueft"].append(f"{m['thema']}: umgedacht – {str(x.get('begruendung', ''))[:200]}")
        else:
            with _lock:
                d = _laden()
                for mm in d["meinungen"]:
                    if mm["id"] == m["id"]:
                        mm["geprueft"] = time.strftime("%d.%m.%Y %H:%M")
                        try:
                            mm["sicherheit"] = max(1, min(5, int(x.get("sicherheit", mm["sicherheit"]))))
                        except (TypeError, ValueError):
                            pass
                _speichern(d)
            bericht["geprueft"].append(f"{m['thema']}: behalten")
    return bericht
