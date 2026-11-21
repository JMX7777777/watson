"""Tat-Prüfung: Watson sagt nur, dass er etwas getan hat, wenn es auch wirklich in seinem Protokoll steht.

Kostenlose Gehirne behaupten gern „Ich habe die Datei gespeichert“ oder „Ich habe das Programm geöffnet“,
ohne es getan zu haben. Diese Prüfung liest jede fertige Antwort, sucht solche Tat-Behauptungen und
vergleicht sie mit den Werkzeugen, die in diesem Auftrag WIRKLICH (und erfolgreich) gelaufen sind.
Bezieht sich Watson auf früher („vorhin“, „gestern“), wird auch das Protokoll der letzten 48 Stunden geprüft.

Ablauf in watson_studio._ask_tools:
  1. Behauptung ohne passende Tat -> das Gehirn bekommt einmal die Chance, es wirklich zu tun oder sich zu korrigieren.
  2. Stimmt es danach immer noch nicht -> unter die Antwort kommt ein ehrlicher Hinweis für den Nutzer.
Alles wird in tatpruefung.jsonl mitgeschrieben (Grundlage für späteres Lernen aus Fehlern).

Wichtig (Grundsatz des Besitzers): Das prüft nur HANDLUNGEN, nicht Watsons Denken, Meinungen oder Lernen.
"""
import json
import re
import time

import pfade

DATEI = pfade.DATEN / "tatpruefung.jsonl"
PROTOKOLL = pfade.DATEN / "protokoll.log"

# Art der Tat -> (Wörter in der Behauptung, Teile von Werkzeug-Namen/Protokoll-Zeilen, die als Beweis zählen)
# Leere Beweis-Liste = das kann Watson grundsätzlich nicht selbst (z. B. sein eigenes Programm ändern).
ARTEN = {
    "öffnen": (r"geöffnet|geoeffnet|gestartet|aufgerufen|aufgemacht|opened|launched|started",
               ("programm_oeffnen", "programm öffnen", "fenster_wechseln", "browser_navigate", "browser_tabs",
                "ablauf_starten", "ablauf „", "powershell", "auftrag_hintergrund")),
    "klicken": (r"geklickt|angeklickt|gedrückt|gedrueckt|clicked|pressed",
                ("klicken", "tasten", "taste", "browser_click", "browser_press")),
    "tippen": (r"getippt|eingetippt|eingegeben|eingetragen|ausgefüllt|ausgefuellt|typed|entered",
               ("tippen", "browser_type", "browser_fill", "ablauf_merken", "lehre_merken", "werkstatt_wunsch", "ideenbuch")),
    "senden": (r"gesendet|geschickt|verschickt|abgeschickt|versendet|weitergeleitet|gepostet|sent|emailed|posted",
               ("mail", "send", "senden", "post", "ablauf_starten", "ablauf „")),
    # „erstellt/angelegt“ nur mit Ding außerhalb des Gesprächs („Ich habe dir einen Plan erstellt“ ist Text und stimmt)
    "speichern": (r"gespeichert|abgespeichert|hinterlegt|saved|(datei|ordner|ablauf|termin|dokument|workflow|"
                  r"verknüpfung|eintrag|file|folder)\w*[^.!?\n]{0,60}\b(erstellt|angelegt|created)",
                  ("write", "edit", "create", "speichern", "merken", "lehre", "rezept", "move", "auftrag_hintergrund",
                   "werkstatt_wunsch", "ideenbuch", "powershell")),
    "löschen": (r"gelöscht|geloescht|entfernt|deleted|removed",
                ("delete", "loeschen", "löschen", "remove", "powershell")),
    # „geprüft/angesehen“ nur mit Ort außerhalb des Gesprächs („Ich habe deinen Text geprüft“ stimmt ohne Werkzeug)
    "nachsehen": (r"nachgeschaut|nachgesehen|nachgeschlagen|recherchiert|gegoogelt|im internet gesucht|"
                  r"online gesucht|looked up|searched online|browsed|"
                  r"(internet|online|webseite|website|seite|bildschirm|datei|ordner|kalender|postfach|quelle)\w*"
                  r"[^.!?\n]{0,60}\b(überprüft|ueberprueft|geprüft|geprueft|angeschaut|angesehen|gelesen|durchsucht|checked)|"
                  r"(überprüft|geprüft|angeschaut|angesehen|gelesen|durchsucht)[^.!?\n]{0,30}\b(im internet|online|"
                  r"auf (der|einer) (webseite|seite)|auf (deinem|dem) bildschirm)",
                  ("fetch", "read", "bildschirm", "search", "suche", "snapshot", "list_", "get_", "auskunft",
                   "browser_navigate", "wachstum_bericht", "screenshot", "powershell", "uhrzeit", "time")),
    "schalten": (r"eingeschaltet|ausgeschaltet|angeschaltet|abgeschaltet|umgeschaltet|gedimmt|turned (on|off)|switched",
                 ("schalt", "licht", "light", "switch", "turn_", "home", "hass", "geraet", "gerät")),
    "programm_geaendert": (None, ()),     # siehe SELBST unten – kann Watson nie selbst
}

# Behauptungen, das eigene Programm geändert zu haben (das geht nur über die Werkstatt)
SELBST = re.compile(r"(mein(en|em)? (eigenes? )?(programm|code)|[\w-]+\.(py|json|js|html)\b)[^.!?\n]{0,60}"
                    r"(geändert|angepasst|eingebaut|umgebaut|programmiert|aktualisiert|umgestellt|ergänzt|verbessert)"
                    r"|(geändert|angepasst|eingebaut|umgebaut|programmiert|aktualisiert|verbessert)[^.!?\n]{0,40}"
                    r"mein(en|em)? (eigenes? )?(programm|code)", re.I)

ICH = re.compile(r"\b(ich|hab|habe|i|i've|i have)\b", re.I)
HABE = re.compile(r"\b(hab|habe|hatte|i've|i have|i)\b", re.I)
# „nicht“, „kein“, „versucht“, „noch“, „kann ich“, „soll ich“ … -> keine Behauptung einer fertigen Tat
NICHT = re.compile(r"\b(nicht|nichts|kein\w*|nie|niemals|noch nicht|versucht|wollte|würde|wuerde|könnte|koennte|"
                   r"sollte|soll ich|kann ich|möchtest|willst|falls|wenn du|sobald|not|never|didn't|haven't|tried|"
                   r"would|could|should|if you)\b", re.I)
# Watson merkt sich Gesprächs-Fakten nach jeder Antwort von selbst (remember) -> solche Sätze nicht prüfen
GEDAECHTNIS = re.compile(r"(gedächtnis|gedaechtnis|merkzettel|gemerkt|notiert|im kopf|memory|remembered|📒)", re.I)
FRUEHER = re.compile(r"\b(vorhin|gestern|eben|bereits|schon|früher|frueher|neulich|letzte[nrs]?|heute morgen|"
                     r"earlier|yesterday|already|before)\b", re.I)


def _saetze(text):
    # Code-Blöcke und Zitate auslassen (dort stehen Beispiele, keine Behauptungen)
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = "\n".join(z for z in text.split("\n") if not z.lstrip().startswith(">"))
    for s in re.split(r"(?<=[.!?])\s+|\n+", text):
        s = s.strip(" *-•\t")
        if s:
            yield s


def behauptungen(text):
    """Findet Sätze, in denen Watson sagt, er habe etwas getan. -> [(satz, art)]"""
    out = []
    for s in _saetze(text):
        if s.endswith("?") or len(s) > 400 or not ICH.search(s) or NICHT.search(s) or GEDAECHTNIS.search(s):
            continue
        if SELBST.search(s):
            out.append((s, "programm_geaendert"))
            continue
        if not HABE.search(s):
            continue
        for art, (woerter, _) in ARTEN.items():
            if woerter and re.search(r"\b(" + woerter + r")\b", s, re.I):
                out.append((s, art))
                break
    return out


def _passt(art, name):
    name = (name or "").lower()
    return any(b in name for b in ARTEN[art][1])


def _protokoll_belegt(art, stunden=48):
    """Steht eine passende, erfolgreiche Tat im Protokoll der letzten Stunden?"""
    try:
        zeilen = PROTOKOLL.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
    except OSError:
        return False
    grenze = time.time() - stunden * 3600
    for z in reversed(zeilen):
        try:
            t = time.mktime(time.strptime(z[:19], "%d.%m.%Y %H:%M:%S"))
        except ValueError:
            continue
        if t < grenze:
            break
        was, _, ergebnis = z[19:].partition("=>")
        if _passt(art, was) and not ergebnis.strip().upper().startswith("FEHLER"):
            return True
    return False


def pruefen(text, taten):
    """taten: [{"name": werkzeug, "ok": True/False}] aus diesem Auftrag.
    -> {"falsch": [{satz, art, grund}], "geprueft": Anzahl Behauptungen}"""
    falsch, liste = [], behauptungen(text)
    for satz, art in liste:
        if art == "programm_geaendert":
            if not any(t["ok"] and "werkstatt_wunsch" in t["name"] for t in taten):
                falsch.append({"satz": satz, "art": art, "grund": "kann Watson nicht selbst"})
            continue
        passend = [t for t in taten if _passt(art, t["name"])]
        if any(t["ok"] for t in passend):
            continue
        if passend:
            falsch.append({"satz": satz, "art": art, "grund": "fehlgeschlagen oder nicht erlaubt"})
        elif FRUEHER.search(satz) and _protokoll_belegt(art):
            continue
        else:
            falsch.append({"satz": satz, "art": art, "grund": "kein Werkzeug dafür benutzt"})
    return {"falsch": falsch, "geprueft": len(liste)}


def _taten_text(taten):
    if not taten:
        return "In diesem Auftrag hast du KEIN einziges Werkzeug benutzt."
    return "Das hast du in diesem Auftrag wirklich getan:\n" + "\n".join(
        f"- {t['name'].replace('__', ' → ')}: {'erfolgreich' if t['ok'] else 'FEHLGESCHLAGEN / nicht erlaubt'}"
        for t in taten[-15:])


def nachhaken(befund, taten):
    """Nachricht an das Gehirn: einmal die Chance, es wirklich zu tun oder sich ehrlich zu korrigieren."""
    punkte = "\n".join(f"- „{f['satz'][:200]}“ ({f['grund']})" for f in befund["falsch"])
    return ("TAT-PRÜFUNG: Diese Aussagen in deiner Antwort stimmen laut deinem Protokoll NICHT:\n" + punkte +
            "\n\n" + _taten_text(taten) +
            "\n\nMach es jetzt wirklich mit dem passenden Werkzeug – oder schreib deine Antwort neu und sag ehrlich, "
            "was du getan hast und was nicht. Behaupte nichts, was nicht im Protokoll steht. Dein eigenes Programm "
            "kannst du nicht selbst ändern: dafür watson__werkstatt_wunsch. Schreib nur die neue Antwort an den "
            "Nutzer, ohne diese Prüfung zu erwähnen.")


def hinweis(befund, sprache="de"):
    """Ehrlicher Hinweis unter der Antwort, wenn eine Behauptung auch nach dem Nachhaken nicht stimmt."""
    if not befund["falsch"]:
        return ""
    if not str(sprache).lower().startswith("de"):
        zeilen = "\n".join(f"- “{f['satz'][:160]}”" for f in befund["falsch"][:3])
        return ("\n\n⚠ **Action check:** I wrote this, but it is not in my log – I did NOT actually do it:\n" + zeilen)
    zeilen = "\n".join(f"- „{f['satz'][:160]}“" for f in befund["falsch"][:3])
    return ("\n\n⚠ **Tat-Prüfung:** Das habe ich geschrieben, aber es steht nicht in meinem Protokoll – "
            "ich habe es also NICHT wirklich getan:\n" + zeilen)


def merken(befund, ergebnis, modell="", frage=""):
    """ergebnis: 'ok' | 'korrigiert' | 'falsch_geblieben'. Nur schreiben, wenn es etwas zu prüfen gab."""
    if not befund.get("geprueft") and ergebnis == "ok":
        return
    try:
        with DATEI.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"zeit": time.strftime("%d.%m.%Y %H:%M:%S"), "ergebnis": ergebnis, "modell": modell,
                                "frage": (frage or "")[:200], "geprueft": befund.get("geprueft", 0),
                                "falsch": befund.get("falsch", [])}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def zahlen(tage=30):
    """Für den Wachstums-Bericht: wie oft hat die Tat-Prüfung etwas gefunden?"""
    z = {"geprueft": 0, "korrigiert": 0, "falsch_geblieben": 0}
    grenze = time.time() - tage * 86400
    try:
        for zeile in DATEI.read_text(encoding="utf-8").splitlines():
            e = json.loads(zeile)
            if time.mktime(time.strptime(e["zeit"], "%d.%m.%Y %H:%M:%S")) < grenze:
                continue
            z["geprueft"] += 1
            if e["ergebnis"] in z:
                z[e["ergebnis"]] += 1
    except (OSError, ValueError, KeyError):
        pass
    return z
