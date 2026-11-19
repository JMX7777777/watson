"""
Aufträge im Hintergrund: Watson nimmt eine längere Arbeit mit und meldet sich von selbst, wenn sie fertig ist.

Gebaut 16.11.2026, weil Watson ehrlich sagen musste: „Ich kann mich nicht von selbst später melden.“
  - Ein Auftrag wird in auftraege.json gespeichert (übersteht einen Neustart) und nacheinander abgearbeitet
    (einer nach dem anderen – die Gratis-Gehirne haben Grenzen).
  - Die Arbeit macht das Team (team.py): Chef plant, Rechercheur liest echte Quellen, Prüfer prüft.
  - Fertig: Ergebnis kommt als Nachricht ins Gespräch, aus dem der Auftrag kam, und die Oberfläche zeigt
    „📬 Watson ist fertig“.

Das Modul kennt Watson selbst nicht: `init(ausfuehren=…, fertig=…)` gibt die Arbeit und die Meldung von außen mit.
"""
import json
import threading
import time
import uuid

import pfade

DATEI = pfade.DATEN / "auftraege.json"
H = {}                       # ausfuehren(auftrag_dict) -> ergebnis_dict ; fertig(auftrag_dict) -> None
_lock = threading.Lock()
_wecker = threading.Event()
_thread = [None]


def init(**helfer):
    H.update(helfer)


def _laden():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except Exception:
        return []


def _speichern(liste):
    pfade.sicher_schreiben(DATEI, json.dumps(liste, ensure_ascii=False, indent=1))


def _aendern(aid, **felder):
    with _lock:
        liste = _laden()
        for a in liste:
            if a["id"] == aid:
                a.update(felder)
        _speichern(liste)


def alle(nur_offene=False):
    liste = _laden()
    return [a for a in liste if a["status"] in ("wartet", "läuft")] if nur_offene else liste


def starten(auftrag, chat_id=None, titel=""):
    """Legt einen Auftrag an und weckt den Arbeiter. Gibt den Auftrag zurück."""
    auftrag = (auftrag or "").strip()
    if not auftrag:
        raise ValueError("Leerer Auftrag")
    a = {"id": uuid.uuid4().hex[:8], "auftrag": auftrag[:4000], "titel": (titel or auftrag)[:80], "chat_id": chat_id,
         "status": "wartet", "erstellt": time.time(), "fertig": None, "fehler": ""}
    with _lock:
        liste = _laden()
        liste.append(a)
        _speichern(liste[-200:])                 # alte Einträge nicht endlos sammeln
    arbeiter_starten()
    _wecker.set()
    return a


def abbrechen(aid):
    _aendern(aid, status="abgebrochen", fertig=time.time())
    return {"ok": True}


def arbeiter_starten():
    """Startet den Hintergrund-Arbeiter (einmal). Unfertige Aufträge vom letzten Mal macht er weiter."""
    if _thread[0] and _thread[0].is_alive():
        return
    with _lock:
        liste = _laden()
        for a in liste:
            if a["status"] == "läuft":           # Watson wurde mittendrin beendet -> nochmal von vorn
                a["status"] = "wartet"
        _speichern(liste)
    _thread[0] = threading.Thread(target=_arbeiter, daemon=True)
    _thread[0].start()


def _arbeiter():
    while True:
        offen = [a for a in _laden() if a["status"] == "wartet"]
        if not offen:
            _wecker.wait(timeout=300)
            _wecker.clear()
            continue
        a = offen[0]
        _aendern(a["id"], status="läuft", gestartet=time.time())
        try:
            ergebnis = H["ausfuehren"](a)
            if any(x["id"] == a["id"] and x["status"] == "abgebrochen" for x in _laden()):
                continue
            _aendern(a["id"], status="fertig", fertig=time.time(),
                     sekunden=round(time.time() - a.get("gestartet", time.time())))
            a.update(status="fertig", ergebnis=ergebnis)
        except Exception as e:
            _aendern(a["id"], status="fehler", fertig=time.time(), fehler=str(e)[:300])
            a.update(status="fehler", fehler=str(e)[:300], ergebnis=None)
        try:
            H["fertig"](a)
        except Exception:
            pass
        time.sleep(5)                            # kurze Pause für die Gratis-Gehirne


TOOL = {"type": "function", "function": {
    "name": "watson__auftrag_hintergrund",
    "description": "Nimmt einen LÄNGEREN Auftrag mit und erledigt ihn im HINTERGRUND (Recherche mit echten Quellen, "
                   "Vergleich, Prüfung – mit deinem Team). Der Nutzer kann währenddessen weiter mit dir reden. Wenn du "
                   "fertig bist, meldest du dich VON SELBST im Gespräch mit dem Ergebnis. Benutze das, wenn eine Aufgabe "
                   "zu groß für eine schnelle Antwort ist, wenn du sagen würdest „ich mache als Nächstes …“ oder wenn "
                   "der Nutzer „Los“ sagt zu einer Arbeit, die du vorgeschlagen hast. Schreib den Auftrag vollständig "
                   "und klar (was genau suchen, lesen, prüfen, gegenüberstellen).",
    "parameters": {"type": "object", "properties": {
        "auftrag": {"type": "string", "description": "Der vollständige Auftrag mit allen Punkten"},
        "titel": {"type": "string", "description": "Kurzer Titel (wenige Wörter)"}},
        "required": ["auftrag"]}}}
NAME = TOOL["function"]["name"]

HINWEIS = ("\n\nDU KANNST IM HINTERGRUND ARBEITEN: Längere Aufträge (Recherche, mehrere Quellen lesen und prüfen, "
           "Vergleiche) gibst du mit watson__auftrag_hintergrund an dein Team. Es arbeitet weiter, während der Nutzer "
           "mit dir redet, und wenn es fertig ist, meldest du dich VON SELBST im Gespräch. Sag also NIE, du könntest "
           "dich nicht später melden oder nicht eigenständig weiterarbeiten – benutze dieses Werkzeug und sag dem Nutzer "
           "ehrlich: „Ich arbeite im Hintergrund daran und melde mich, sobald ich fertig bin (meist wenige Minuten).“ "
           "Versprich aber keine festen Uhrzeiten.")
