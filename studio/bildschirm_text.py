"""
Watsons "Text-Augen": liest den Bildschirm über Windows UI Automation – ohne Bild.

Windows weiß selbst, welche Fenster offen sind und welche Knöpfe, Texte, Menüs und
Eingabefelder darin stehen (das nutzen auch Bildschirmleser für blinde Menschen).
Watson fragt Windows einfach danach. Das ist schnell, genau und privat.
Passwort-Felder werden nie ausgelesen.
"""
import ctypes
import time
from ctypes import wintypes

import uiautomation as auto

user32 = ctypes.windll.user32
GW_HWNDNEXT = 2

# Steuerelement-Arten, die für den Nutzer interessant sind (deutsche Namen für das Gehirn)
KIND = {
    "ButtonControl": "Knopf", "EditControl": "Eingabefeld", "TextControl": "Text", "DocumentControl": "Dokument",
    "MenuItemControl": "Menüpunkt", "TabItemControl": "Tab", "HyperlinkControl": "Link", "CheckBoxControl": "Kästchen",
    "RadioButtonControl": "Auswahl", "ComboBoxControl": "Auswahlliste", "ListItemControl": "Listeneintrag",
    "TreeItemControl": "Eintrag", "DataItemControl": "Zelle", "HeaderItemControl": "Spaltenkopf",
    "MenuBarControl": "Menüleiste", "ToolBarControl": "Werkzeugleiste", "StatusBarControl": "Statusleiste",
    "WindowControl": "Fenster", "TitleBarControl": None, "ScrollBarControl": None, "ThumbControl": None,
    "SplitButtonControl": "Knopf", "ImageControl": "Bild", "GroupControl": "Gruppe", "PaneControl": None,
    "CustomControl": None, "ListControl": "Liste", "TreeControl": "Baum", "TableControl": "Tabelle",
    "DataGridControl": "Tabelle", "TabControl": None, "MenuControl": "Menü", "ToolTipControl": "Hinweis",
    "SliderControl": "Regler", "SpinnerControl": "Zähler", "ProgressBarControl": "Fortschritt",
}
# Watson selbst und unsichtbare Windows-Hilfsfenster nicht als "vorderstes Fenster" nehmen
SKIP_TITLES = ("Watson Studio", "Klick-und-Los", "Click to Do", "Windows-Eingabeerfahrung",
               "Windows Input Experience", "Startmenü", "Start", "Suche", "Search", "Benachrichtigungscenter",
               "Info-Center", "Taskleiste", "Program Manager")


def _visible(hwnd):
    return user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd)


def _title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def open_windows(limit=15):
    """Sichtbare Fenster in der Reihenfolge von vorne nach hinten."""
    out, hwnd = [], user32.GetTopWindow(None)
    while hwnd and len(out) < limit:
        if _visible(hwnd):
            t = _title(hwnd)
            if t and t not in SKIP_TITLES and not t.startswith("Watson Studio"):
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                if rect.right - rect.left > 120 and rect.bottom - rect.top > 80:
                    out.append((hwnd, t))
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
    return out


def _clean(s):
    """Symbol-Zeichen (z. B. Icon-Schriften) entfernen, Zeilenumbrüche glätten."""
    s = "".join(ch for ch in (s or "") if not 0xE000 <= ord(ch) <= 0xF8FF)
    return " ".join(s.split())


def _text_of(c):
    """Inhalt eines Eingabefelds/Dokuments lesen (erst Wert, sonst Text-Muster)."""
    try:
        v = c.GetValuePattern().Value
        if v:
            return _clean(v)
    except Exception:
        pass
    try:
        return _clean(c.GetTextPattern().DocumentRange.GetText(4000))
    except Exception:
        return ""


# Merkt sich nach jedem Lesen, welche Nummer zu welchem Element gehört (für die "Hände")
ELEMENTS = {}       # nr -> {"hwnd", "rid", "kind", "name", "window", "password"}
ACTIONABLE = {"Knopf", "Eingabefeld", "Menüpunkt", "Tab", "Link", "Kästchen", "Auswahl", "Auswahlliste",
              "Listeneintrag", "Eintrag", "Dokument", "Zelle", "Regler", "Zähler"}
_ctx = {"hwnd": None, "window": ""}


def _walk(ctrl, depth, lines, budget, deadline):
    if depth > 14 or budget[0] <= 0 or time.time() > deadline:
        return
    try:
        children = ctrl.GetChildren()
    except Exception:
        return
    for c in children:
        if budget[0] <= 0 or time.time() > deadline:
            return
        try:
            kind = KIND.get(c.ControlTypeName, c.ControlTypeName.replace("Control", ""))
            name = _clean(c.Name)
            value = ""
            if c.ControlTypeName in ("EditControl", "ComboBoxControl", "DocumentControl"):
                if getattr(c, "IsPassword", False):
                    value = "[Passwortfeld – wird nicht gelesen]"
                else:
                    value = _text_of(c)
            if kind and (name or value or kind in ("Eingabefeld", "Dokument")):
                state = "" if c.IsEnabled else " (ausgegraut)"
                nr = ""
                if kind in ACTIONABLE and c.IsEnabled:
                    n = len(ELEMENTS) + 1
                    ELEMENTS[n] = {"hwnd": _ctx["hwnd"], "rid": tuple(c.GetRuntimeId() or ()), "kind": kind,
                                   "name": name[:80], "window": _ctx["window"],
                                   "password": bool(getattr(c, "IsPassword", False))}
                    nr = f"[{n}] "
                text = f"{'  ' * min(depth, 8)}- {nr}{kind}: {name[:120]}"
                if value:
                    text += f" = „{value[:1500]}“"
                lines.append(text + state)
                budget[0] -= 1
        except Exception:
            continue
        _walk(c, depth + 1, lines, budget, deadline)


def read_screen(window_hint="", max_items=250, seconds=6.0):
    """Liest das vorderste Fenster (oder das, dessen Titel window_hint enthält) als Text."""
    wins = open_windows()
    if not wins:
        return "Es ist gerade kein Fenster offen (oder alle sind minimiert)."
    target = wins[0]
    if window_hint:
        for w in wins:
            if window_hint.lower() in w[1].lower():
                target = w
                break
    lines = [f"Offene Fenster (vorne zuerst): " + " | ".join(t for _, t in wins[:10]),
             f"\nInhalt von „{target[1]}“ (Elemente mit [Nummer] kann Watson anklicken oder beschreiben):"]
    ELEMENTS.clear()
    _ctx.update(hwnd=target[0], window=target[1])
    with auto.UIAutomationInitializerInThread():
        ctrl = auto.ControlFromHandle(target[0])
        budget = [max_items]
        _walk(ctrl, 0, lines, budget, time.time() + seconds)
        if budget[0] <= 0:
            lines.append("… (gekürzt – das Fenster hat noch mehr Inhalt)")
    return "\n".join(lines)


if __name__ == "__main__":
    t = time.time()
    print(read_screen()[:3000])
    print(f"\n({time.time() - t:.1f} s)")
