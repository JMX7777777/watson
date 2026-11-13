"""
Watsons Hände: klicken, tippen, Tasten drücken, Programme öffnen, Fenster wechseln.

Funktioniert über Windows UI Automation (wie das Text-Sehen): Watson liest den Bildschirm,
jedes bedienbare Element bekommt eine [Nummer], und Watson handelt über diese Nummer.
Jede Handlung wird vorher mit dem Nutzer bestätigt (siehe watson_studio.py).
"""
import ctypes
import os
import re
import subprocess
import time

import uiautomation as auto

import bildschirm_text as bt

# Wörter im Fenstertitel, bei denen Watson grundsätzlich NICHT tippt oder klickt
BLOCKED = ("bank", "sparkasse", "volksbank", "paypal", "klarna", "kreditkarte", "credit card", "wallet",
           "passwort", "password", "kennwort", "login", "anmelden", "sign in", "steuer", "elster", "kasse", "checkout")

PROGRAMS = {
    "editor": "notepad", "notepad": "notepad", "rechner": "calc", "taschenrechner": "calc", "calc": "calc",
    "explorer": "explorer", "datei-explorer": "explorer", "paint": "mspaint", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "outlook": "outlook", "edge": "msedge", "browser": "msedge",
    "einstellungen": "ms-settings:", "kalender": "outlookcal:", "uhr": "ms-clock:", "kamera": "microsoft.windows.camera:",
}

TOOLS = [
    {"type": "function", "function": {
        "name": "watson__klicken",
        "description": "Klickt auf ein Element mit [Nummer] aus dem letzten Bildschirm-Lesen. Danach Bildschirm neu lesen.",
        "parameters": {"type": "object", "properties": {"nr": {"type": "integer"}}, "required": ["nr"]}}},
    {"type": "function", "function": {
        "name": "watson__tippen",
        "description": "Schreibt Text in ein Eingabefeld/Dokument mit [Nummer]. 'ersetzen'=true löscht vorher den alten Inhalt.",
        "parameters": {"type": "object", "properties": {"nr": {"type": "integer"}, "text": {"type": "string"},
                                                        "ersetzen": {"type": "boolean"}}, "required": ["nr", "text"]}}},
    {"type": "function", "function": {
        "name": "watson__tasten",
        "description": "Drückt Tasten im vordersten Fenster, z. B. 'Enter', 'Tab', 'Strg+S', 'Strg+A', 'Alt+F4', 'Esc', 'Pfeil runter'.",
        "parameters": {"type": "object", "properties": {"tasten": {"type": "string"}}, "required": ["tasten"]}}},
    {"type": "function", "function": {
        "name": "watson__programm_oeffnen",
        "description": "Öffnet ein Programm, z. B. 'Editor', 'Rechner', 'Explorer', 'Paint', 'Word', 'Excel', 'Edge', 'Einstellungen'.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "watson__fenster_wechseln",
        "description": "Holt ein offenes Fenster nach vorne (Teil des Titels angeben).",
        "parameters": {"type": "object", "properties": {"titel": {"type": "string"}}, "required": ["titel"]}}},
]
NAMES = {t["function"]["name"] for t in TOOLS}


# Schritte, die auch bei „Auftrag erlaubt“ IMMER einzeln gefragt werden
RISKY_WORDS = ("senden", "absenden", "abschicken", "send", "löschen", "loeschen", "entfernen", "delete", "papierkorb",
               "kaufen", "bestellen", "bezahlen", "zahlungspflichtig", "buy", "order", "pay", "deinstallieren",
               "formatieren", "zurücksetzen", "überschreiben", "veröffentlichen", "posten", "publish")
RISKY_KEYS = ("alt+f4", "entf", "delete", "löschen", "umschalt+entf", "shift+delete")


def risky(name, args):
    """Gefährliche Schritte: Senden, Löschen, Kaufen, Fenster schließen …"""
    if name == "watson__klicken":
        e = bt.ELEMENTS.get(int(args.get("nr", 0) or 0))
        return bool(e) and any(w in e["name"].lower() for w in RISKY_WORDS)
    if name == "watson__tasten":
        spec = str(args.get("tasten", "")).lower().replace(" ", "")
        return any(k.replace(" ", "") in spec for k in RISKY_KEYS)
    if name == "watson__programm_oeffnen":
        return False
    return False


def _blocked(title):
    t = (title or "").lower()
    return any(w in t for w in BLOCKED)


def describe(name, args):
    """Klartext für das Bestätigungsfenster."""
    if name in ("watson__klicken", "watson__tippen"):
        e = bt.ELEMENTS.get(int(args.get("nr", 0)))
        where = f"{e['kind']} „{e['name']}“ im Fenster „{e['window']}“" if e else f"Element [{args.get('nr')}] (unbekannt)"
        if name == "watson__klicken":
            return f"Klicken auf: {where}"
        return f"Tippen in: {where}\nText: „{str(args.get('text', ''))[:300]}“" + \
               ("\n(alter Inhalt wird ersetzt)" if args.get("ersetzen") else "")
    if name == "watson__tasten":
        return f"Tasten drücken: {args.get('tasten')}\nim Fenster: „{bt._ctx.get('window') or 'vorderstes Fenster'}“"
    if name == "watson__programm_oeffnen":
        return f"Programm öffnen: {args.get('name')}"
    if name == "watson__fenster_wechseln":
        return f"Fenster nach vorne holen: {args.get('titel')}"
    return name


def _find(entry, deadline):
    """Element anhand seiner Windows-Kennung im Fenster wiederfinden."""
    root = auto.ControlFromHandle(entry["hwnd"])
    stack = [root]
    while stack and time.time() < deadline:
        c = stack.pop()
        try:
            if tuple(c.GetRuntimeId() or ()) == entry["rid"]:
                return c
            stack.extend(c.GetChildren())
        except Exception:
            continue
    return None


def _element(nr):
    e = bt.ELEMENTS.get(int(nr))
    if not e:
        raise RuntimeError(f"Element [{nr}] kenne ich nicht. Bitte zuerst den Bildschirm neu lesen.")
    if _blocked(e["window"]):
        raise RuntimeError("Aus Sicherheitsgründen bediene ich keine Bank-, Bezahl-, Login- oder Passwort-Fenster.")
    c = _find(e, time.time() + 5)
    if c is None:
        raise RuntimeError(f"Element [{nr}] ist nicht mehr da (das Fenster hat sich geändert). Bitte neu lesen.")
    return e, c


def _front(hwnd):
    try:
        auto.ControlFromHandle(hwnd).SetActive()
    except Exception:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


KEYMAP = {"strg": "{Ctrl}", "ctrl": "{Ctrl}", "alt": "{Alt}", "umschalt": "{Shift}", "shift": "{Shift}",
          "win": "{Win}", "enter": "{Enter}", "eingabe": "{Enter}", "tab": "{Tab}", "esc": "{Esc}",
          "escape": "{Esc}", "leertaste": "{Space}", "space": "{Space}", "entf": "{Delete}", "löschen": "{Delete}",
          "rücktaste": "{Back}", "backspace": "{Back}", "pos1": "{Home}", "ende": "{End}",
          "pfeil hoch": "{Up}", "pfeil runter": "{Down}", "pfeil links": "{Left}", "pfeil rechts": "{Right}",
          "hoch": "{Up}", "runter": "{Down}", "links": "{Left}", "rechts": "{Right}",
          "bild hoch": "{PageUp}", "bild runter": "{PageDown}"}


def _keys(spec):
    out = []
    for combo in re.split(r"\s*,\s*|\s+dann\s+", spec.strip()):
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        seq = ""
        for p in parts:
            if p in KEYMAP:
                seq += KEYMAP[p]
            elif re.fullmatch(r"f\d{1,2}", p):
                seq += "{" + p.upper() + "}"
            elif len(p) == 1:
                seq += p
            else:
                raise RuntimeError(f"Taste „{p}“ kenne ich nicht.")
        out.append(seq)
    return out


def run(name, args):
    """Führt eine Handlung aus (Bestätigung ist vorher schon passiert)."""
    with auto.UIAutomationInitializerInThread():
        if name == "watson__klicken":
            e, c = _element(args["nr"])
            for how in ("Invoke", "Toggle", "SelectionItem", "ExpandCollapse"):
                try:
                    if how == "Invoke":
                        c.GetInvokePattern().Invoke()
                    elif how == "Toggle":
                        c.GetTogglePattern().Toggle()
                    elif how == "SelectionItem":
                        c.GetSelectionItemPattern().Select()
                    else:
                        p = c.GetExpandCollapsePattern()
                        p.Expand() if p.ExpandCollapseState == 0 else p.Collapse()
                    break
                except Exception:
                    continue
            else:
                _front(e["hwnd"])
                c.Click(simulateMove=False)
            time.sleep(0.4)
            return f"Geklickt: {e['kind']} „{e['name']}“. Lies den Bildschirm neu, um das Ergebnis zu sehen."

        if name == "watson__tippen":
            e, c = _element(args["nr"])
            if e["password"] or getattr(c, "IsPassword", False):
                return "Abgelehnt: In Passwortfelder tippe ich grundsätzlich nicht."
            text = str(args.get("text", ""))
            try:
                vp = c.GetValuePattern()
                if vp.IsReadOnly:
                    raise RuntimeError
                vp.SetValue(text if args.get("ersetzen") else (vp.Value or "") + text)
            except Exception:
                _front(e["hwnd"])
                c.SetFocus()
                if args.get("ersetzen"):
                    auto.SendKeys("{Ctrl}a{Delete}", waitTime=0.05)
                auto.SetClipboardText(text)
                auto.SendKeys("{Ctrl}v", waitTime=0.1)
            time.sleep(0.3)
            return f"Getippt in {e['kind']} „{e['name']}“: „{text[:80]}“"

        if name == "watson__tasten":
            hwnd = bt._ctx.get("hwnd")
            if hwnd:
                if _blocked(bt._ctx.get("window")):
                    return "Abgelehnt: In Bank-, Bezahl-, Login- oder Passwort-Fenstern drücke ich keine Tasten."
                _front(hwnd)
            for seq in _keys(args["tasten"]):
                auto.SendKeys(seq, waitTime=0.15)
            return f"Gedrückt: {args['tasten']}"

        if name == "watson__programm_oeffnen":
            want = str(args["name"]).strip()
            target = PROGRAMS.get(want.lower())
            if not target:
                return (f"„{want}“ kenne ich noch nicht sicher. Bekannt sind: "
                        + ", ".join(sorted({k.capitalize() for k in PROGRAMS})))
            if target.endswith(":"):
                os.startfile(target)
            else:
                subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=0x08000000)
            time.sleep(2.0)
            return f"Geöffnet: {want}. Lies den Bildschirm, um es zu bedienen."

        if name == "watson__fenster_wechseln":
            want = str(args["titel"]).lower()
            for hwnd, title in bt.open_windows(30):
                if want in title.lower():
                    _front(hwnd)
                    return f"Vorne: „{title}“"
            return f"Kein Fenster mit „{args['titel']}“ im Titel gefunden."

    return "Unbekannte Handlung."
