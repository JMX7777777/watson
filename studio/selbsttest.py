"""
Watsons Selbsttest – ein nächtlicher Gesundheits-Check (seit 22.11.2026).

Jede Nacht (Schritt „selbsttest“ in der Abendrunde) probiert Watson leise seine wichtigsten Fähigkeiten aus:
Gehirn, Internet-Suche, YouTube, Gedächtnis, Datenbank, Handy-Seite, Handy-Tunnel, Abläufe (n8n), Stimme
(nur erzeugen, nie abspielen) und Sicherung. Ergebnis: selbsttest.json. Geht etwas nicht, meldet der Herzschlag
es morgens; der Morgenbericht von Claude liest die Datei ebenfalls.
Kostet nichts (eine kleine Frage an ein Gratis-Gehirn) und macht keinen Ton.
"""
import json
import sqlite3
import threading
import time
import urllib.request

import pfade

DATEI = pfade.DATEN / "selbsttest.json"
H = {}            # aus watson_studio: frage, schnell, mem, mund, stimme_name, sicherung, n8n_hub, n8n_an, handy
_lock = threading.Lock()
YOUTUBE_PROBE = "https://www.youtube.com/watch?v=hJ6aYSA-Xq4"     # Video mit Untertiteln (vom 22.11.2026)


def init(**helfer):
    H.update(helfer)


# ---------------- Die einzelnen Tests: geben (ok, kurzer Text) zurück ----------------
def t_gehirn():
    text, modell = H["frage"]([{"role": "user", "content": "Antworte nur mit dem Wort: bereit"}], H["schnell"])
    return ("bereit" in text.lower(), f"{modell.split('/')[-1]} antwortet" if text else "keine Antwort")


def t_internet():
    import wachstum
    treffer = wachstum.internet_suchen("Psalm 23 Der Herr ist mein Hirte", 3)
    return (len(treffer) > 0, f"{len(treffer)} Treffer")


def t_youtube():
    import youtube
    r = youtube.lesen(YOUTUBE_PROBE, max_zeichen=800)
    ok = isinstance(r, str) and "Untertitel:" in r and len(r) > 300
    return (ok, "Untertitel gelesen" if ok else str(r)[:120])


def t_gedaechtnis():
    mem = H["mem"]
    n = mem._x("SELECT COUNT(*) FROM facts").fetchone()[0]
    gefunden = mem.relevant_facts("Bibel Glaube Gott", k=3)
    return (n > 0 and len(gefunden) > 0, f"{n} Fakten, Suche findet {len(gefunden)}")


def t_datenbank():
    con = sqlite3.connect(f"file:{pfade.DATEN / 'watson.db'}?mode=ro", uri=True, timeout=10)
    try:
        r = con.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        con.close()
    return (r == "ok", "unbeschädigt" if r == "ok" else r[:120])


def t_handy_seite():
    port = H["handy"].PORT
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=10) as r:
        j = json.loads(r.read().decode("utf-8"))
    return ("pin_gesetzt" in j, "antwortet")


def t_handy_tunnel():
    s = H["handy"].tailscale_status()
    if not s.get("installiert"):
        return (None, "Tailscale nicht installiert – übersprungen")
    if s.get("fehler"):
        return (False, s["fehler"][:120])
    if not s.get("angemeldet"):
        return (False, f"Tailscale nicht verbunden ({s.get('zustand')})")
    return (bool(s.get("tunnel_an")), "Tunnel an" if s.get("tunnel_an") else "Tunnel ist aus – Handy erreicht Watson nicht")


def t_n8n():
    if not H["n8n_an"]():
        return (None, "Abläufe ausgeschaltet – übersprungen")
    hub = H["n8n_hub"]
    if not hub.installed():
        return (None, "n8n nicht installiert – übersprungen")
    if not hub.running():
        hub.start()
    return (hub.bereit(), "bereit" if hub.bereit() else "startet nicht")


def t_stimme():
    mund = H["mund"]()
    if mund is None:
        return (None, "Stimme nicht eingerichtet – übersprungen")
    audio, rate = mund._synth("Alles in Ordnung.", H["stimme_name"]())     # nur erzeugen, NIE abspielen
    sek = len(audio) / rate if rate else 0
    return (sek > 0.3, f"{sek:.1f} s erzeugt (still)")


def t_sicherung():
    s = H["sicherung"]
    letzte = s._letzte()
    if letzte is None:
        return (False, "noch keine Sicherung")
    alter_h = (time.time() - letzte.stat().st_mtime) / 3600
    if alter_h > 48:
        return (False, f"letzte Sicherung ist {alter_h / 24:.0f} Tage alt")
    p = s.pruefen(letzte)
    return (p["ok"], f"vor {alter_h:.0f} Std., lesbar" if p["ok"] else "; ".join(p["fehler"])[:120])


TESTS = [("Gehirn", t_gehirn), ("Internet-Suche", t_internet), ("YouTube", t_youtube),
         ("Gedächtnis", t_gedaechtnis), ("Datenbank", t_datenbank), ("Handy-Seite", t_handy_seite),
         ("Handy-Tunnel", t_handy_tunnel), ("Abläufe (n8n)", t_n8n), ("Stimme", t_stimme), ("Sicherung", t_sicherung)]


def lauf():
    """Alle Tests nacheinander. Ein Fehler in einem Test stoppt die anderen nie."""
    ergebnisse = []
    for name, f in TESTS:
        t0 = time.time()
        try:
            ok, text = f()
        except Exception as e:
            ok, text = False, f"{type(e).__name__}: {str(e)[:140]}"
        ergebnisse.append({"name": name, "ok": ok, "text": text, "dauer": round(time.time() - t0, 1)})
    kaputt = [e["name"] for e in ergebnisse if e["ok"] is False]
    eintrag = {"zeit": time.strftime("%d.%m.%Y %H:%M"), "t": time.time(), "ergebnisse": ergebnisse,
               "ok": sum(1 for e in ergebnisse if e["ok"]), "kaputt": kaputt,
               "uebersprungen": sum(1 for e in ergebnisse if e["ok"] is None)}
    with _lock:
        try:
            alt = json.loads(DATEI.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            alt = {"verlauf": []}
        alt["letzter"] = eintrag
        alt["verlauf"] = (alt.get("verlauf", []) + [{k: eintrag[k] for k in ("zeit", "ok", "kaputt")}])[-30:]
        DATEI.write_text(json.dumps(alt, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": eintrag["ok"], "kaputt": kaputt, "uebersprungen": eintrag["uebersprungen"]}


def letzter():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8")).get("letzter")
    except (OSError, ValueError):
        return None
