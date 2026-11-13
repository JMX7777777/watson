"""Baut studio/i18n.js (Menüsprache Englisch) aus der Wörterliste studio/i18n_en.json.

Aufruf:  studio\\.venv\\Scripts\\python.exe werkzeuge\\i18n_bauen.py
Meldet deutsche Texte aus app.html/handy.html, die noch keine Übersetzung haben (dann in i18n_en.json ergänzen).
"""
import html, json, re, sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
STUDIO = HIER.parent / "studio"
sys.path.insert(0, str(HIER))
import i18n_texte  # noqa: E402  (sammelt die Texte)

woerter = json.loads((STUDIO / "i18n_en.json").read_text(encoding="utf-8"))
gefunden = i18n_texte.sammeln([STUDIO / "app.html", STUDIO / "handy.html"])
fehlt = [t for t in gefunden if t not in woerter]
exakt, muster = {}, []
for d, e in woerter.items():
    d2, e2 = html.unescape(d), html.unescape(e)
    if sorted(re.findall(r"\{\d\}", d2)) != sorted(re.findall(r"\{\d\}", e2)):
        raise SystemExit(f"Platzhalter passen nicht: {d2!r} -> {e2!r}")
    if d2 == e2 and "{0}" not in d2:      # gleiche Muster behalten: ihre eingesetzten Teile werden übersetzt
        continue
    (muster.append([d2, e2]) if "{0}" in d2 else exakt.__setitem__(d2, e2))
kern = (HIER / "i18n_kern.js").read_text(encoding="utf-8")
(STUDIO / "i18n.js").write_text(
    "// Watson – Menüsprache Englisch. Automatisch erzeugt mit werkzeuge/i18n_bauen.py – nicht von Hand ändern,\n"
    "// sondern studio/i18n_en.json ergänzen. Gesprächsinhalte (.msg, Eingabefelder) werden nie übersetzt.\n"
    "window.WATSON_EN = " + json.dumps({"exakt": exakt, "muster": muster}, ensure_ascii=False) + ";\n" + kern,
    encoding="utf-8")
print(f"i18n.js: {len(exakt)} Texte, {len(muster)} Muster")
if fehlt:
    print(f"NOCH OHNE ÜBERSETZUNG ({len(fehlt)}):")
    for t in fehlt:
        print("  " + t)
