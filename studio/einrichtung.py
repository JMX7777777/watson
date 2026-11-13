"""
Wird vom Installer aufgerufen: übernimmt die Antworten aus dem Einrichtungs-Assistenten
(Land, Sprache, Name, Anrede, Grundhaltung, Stimme, Menüsprache) in Watsons Einstellungen.

Aufruf:  python einrichtung.py <antworten.json>
Vorhandene Einstellungen (z. B. bei einer Neuinstallation) bleiben erhalten, nur diese Felder werden gesetzt.
"""
import json
import sys

import pfade
import sprachen

CHARAKTER_FELDER = ("name", "nutzer", "anrede", "vorlage", "eigenes", "land", "land_name", "sprache")


def uebernehmen(antworten):
    datei = pfade.DATEN / "einstellungen.json"
    cfg = {}
    if datei.exists():
        try:
            cfg = json.loads(datei.read_text(encoding="utf-8"))
        except ValueError:
            cfg = {}
    c = dict(cfg.get("charakter") or {})
    for k in CHARAKTER_FELDER:
        v = (antworten.get("charakter") or {}).get(k)
        if v is not None:
            c[k] = str(v).strip()[:3000]
    if c.get("sprache") not in sprachen.SPRACHEN:
        c["sprache"] = "en"
    if c.get("vorlage") not in ("christlich", "freundlich", "eigene"):
        c["vorlage"] = "freundlich"
    if c.get("anrede") not in ("du", "Sie"):
        c["anrede"] = "du"
    cfg["charakter"] = c
    if antworten.get("ui_sprache") in ("de", "en"):
        cfg["ui_sprache"] = antworten["ui_sprache"]
    if antworten.get("piper_voice"):
        cfg["piper_voice"] = antworten["piper_voice"]
        cfg["tts_engine"] = "piper"
    datei.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


if __name__ == "__main__":
    a = json.loads(open(sys.argv[1], encoding="utf-8-sig").read())
    uebernehmen(a)
    print("ok")
