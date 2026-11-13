"""
Watsons Sicherung (Backup) – "ein treuer Verwalter sichert, was ihm anvertraut ist".

Gesichert wird alles, was man NICHT einfach neu installieren kann:
  - Gedächtnis-Ordner, CLAUDE.md, Ablage, Dokumente
  - Watson Studio: Programm-Dateien, Werkzeug-Liste, Protokoll, Gespräche + Merkzettel (watson.db)
  - Einstellungen OHNE Schlüssel (OpenRouter- und n8n-Schlüssel kommen nie in die Sicherung)
  - n8n-Abläufe (ohne Zugangsdaten)
Nicht gesichert (lässt sich neu installieren): .venv, mcp-pakete, Browser-Profil, n8n-Programm.

Ziel: OneDrive\\Watson-Sicherungen\\Watson-Sicherung_JJJJ-MM-TT_HHMM.zip – die letzten 14 bleiben.
"""
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

import pfade
WATSON = pfade.WATSON_HOME          # Gedächtnis, Ablage …
STUDIO = pfade.DATEN                # Einstellungen, Gespräche
ZIEL = (Path(os.environ["OneDrive"]) if os.environ.get("OneDrive") else Path.home() / "Documents") / "Watson-Sicherungen"
BEHALTEN = 14
SECRET_KEYS = ("api_key", "n8n_api_key", "google_client_secret")

SKIP_DIRS = {".venv", "mcp-pakete", ".webview", "browser-profil", "__pycache__", ".playwright-mcp", "node_modules"}
SKIP_FILES = {"einstellungen.json", "watson.db", "watson.db-wal", "watson.db-shm"}

ANLEITUNG = """WATSON – SICHERUNG WIEDERHERSTELLEN
====================================
Diese Datei ist eine Sicherung von Watson (Gedächtnis, Gespräche, Abläufe, Watson Studio).

Am einfachsten: Watson in Claude bitten: „Stelle die Sicherung <Dateiname> wieder her.“

Von Hand:
1. Watson Studio schließen.
2. Inhalt dieser ZIP-Datei in deinen Watson-Ordner entpacken (überschreiben).
3. studio\\einstellungen-ohne-schluessel.json in studio\\einstellungen.json umbenennen.
4. Watson Studio starten und die Schlüssel neu eintragen:
   - Tab „Gehirne“: OpenRouter-Schlüssel (openrouter.ai/keys)
   - Tab „Abläufe“: n8n-API-Schlüssel (in n8n: Settings → n8n API)
5. n8n-Abläufe liegen im Ordner n8n-ablaeufe\\ und werden mit
   „python studio\\sicherung.py --n8n-import <Ordner>“ wieder in n8n geladen.
   Zugangsdaten (Gmail usw.) müssen in n8n neu eingerichtet werden.
Programm-Teile (.venv, mcp-pakete, n8n in Ubuntu) werden bei Bedarf neu installiert.
"""


def _letzte():
    if not ZIEL.exists():
        return None
    files = sorted(ZIEL.glob("Watson-Sicherung_*.zip"))
    return files[-1] if files else None


def faellig(stunden=24):
    last = _letzte()
    return last is None or (time.time() - last.stat().st_mtime) > stunden * 3600


def _add_tree(z, root: Path, arc_root: str):
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file() and p.name not in SKIP_FILES and p.stat().st_size < 50 * 1024 * 1024:
            z.write(p, f"{arc_root}/{rel.as_posix()}" if arc_root else rel.as_posix())


def sichern(n8n_export=None):
    """Erstellt eine Sicherung. n8n_export: Funktion(ordner) -> Anzahl exportierter Abläufe (optional)."""
    ZIEL.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    ziel = ZIEL / f"Watson-Sicherung_{stamp}.zip"
    info = {"zeit": time.strftime("%d.%m.%Y %H:%M"), "n8n_ablaeufe": 0, "warnungen": []}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Gespräche + Merkzettel: sauber kopieren, auch während Watson läuft
        if (STUDIO / "watson.db").exists():
            src = sqlite3.connect(str(STUDIO / "watson.db"))
            dst = sqlite3.connect(str(tmp / "watson.db"))
            src.backup(dst)
            dst.close(); src.close()
        # Einstellungen ohne Schlüssel
        if (STUDIO / "einstellungen.json").exists():
            cfg = json.loads((STUDIO / "einstellungen.json").read_text(encoding="utf-8"))
            for k in SECRET_KEYS:
                cfg.pop(k, None)
            (tmp / "einstellungen-ohne-schluessel.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                                                   encoding="utf-8")
        # n8n-Abläufe
        if n8n_export:
            try:
                (tmp / "n8n").mkdir()
                info["n8n_ablaeufe"] = n8n_export(tmp / "n8n")
            except Exception as e:
                info["warnungen"].append(f"n8n-Abläufe nicht gesichert: {e}")
        with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("WIEDERHERSTELLEN.txt", ANLEITUNG)
            for item in WATSON.iterdir():
                if item.name in SKIP_DIRS or item.name == "studio":
                    continue
                if item.is_dir():
                    _add_tree(z, item, item.name)
                elif item.is_file():
                    z.write(item, item.name)
            _add_tree(z, STUDIO, "studio")
            if (tmp / "watson.db").exists():
                z.write(tmp / "watson.db", "studio/watson.db")
            if (tmp / "einstellungen-ohne-schluessel.json").exists():
                z.write(tmp / "einstellungen-ohne-schluessel.json", "studio/einstellungen-ohne-schluessel.json")
            for f in (tmp / "n8n").glob("*.json") if (tmp / "n8n").exists() else []:
                z.write(f, f"n8n-ablaeufe/{f.name}")
            z.writestr("sicherung-info.json", json.dumps(info, ensure_ascii=False, indent=2))
    # alte Sicherungen aufräumen
    alle = sorted(ZIEL.glob("Watson-Sicherung_*.zip"))
    for alt in alle[:-BEHALTEN]:
        alt.unlink()
    info.update(datei=str(ziel), groesse_kb=round(ziel.stat().st_size / 1024), anzahl=min(len(alle), BEHALTEN))
    return info


def pruefen(zip_path: Path):
    """Prüft, ob eine Sicherung vollständig und lesbar ist (ohne etwas zu überschreiben)."""
    out = {"ok": True, "fehler": []}
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            out["ok"] = False
            out["fehler"].append(f"beschädigt: {bad}")
        names = z.namelist()
        for muss in ("CLAUDE.md", "studio/watson_studio.py", "studio/app.html", "studio/watson.db"):
            if muss not in names:
                out["ok"] = False
                out["fehler"].append(f"fehlt: {muss}")
        out["gedaechtnis_dateien"] = len([n for n in names if n.startswith("gedaechtnis/")])
        out["n8n_ablaeufe"] = len([n for n in names if n.startswith("n8n-ablaeufe/")])
        out["schluessel_drin"] = any(k in z.read(n).decode("utf-8", "ignore")
                                     for n in names if n.endswith("einstellungen-ohne-schluessel.json")
                                     for k in ('"api_key"', '"n8n_api_key"'))
        if "studio/watson.db" in names:
            with tempfile.TemporaryDirectory() as tmp:
                z.extract("studio/watson.db", tmp)
                c = sqlite3.connect(str(Path(tmp) / "studio" / "watson.db"))
                out["gespraeche"] = c.execute("select count(*) from chats").fetchone()[0]
                out["nachrichten"] = c.execute("select count(*) from messages").fetchone()[0]
                out["fakten"] = c.execute("select count(*) from facts").fetchone()[0]
                c.close()
    return out


def wiederherstellen(zip_path: Path, ziel: Path = WATSON):
    """Spielt eine Sicherung zurück. Watson Studio sollte dabei geschlossen sein.
    Die aktuellen Dateien werden vorher selbst noch einmal gesichert (Sicherheitsnetz)."""
    netz = sichern() if ziel == WATSON else None
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n in ("WIEDERHERSTELLEN.txt", "sicherung-info.json") or n.startswith("n8n-ablaeufe/"):
                continue
            target = ziel / n
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    # Einstellungen zurück, aber vorhandene Schlüssel behalten
    neu = ziel / "studio" / "einstellungen-ohne-schluessel.json"
    if neu.exists():
        cfg = json.loads(neu.read_text(encoding="utf-8"))
        alt_file = ziel / "studio" / "einstellungen.json"
        if alt_file.exists():
            alt = json.loads(alt_file.read_text(encoding="utf-8"))
            for k in SECRET_KEYS:
                if alt.get(k):
                    cfg[k] = alt[k]
        alt_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        neu.unlink()
    for f in ("watson.db-wal", "watson.db-shm"):
        (ziel / "studio" / f).unlink(missing_ok=True)
    return {"ok": True, "sicherheitsnetz": netz["datei"] if netz else None}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--pruefen":
        print(json.dumps(pruefen(Path(sys.argv[2])), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(sichern(), ensure_ascii=False, indent=2))
