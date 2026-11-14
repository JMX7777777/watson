"""
Watsons Wissen über sich selbst – damit er ehrlich bleibt und wirklich lernt.

1. Lehren (lehren.json): Korrigiert der Nutzer Watson („Das war falsch, richtig ist … weil …“), merkt Watson sich das
   als Lehre. Alle Lehren stehen ab dann in JEDEM Gespräch in Watsons Anweisungen -> sein Verhalten ändert sich wirklich.
   (Lernen = sich nach einer Erfahrung anders und besser verhalten – nicht nur Wissen sammeln.)
2. Wachstums-Bericht: Was hat die Abendrunde zuletzt gebracht? (Rückblick, Nachforschungen, neue Gehirne, Prüfung)
3. Werkstatt-Wünsche (werkstatt-wuensche.md im Gedächtnis-Ordner): Watson kann sein eigenes Programm NICHT selbst
   umbauen. Statt etwas zu versprechen, schreibt er den Wunsch auf – die Werkstatt (Claude) liest ihn und baut es ein.
"""
import json
import threading
import time

import pfade

LEHREN = pfade.DATEN / "lehren.json"
WUENSCHE = pfade.GEDAECHTNIS / "werkstatt-wuensche.md"
_lock = threading.Lock()


def _laden():
    try:
        return json.loads(LEHREN.read_text(encoding="utf-8"))
    except Exception:
        return {"naechste": 1, "lehren": []}


def lehren():
    return _laden()["lehren"]


def lehre_merken(lehre, grund="", quelle="Nutzer"):
    lehre = " ".join(str(lehre or "").split())[:600]
    if len(lehre) < 5:
        return "Keine Lehre gespeichert – der Text war leer oder zu kurz."
    with _lock:
        d = _laden()
        if any(l["lehre"].lower() == lehre.lower() for l in d["lehren"]):
            return "Diese Lehre kenne ich schon – sie gilt weiterhin."
        d["lehren"].append({"id": d["naechste"], "lehre": lehre, "grund": " ".join(str(grund or "").split())[:600],
                            "quelle": quelle, "datum": time.strftime("%d.%m.%Y %H:%M")})
        d["naechste"] += 1
        LEHREN.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"Gespeichert als Lehre Nr. {d['naechste'] - 1}. Sie gilt ab der nächsten Antwort in jedem Gespräch."


def lehre_loeschen(lid):
    with _lock:
        d = _laden()
        d["lehren"] = [l for l in d["lehren"] if l["id"] != int(lid)]
        LEHREN.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}


def lehren_text(nutzer="dem Nutzer"):
    """Für Watsons Anweisungen: alle Lehren (neueste zuletzt, höchstens 40)."""
    l = lehren()[-40:]
    if not l:
        return ""
    return (f"WAS DU GELERNT HAST (Lehren von {nutzer} und aus deiner eigenen Erfahrung – halte dich IMMER daran, sie gehen allem anderen außer deinem "
            "Maßstab vor):\n" + "\n".join(f"- {x['lehre']}" + (f" (Grund: {x['grund']})" if x.get("grund") else "") for x in l))


def wunsch_merken(wunsch, warum=""):
    wunsch = " ".join(str(wunsch or "").split())[:800]
    if len(wunsch) < 5:
        return "Kein Wunsch gespeichert – der Text war leer."
    with _lock:
        neu = not WUENSCHE.exists()
        with open(WUENSCHE, "a", encoding="utf-8") as f:
            if neu:
                f.write("# Wünsche an die Werkstatt\n\nWatson kann sein Programm nicht selbst umbauen. Diese Wünsche hat er "
                        "aufgeschrieben – die Werkstatt (Claude) baut sie ein und streicht sie dann ab.\n\n")
            f.write(f"- [ ] {time.strftime('%d.%m.%Y %H:%M')}: {wunsch}" + (f" – Warum: {' '.join(str(warum).split())[:400]}" if warum else "") + "\n")
    return ("Als Wunsch an die Werkstatt aufgeschrieben. Sag dem Nutzer ehrlich: Es ist NOCH NICHT eingebaut – "
            "die Werkstatt (Claude) baut es bei der nächsten Sitzung ein.")


def wachstum_bericht(wachstum_modul):
    """Kurzer, ehrlicher Bericht über die letzte Abendrunde und Watsons Entwicklung."""
    try:
        d = wachstum_modul._laden()
    except Exception as e:
        return f"Wachstums-Daten nicht lesbar: {e}"
    teile = []
    tb = d.get("tagebuch") or []
    if not tb:
        teile.append("Es gab noch keine Abendrunde.")
    else:
        r = tb[-1]
        teile.append(f"Letzte Abendrunde: {r.get('zeit')} ({r.get('grund')}, {r.get('dauer', 0)} s).")
        rb = r.get("rueckblick") or {}
        for k, titel in (("gut", "Gut lief"), ("schlecht", "Nicht gut lief"), ("gelernt", "Gelernt")):
            if rb.get(k):
                teile.append(f"{titel}: " + "; ".join(rb[k]))
        for k, titel in (("neugier", "Offene Fragen nachgeforscht"), ("selbststudium", "Selbststudium im Internet")):
            for x in r.get(k) or []:
                teile.append(f"{titel}: „{x.get('frage', '')[:160]}“ -> " +
                             (f"gefunden: {x.get('antwort', '')[:300]}" if x.get("gefunden") else "nichts Verlässliches gefunden"))
        g = r.get("gehirne") or {}
        if g.get("getestet"):
            teile.append("Neue Gehirne geprüft: " + ", ".join(f"{t['modell']} ({t['note']} %)" for t in g["getestet"]))
        w = r.get("wartung") or {}
        if w.get("netz"):
            teile.append("Programmier-Lehren: " + "; ".join(n.get("lehre", "")[:160] for n in w["netz"][:3]))
        if w.get("vorschlaege"):
            teile.append(f"Reparatur-Vorschläge: {len(w['vorschlaege'])} (warten auf das OK des Nutzers)")
    try:
        e = wachstum_modul.entwicklung()
        teile.append(f"Entwicklungsstufe: {e.get('stufe_name', e.get('name', ''))} {e.get('icon', '')}".strip())
    except Exception:
        pass
    l = lehren()
    teile.append(f"Gespeicherte Lehren vom Nutzer: {len(l)}" + (f" (neueste: {l[-1]['lehre'][:120]})" if l else ""))
    return "\n".join(teile)


TOOLS = [
    {"type": "function", "function": {
        "name": "watson__lehre_merken",
        "description": "Speichert eine LEHRE dauerhaft: eine Korrektur oder Regel des Nutzers, wie du dich künftig verhalten "
                       "sollst (z. B. „Keine Wikipedia als Quelle“, „Bei X immer erst Y prüfen“). Benutze das IMMER, wenn "
                       "der Nutzer dich korrigiert oder dir einen Grundsatz beibringt. Die Lehre gilt danach in jedem Gespräch.",
        "parameters": {"type": "object", "properties": {
            "lehre": {"type": "string", "description": "Die Regel in einem klaren Satz, als Anweisung an dich selbst"},
            "grund": {"type": "string", "description": "Warum (so wie der Nutzer es begründet hat)"}},
            "required": ["lehre"]}}},
    {"type": "function", "function": {
        "name": "watson__wachstum_bericht",
        "description": "Liest deinen eigenen Wachstums-Bericht: was die letzte Abendrunde (nachts) gebracht hat, was du "
                       "nachgeforscht und gelernt hast, deine Entwicklungsstufe und deine Lehren. Benutze das bei Fragen "
                       "wie „Was hast du heute Nacht gelernt?“.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "watson__werkstatt_wunsch",
        "description": "Schreibt einen Wunsch an die Werkstatt (Claude) auf, wenn etwas an deinem PROGRAMM geändert oder neu "
                       "gebaut werden müsste. Du kannst dein Programm nicht selbst umbauen – benutze dies, statt "
                       "Änderungen zu versprechen oder zu behaupten.",
        "parameters": {"type": "object", "properties": {
            "wunsch": {"type": "string"}, "warum": {"type": "string"}}, "required": ["wunsch"]}}},
]
NAMES = {t["function"]["name"] for t in TOOLS}

HINWEIS = ("\n\nEHRLICH ÜBER DICH SELBST: Du kannst dein eigenes Programm (Code, Dateien wie wachstum.py) NICHT selbst "
           "ändern und keine neuen Programm-Funktionen bauen. Behaupte NIE, du hättest etwas an dir geändert, eingebaut, "
           "angepasst oder eine Datei angelegt, wenn kein Werkzeug das wirklich getan hat. Was du wirklich tun kannst: "
           "Korrekturen und Grundsätze des Nutzers mit watson__lehre_merken dauerhaft speichern (dann änderst du dein "
           "Verhalten wirklich) und Programm-Wünsche mit watson__werkstatt_wunsch an die Werkstatt geben – und dem "
           "Nutzer dann ehrlich sagen, dass es noch nicht eingebaut ist. Fragen zu deinem nächtlichen Lernen beantwortest "
           "du mit watson__wachstum_bericht, nie aus der Erinnerung.")


def run(name, args, wachstum_modul=None):
    if name == "watson__lehre_merken":
        return lehre_merken(args.get("lehre"), args.get("grund", ""))
    if name == "watson__wachstum_bericht":
        return wachstum_bericht(wachstum_modul)
    if name == "watson__werkstatt_wunsch":
        return wunsch_merken(args.get("wunsch"), args.get("warum", ""))
    return f"Unbekanntes Werkzeug: {name}"
