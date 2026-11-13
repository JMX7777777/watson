"""
Watsons Lernbuch und Wissensbuch – so lernt Watson aus Erfahrung (ohne dass die KI-Modelle neu trainiert werden).

Lernbuch:   Für jede Antwort: Art der Aufgabe, welches Gehirn, wie lange, ob es geklappt hat und wie der Nutzer
            sie bewertet hat (👍/👎). Daraus weiß der Dirigent mit der Zeit, welches Gehirn wofür am besten ist.
Wissensbuch: Wissen, das Watson beigebracht wurde (z. B. über die Lehrer-Brücke von ChatGPT, Claude, Gemini),
            immer mit Quelle und Datum. Passendes Wissen bekommt das Gehirn bei neuen Fragen mit.
"""
import json
import re
import threading
import time

import pfade

LERN = pfade.DATEN / "lernbuch.json"
WISSEN = pfade.DATEN / "wissensbuch.json"
_lock = threading.Lock()


def _laden(datei, leer):
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except Exception:
        return leer


def _speichern(datei, daten):
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(datei)


# ---------------- Lernbuch ----------------
def eintragen(frage, kategorie, modell, dauer, ok=True):
    with _lock:
        d = _laden(LERN, {"naechste": 1, "eintraege": []})
        eid = d["naechste"]; d["naechste"] += 1
        d["eintraege"].append({"id": eid, "zeit": time.strftime("%d.%m.%Y %H:%M"), "frage": (frage or "")[:200],
                               "kategorie": kategorie, "modell": modell, "dauer": round(dauer, 1), "ok": bool(ok),
                               "bewertung": 0})
        d["eintraege"] = d["eintraege"][-3000:]
        _speichern(LERN, d)
    return eid


def bewerten(eid, wert):
    with _lock:
        d = _laden(LERN, {"naechste": 1, "eintraege": []})
        for e in d["eintraege"]:
            if e["id"] == eid:
                e["bewertung"] = 1 if wert > 0 else -1 if wert < 0 else 0
                _speichern(LERN, d)
                return True
    return False


def _punkte(e):
    """Wie gut war diese Antwort? 👍 zählt am meisten, 👎 am stärksten negativ, Fehler sind schlecht."""
    if not e["ok"]:
        return 0.0
    if e["bewertung"] > 0:
        return 1.0
    if e["bewertung"] < 0:
        return 0.0
    return 0.7          # ohne Bewertung: hat geantwortet, aber unbekannt ob gut


def werte(kategorie):
    """Erfahrung je Gehirn in einer Aufgaben-Art: {modell: (anzahl, guete 0..1, mittlere dauer)}."""
    d = _laden(LERN, {"eintraege": []})
    gruppen = {}
    for e in d["eintraege"][-1500:]:
        if e["kategorie"] == kategorie:
            gruppen.setdefault(e["modell"], []).append(e)
    out = {}
    for m, es in gruppen.items():
        n = len(es)
        guete = (sum(_punkte(e) for e in es) + 1) / (n + 2)      # vorsichtig gemittelt (wenig Erfahrung = 0,5)
        dauer = sum(e["dauer"] for e in es) / n
        out[m] = (n, guete, dauer)
    return out


def ordnen(kategorie, kandidaten):
    """Kandidaten nach Erfahrung sortieren. Unerprobte Gehirne bekommen ab und zu eine Chance (Neugier)."""
    w = werte(kategorie)
    def note(m):
        n, guete, dauer = w.get(m, (0, 0.6, 30.0))     # neu: leicht positiv, damit es ausprobiert wird
        return guete - min(dauer, 120) / 600            # langsam kostet etwas (max. -0,2)
    reihe = sorted(kandidaten, key=note, reverse=True)
    return reihe


def statistik():
    d = _laden(LERN, {"eintraege": []})
    es = d["eintraege"]
    kats = {}
    for e in es:
        k = kats.setdefault(e["kategorie"], {})
        m = k.setdefault(e["modell"], {"anzahl": 0, "gut": 0, "schlecht": 0, "fehler": 0, "dauer": 0.0})
        m["anzahl"] += 1; m["dauer"] += e["dauer"]
        m["gut"] += e["bewertung"] > 0; m["schlecht"] += e["bewertung"] < 0; m["fehler"] += not e["ok"]
    for k in kats.values():
        for m in k.values():
            m["dauer"] = round(m["dauer"] / m["anzahl"], 1)
    return {"anzahl": len(es), "bewertet": sum(1 for e in es if e["bewertung"]),
            "gut": sum(1 for e in es if e["bewertung"] > 0), "schlecht": sum(1 for e in es if e["bewertung"] < 0),
            "kategorien": kats}


# ---------------- Wissensbuch ----------------
STOP = set("der die das ein eine einer eines und oder aber ich du er sie es wir ihr mir mich dir dich ist sind war "
           "wie was wer wo wann warum wieso welche welcher welches mit von zu zum zur im in am an auf für bei über "
           "unter nach vor aus bitte kannst kann können soll sollte mein meine dein deine jim watson nicht noch auch "
           "nur schon sehr mal denn dann wenn ob als so ja nein".split())


def _woerter(t):
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", (t or "").lower()) if w not in STOP}


def wissen_merken(frage, antwort, quelle, zusammenfassung=""):
    with _lock:
        d = _laden(WISSEN, {"naechste": 1, "eintraege": []})
        eid = d["naechste"]; d["naechste"] += 1
        d["eintraege"].append({"id": eid, "datum": time.strftime("%d.%m.%Y"), "frage": frage.strip()[:1000],
                               "antwort": antwort.strip()[:8000], "kurz": zusammenfassung.strip()[:1500],
                               "quelle": quelle.strip()[:80] or "unbekannt"})
        _speichern(WISSEN, d)
    return eid


def wissen_liste():
    return list(reversed(_laden(WISSEN, {"eintraege": []})["eintraege"]))


def wissen_loeschen(eid):
    with _lock:
        d = _laden(WISSEN, {"naechste": 1, "eintraege": []})
        d["eintraege"] = [e for e in d["eintraege"] if e["id"] != eid]
        _speichern(WISSEN, d)


def wissen_passend(frage, anzahl=3):
    """Die Einträge, die am besten zur Frage passen (einfacher Wortvergleich)."""
    q = _woerter(frage)
    if not q:
        return []
    treffer = []
    for e in _laden(WISSEN, {"eintraege": []})["eintraege"]:
        w = _woerter(e["frage"] + " " + (e["kurz"] or e["antwort"][:1500]))
        gemeinsam = len(q & w)
        if gemeinsam >= max(1, min(2, len(q) // 3)):
            treffer.append((gemeinsam / (len(q) ** 0.5), e))
    treffer.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in treffer[:anzahl]]
