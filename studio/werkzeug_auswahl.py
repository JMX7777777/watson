"""
Werkzeuge nach Bedarf (21.11.2026) – spart Tokens.

Gemessen am 21.11.2026: Bei jeder Frage mit Werkzeugen gingen ~27.000 Tokens nur für Werkzeug-Beschreibungen mit
(n8n-Baukasten allein ~13.400, Browser ~5.800, Dateien ~3.300) – und das bei JEDEM Zwischenschritt (bis 20×).

Jetzt nach der Stufenleiter-Idee („Brain First“ aus dem Second-Brain-Video):
- Kleine Grundwerkzeuge gehen immer mit (Watson-eigene, Hände, Webseiten lesen, Abläufe starten).
- Große Gruppen nur, wenn die Frage (oder die letzten Nachrichten) dazu passen.
- Fehlt trotzdem etwas, holt Watson die Gruppe selbst mit watson__werkzeuge_holen – ohne Nachfrage,
  es ist nur „Werkzeugkasten aufmachen“, keine Handlung. Erlaubnis-Regeln der Werkzeuge bleiben unverändert.
"""
import re

# Gruppe -> (Kurzbeschreibung für das Gehirn, Stichworte in der Frage)
GRUPPEN = {
    "n8n-baukasten": ("n8n-Abläufe bauen, prüfen, ändern und verwalten (Knoten, Workflows)",
                      r"n8n|ablauf|abläuf|workflow|automati|knoten|webhook|trigger|zeitplan|jeden (tag|morgen|abend)"),
    "browser": ("Den Edge-Browser steuern: Seiten öffnen, klicken, Formulare ausfüllen, anmelden, Screenshots",
                r"browser|edge|chrome|webseite|website|internetseite|seite (öffn|auf)|klick|formular|anmeld|einlogg|"
                r"login|bestell|youtube|http|www\.|\.de\b|\.com\b"),
    "dateien": ("Dateien und Ordner im Ablage-Ordner lesen, schreiben, suchen, verschieben",
                r"datei|ordner|ablage|dokument|\.txt|\.md|\.csv|\.json|speicher(e|n|t)?\b.{0,20}\b(als|unter|in)\b|abspeicher"),
    "uhrzeit": ("Uhrzeiten zwischen Zeitzonen umrechnen",
                r"zeitzone|wie spät.{0,30}\bin\b|uhrzeit.{0,30}\bin\b|umrechn.{0,20}(uhr|zeit)"),
    "system": ("Windows-Auskunft (Speicher, Programme, Akku, Netzwerk …) und PowerShell-Befehle",
               r"windows|system|powershell|prozess|laufwerk|festplatte|speicherplatz|akku|wlan|netzwerk|"
               r"installiert|treiber|dienst|cpu|\bram\b|arbeitsspeicher|update|langsam|deinstall"),
}
IMMER = {"webseiten"}          # klein (~400 Tokens), oft gebraucht

NAME = "watson__werkzeuge_holen"


def gruppe_von(tool, system_namen=()):
    n = tool["function"]["name"]
    if n in system_namen:
        return "system"
    if "__" in n and not n.startswith("watson__"):
        return n.split("__")[0]
    return None                 # Watson-eigenes Werkzeug -> immer dabei


def passende_gruppen(texte):
    t = " ".join(texte).lower()
    return {g for g, (_, muster) in GRUPPEN.items() if re.search(muster, t)}


def auswaehlen(alle, texte, system_namen=()):
    """-> (mitgeben, zurueckgehalten{gruppe: [tools]}). Unbekannte MCP-Gruppen (neu eingesteckt) gehen immer mit."""
    wahl = passende_gruppen(texte) | IMMER
    mit, weg = [], {}
    for t in alle:
        g = gruppe_von(t, system_namen)
        if g is None or g in wahl or g not in GRUPPEN:
            mit.append(t)
        else:
            weg.setdefault(g, []).append(t)
    if weg:
        mit.append(tool_holen(weg))
    return mit, weg


def tool_holen(weg):
    return {"type": "function", "function": {
        "name": NAME,
        "description": "Öffnet weitere Werkzeug-Gruppen, die gerade nicht geladen sind (spart Platz). Benutze es, "
                       "wenn du für die Aufgabe ein Werkzeug brauchst, das du nicht siehst. Verfügbar: " +
                       "; ".join(f"{g} = {GRUPPEN[g][0]}" for g in weg),
        "parameters": {"type": "object", "properties": {
            "gruppen": {"type": "array", "items": {"type": "string", "enum": sorted(weg)},
                        "description": "Welche Gruppen du brauchst"}},
            "required": ["gruppen"]}}}


def holen(args, tools, weg):
    """Führt watson__werkzeuge_holen aus: hängt die Gruppen an die Werkzeugliste an. -> Text fürs Gehirn."""
    gew = args.get("gruppen") or []
    if isinstance(gew, str):
        gew = [gew]
    neu = []
    for g in gew:
        if g in weg:
            tools.extend(weg.pop(g))
            neu.append(g)
    # Werkzeug „holen“ neu beschreiben (oder entfernen, wenn alles geladen ist)
    tools[:] = [t for t in tools if t["function"]["name"] != NAME]
    if weg:
        tools.append(tool_holen(weg))
    if not neu:
        return "Keine neue Gruppe geladen (schon da oder unbekannt). Verfügbar: " + (", ".join(weg) or "alles geladen")
    return "Geladen: " + ", ".join(neu) + ". Die Werkzeuge stehen dir ab jetzt zur Verfügung – benutze sie direkt."


def kuerzen(msgs, behalten=2, max_zeichen=1500):
    """Alte Werkzeug-Ergebnisse (z. B. riesige Browser-Abbilder) kürzen – die letzten `behalten` bleiben ganz.
    Jeder Zwischenschritt schickt alles erneut; so wächst die Anfrage nicht mit jedem Schritt um Tausende Tokens."""
    idx = [i for i, m in enumerate(msgs) if m.get("role") == "tool"]
    for i in idx[:-behalten] if behalten else idx:
        c = msgs[i].get("content")
        if isinstance(c, str) and len(c) > max_zeichen:
            msgs[i] = dict(msgs[i], content=c[:max_zeichen] + f"\n… (gekürzt, {len(c) - max_zeichen} Zeichen weggelassen, "
                                                               "weil schon verarbeitet)")
    return msgs
