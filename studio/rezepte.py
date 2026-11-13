"""
Watsons Fertigkeiten (intern: Rezepte) – erprobte Vorgehensweisen, damit Aufgaben beim nächsten Mal schneller und sicherer klappen.

Ein Rezept entsteht auf zwei Wegen:
  1. Watson hat eine Aufgabe am Computer erfolgreich erledigt -> er schlägt vor, sich das Vorgehen zu merken.
  2. Der Nutzer schreibt selbst ein Rezept (z. B. „So möchte ich meine Briefe haben“) -> so erweitert er Watson.
Passt eine neue Aufgabe zu einem Rezept, bekommt das Gehirn das Rezept als Anleitung mit.
"""
import json
import re
import threading
import time

import pfade

DATEI = pfade.DATEN / "rezepte.json"
_lock = threading.Lock()
STOP = set("der die das ein eine einer eines und oder aber ich du er sie es wir mir mich dir dich ist sind war wie was "
           "wer wo wann warum mit von zu zum zur im in am an auf für bei über unter nach vor aus bitte kannst kann "
           "soll mein meine dein deine jim watson nicht noch auch nur schon sehr mal dann wenn als so ja nein".split())


def _woerter(t):
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", (t or "").lower()) if w not in STOP}


def _laden():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except Exception:
        return {"naechste": 1, "rezepte": []}


def _speichern(d):
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def liste():
    return sorted(_laden()["rezepte"], key=lambda r: (-r.get("benutzt", 0), r["titel"].lower()))


def speichern(titel, wann, schritte, quelle="Nutzer", rid=None):
    titel = (titel or "").strip()[:120]
    schritte = [s.strip() for s in (schritte or []) if s and s.strip()][:30]
    if not titel or not schritte:
        raise ValueError("Ein Rezept braucht einen Titel und mindestens einen Schritt.")
    with _lock:
        d = _laden()
        if rid:
            for r in d["rezepte"]:
                if r["id"] == int(rid):
                    r.update(titel=titel, wann=(wann or "").strip()[:400], schritte=schritte,
                             geaendert=time.strftime("%d.%m.%Y"))
                    _speichern(d)
                    return r["id"]
        rid = d["naechste"]; d["naechste"] += 1
        d["rezepte"].append({"id": rid, "titel": titel, "wann": (wann or "").strip()[:400], "schritte": schritte,
                             "quelle": quelle, "erstellt": time.strftime("%d.%m.%Y"), "benutzt": 0})
        _speichern(d)
        return rid


def loeschen(rid):
    with _lock:
        d = _laden()
        d["rezepte"] = [r for r in d["rezepte"] if r["id"] != int(rid)]
        _speichern(d)


def passend(aufgabe, anzahl=2):
    """Rezepte, die zur Aufgabe passen (Wortvergleich mit Titel und „Wann“)."""
    q = _woerter(aufgabe)
    if not q:
        return []
    treffer = []
    for r in _laden()["rezepte"]:
        w = _woerter(r["titel"] + " " + r.get("wann", ""))
        gleich = q & w
        # Treffer: zwei gemeinsame Wörter – oder ein deutliches, längeres Wort (z. B. „bibelvers“, „bewerbung“)
        if len(gleich) >= 2 or any(len(x) >= 6 for x in gleich):
            treffer.append((len(gleich) + sum(len(x) >= 6 for x in gleich) * 0.5, r))
    treffer.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in treffer[:anzahl]]


def benutzt(rids):
    if not rids:
        return
    with _lock:
        d = _laden()
        for r in d["rezepte"]:
            if r["id"] in rids:
                r["benutzt"] = r.get("benutzt", 0) + 1
        _speichern(d)


def als_text(rezepte_liste):
    return "\n".join(f"FERTIGKEIT „{r['titel']}“ ({'selbst gelernt' if r.get('quelle') == 'Watson' else 'vom Nutzer geschrieben'}):\n" +
                     "\n".join(f"  {i}. {s}" for i, s in enumerate(r["schritte"], 1)) for r in rezepte_liste)
