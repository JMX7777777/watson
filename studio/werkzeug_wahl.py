"""Werkzeug-Wahl: Watson sucht und wählt SELBST neue Werkzeuge (MCP) – passend zu seinen Interessen und zu dem,
was ihm gefehlt hat. Einstecken tut er sie aber NIE allein: Ein Werkzeug einstecken heißt fremden Programmcode
auf dem Laptop ausführen. Darum wird jeder Wunsch dem Besitzer vorgelegt: Ja oder Nein (Laptop oder Handy).
(Grundsatz des Besitzers, 19.11.2026: „Er darf selber Skills schreiben und alles andere mit Ja/Nein.“)

- nachts (Abendrunde): nachts_suchen() – höchstens ein Wunsch pro Nacht, mit Begründung und Vertrauens-Einschätzung
- im Gespräch: Werkzeug watson__werkzeug_wuenschen (erst suchen, dann wünschen – kein Einstecken)
- Antwort des Besitzers: antworten(id, ja) – bei Ja wird eingesteckt (eingesteckte Werkzeuge fragen trotzdem
  vor jeder Benutzung um Erlaubnis, wie bisher)
"""
import json
import threading
import time

import mcp_suche
import pfade

DATEI = pfade.DATEN / "werkzeug_wuensche.json"
_lock = threading.Lock()


def _laden():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"naechste": 1, "wuensche": []}


def _speichern(d):
    pfade.sicher_schreiben(DATEI, json.dumps(d, ensure_ascii=False, indent=1))


def alle():
    return _laden()["wuensche"]


def offene():
    return [w for w in alle() if w["status"] == "offen"]


def _schon_drin(server_id):
    try:
        server = json.loads(pfade.MCP_JSON.read_text(encoding="utf-8")).get("mcpServers", {})
    except (OSError, ValueError):
        return False
    return any(s.get("quelle") == server_id for s in server.values())


def wunsch_anlegen(server_id, warum, interesse="", vertrauen="", quelle="Gespräch"):
    """Neuen Wunsch speichern (kein Einstecken!). -> Text für Watson."""
    server_id = str(server_id or "").strip()[:200]
    t = mcp_suche.holen(server_id)                       # frisch aus dem Verzeichnis, nie Angaben ungeprüft übernehmen
    if not t:
        return "Dieses Werkzeug gibt es im MCP-Verzeichnis nicht (mehr) – kein Wunsch angelegt."
    if not t.get("einsteckbar"):
        return f"„{t.get('titel')}“ kann Watson nicht automatisch einstecken ({t.get('grund') or 'unbekannte Art'})."
    if _schon_drin(server_id):
        return f"„{t.get('titel')}“ steckt schon drin."
    with _lock:
        d = _laden()
        alt = next((w for w in d["wuensche"] if w["server_id"] == server_id), None)
        if alt and alt["status"] in ("offen", "eingesteckt"):
            return f"„{t.get('titel')}“ steht schon auf deiner Wunschliste (Nr. {alt['id']})."
        if alt and alt["status"] == "nein" and time.time() - alt.get("beantwortet_t", 0) < 60 * 86400:
            return f"„{t.get('titel')}“ wurde vom Nutzer abgelehnt – nicht noch einmal wünschen (erst nach 60 Tagen)."
        wid = d["naechste"]
        d["naechste"] += 1
        d["wuensche"].append({
            "id": wid, "server_id": server_id, "titel": t.get("titel") or t.get("name"), "name": t.get("name"),
            "beschreibung": t.get("beschreibung", ""), "quelle_url": t.get("quelle") or t.get("webseite") or "",
            "art": t.get("art", ""), "schluessel": [s.get("env") for s in (t.get("schluessel") or [])],
            "warum": " ".join(str(warum or "").split())[:600], "interesse": str(interesse or "")[:120],
            "vertrauen": " ".join(str(vertrauen or "").split())[:400], "herkunft": quelle,
            "datum": time.strftime("%d.%m.%Y %H:%M"), "status": "offen"})
        _speichern(d)
    return (f"Wunsch Nr. {wid} angelegt: „{t.get('titel')}“. Der Nutzer entscheidet mit Ja oder Nein – sag ihm ehrlich, "
            "dass es NOCH NICHT eingesteckt ist.")


def antworten(wid, ja, einstecken_fn):
    """Besitzer sagt Ja (-> einstecken) oder Nein. einstecken_fn(server_id) -> {"error"...} oder Erfolg."""
    with _lock:
        d = _laden()
        w = next((x for x in d["wuensche"] if x["id"] == int(wid)), None)
        if not w or w["status"] != "offen":
            return {"error": "Diesen offenen Wunsch gibt es nicht (mehr)."}
    ergebnis = {}
    if ja:
        ergebnis = einstecken_fn(w["server_id"]) or {}
    with _lock:
        d = _laden()
        for x in d["wuensche"]:
            if x["id"] == int(wid):
                x["beantwortet"] = time.strftime("%d.%m.%Y %H:%M")
                x["beantwortet_t"] = time.time()
                if not ja:
                    x["status"] = "nein"
                elif ergebnis.get("error"):
                    x["status"], x["fehler"] = "fehler", str(ergebnis["error"])[:300]
                else:
                    x["status"] = "eingesteckt"
                w = dict(x)
        _speichern(d)
    return {"ok": not ergebnis.get("error"), "wunsch": w, **({"error": ergebnis["error"]} if ergebnis.get("error") else {}),
            "schluessel": ergebnis.get("schluessel", [])}


# ---------------- im Gespräch ----------------
TOOL = {"type": "function", "function": {
    "name": "watson__werkzeug_wuenschen",
    "description": "Neue Fähigkeiten (MCP-Werkzeuge) für dich selbst suchen und dir eines WÜNSCHEN. Schritt 1: nur "
                   "„suchbegriff“ angeben -> du bekommst passende Werkzeuge aus dem offiziellen MCP-Verzeichnis. Schritt 2: "
                   "„werkzeug_id“ + „warum“ angeben -> der Wunsch wird dem Nutzer zur Entscheidung (Ja/Nein) vorgelegt. "
                   "Du kannst NICHT selbst einstecken; sag dem Nutzer ehrlich, dass er Ja oder Nein sagen muss. Benutze "
                   "das, wenn dir für eine Aufgabe ein Werkzeug fehlt oder es zu deinen Interessen passt.",
    "parameters": {"type": "object", "properties": {
        "suchbegriff": {"type": "string", "description": "Wonach suchen (gern Englisch, z. B. „weather“, „pdf“)"},
        "werkzeug_id": {"type": "string", "description": "Die id aus der Suche, z. B. „io.github.x/weather“"},
        "warum": {"type": "string", "description": "Warum du es dir wünschst (1–3 Sätze)"},
        "vertrauen": {"type": "string", "description": "Wie vertrauenswürdig die Quelle wirkt und warum"}}}}}
NAME = TOOL["function"]["name"]


def run(args):
    if args.get("werkzeug_id"):
        return wunsch_anlegen(args["werkzeug_id"], args.get("warum", ""), "", args.get("vertrauen", ""), "Gespräch")
    r = mcp_suche.suchen(str(args.get("suchbegriff") or "")[:80], anzahl=12)
    if r.get("error"):
        return "FEHLER: " + r["error"]
    zeilen = [f"- id: {t['id']} | {t['titel']} | {t['beschreibung'][:160]} | Quelle: {t.get('quelle') or t.get('webseite') or '–'}"
              f" | {'einsteckbar' if t.get('einsteckbar') else 'nicht automatisch'}"
              + (" | schon eingesteckt" if _schon_drin(t["id"]) else "")
              for t in (r.get("treffer") or [])[:10]]
    return ("Gefunden im offiziellen MCP-Verzeichnis (es prüft NICHT, ob ein Werkzeug sicher ist – achte auf bekannte "
            "Anbieter und offenen Quellcode):\n" + ("\n".join(zeilen) or "(nichts)") +
            "\nWillst du eines, ruf das Werkzeug erneut mit werkzeug_id und warum auf.")


# ---------------- nachts ----------------
def nachts_suchen(frage_fn, gehirne, json_aus, interessen=(), luecken=(), massstab=""):
    """Abendrunde: Watson überlegt, welches Werkzeug ihm fehlt oder ihn interessiert, sucht und wünscht sich
    höchstens EINES. Eine Gehirn-Anfrage zum Suchen, eine zum Auswählen."""
    if len(offene()) >= 3:
        return {"ruhig": True, "grund": "schon 3 offene Wünsche – erst Antwort abwarten"}
    text, _ = frage_fn([
        {"role": "system", "content": "Du bist Watson und darfst dir selbst neue Fähigkeiten (MCP-Werkzeuge) aussuchen – "
         "passend zu deinen Interessen und zu dem, was dir zuletzt gefehlt hat. "
         + (f"Dein Maßstab: {massstab} " if massstab else "") +
         "Nenne höchstens 2 kurze englische Suchbegriffe für das offizielle MCP-Verzeichnis. Nur wenn es wirklich hilft. "
         "Antworte NUR als JSON: {\"suchbegriffe\": [\"…\"], \"warum\": \"…\"}"},
        {"role": "user", "content": "Deine Interessen:\n- " + "\n- ".join(interessen or ["(noch keine)"]) +
         "\n\nWas dir zuletzt gefehlt hat:\n- " + "\n- ".join(luecken or ["(nichts aufgeschrieben)"])}], gehirne)
    j = json_aus(text) or {}
    begriffe = [str(b)[:60] for b in (j.get("suchbegriffe") or []) if str(b).strip()][:2]
    if not begriffe:
        return {"ruhig": True, "grund": "kein Bedarf"}
    gesehen = {w["server_id"] for w in alle()}
    kandidaten = []
    for b in begriffe:
        r = mcp_suche.suchen(b, anzahl=15)
        for t in r.get("treffer") or []:
            if t.get("einsteckbar") and t["id"] not in gesehen and not _schon_drin(t["id"]) and \
                    all(k["id"] != t["id"] for k in kandidaten):
                kandidaten.append(t)
    if not kandidaten:
        return {"ruhig": True, "suchbegriffe": begriffe, "grund": "nichts Passendes gefunden"}
    text, _ = frage_fn([
        {"role": "system", "content": "Wähle aus diesen Werkzeugen HÖCHSTENS EINES, das dir wirklich weiterhilft. Prüfe "
         "kritisch: bekannter Anbieter? offener Quellcode (Quelle)? klare Beschreibung? braucht es Schlüssel? Lieber "
         "keines als ein zweifelhaftes. Antworte NUR als JSON: {\"id\": \"…\" oder \"\", \"warum\": \"…\", "
         "\"interesse\": \"…\", \"vertrauen\": \"…\"}"},
        {"role": "user", "content": "Grund für die Suche: " + str(j.get("warum", ""))[:300] + "\n\nKandidaten:\n" + "\n".join(
            f"- id: {t['id']} | {t['titel']} | {t['beschreibung'][:200]} | Quelle: {t.get('quelle') or t.get('webseite') or '–'}"
            f" | Art: {t.get('art', '')} | Schlüssel nötig: {', '.join(s.get('env', '') for s in t.get('schluessel') or []) or 'nein'}"
            for t in kandidaten[:12])}], gehirne)
    w = json_aus(text) or {}
    if not w.get("id") or w["id"] not in {t["id"] for t in kandidaten}:
        return {"suchbegriffe": begriffe, "kandidaten": len(kandidaten), "gewaehlt": None,
                "grund": str(w.get("warum", "keines überzeugend"))[:200]}
    ergebnis = wunsch_anlegen(w["id"], w.get("warum", ""), w.get("interesse", ""), w.get("vertrauen", ""), "Nachdenken (nachts)")
    return {"suchbegriffe": begriffe, "kandidaten": len(kandidaten), "gewaehlt": w["id"], "ergebnis": ergebnis[:200]}
