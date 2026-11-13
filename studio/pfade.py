"""
Wo Watson was ablegt.

- Entwickler-Version (Ordner <Watson>\\studio): alles bleibt wie bisher.
- Installierte Version (Datei „installiert.txt“ neben dem Programm):
    Programm   ->  %LOCALAPPDATA%\\Programs\\Watson         (wird bei Updates ersetzt)
    Daten      ->  %LOCALAPPDATA%\\Watson                   (Einstellungen, Gespräche, Protokoll)
    Gedächtnis ->  %USERPROFILE%\\Watson\\gedaechtnis        (lesbare Notizen)
    Ablage     ->  %USERPROFILE%\\Watson\\ablage
  Die persönlichen Daten liegen also nie im Programm-Ordner und bleiben bei Updates erhalten.
"""
import json
import os
import shutil
import sys
from pathlib import Path

PROGRAMM = Path(__file__).resolve().parent
INSTALLIERT = (PROGRAMM / "installiert.txt").exists()

if INSTALLIERT:
    DATEN = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Watson"
    WATSON_HOME = Path.home() / "Watson"
    STIMMEN = DATEN / "stimmen"
else:
    DATEN = PROGRAMM
    WATSON_HOME = PROGRAMM.parent
    STIMMEN = PROGRAMM / "stimmen"

GEDAECHTNIS = WATSON_HOME / "gedaechtnis"
ABLAGE = WATSON_HOME / "ablage"
MCP_JSON = DATEN / "mcp.json"

for _d in (DATEN, GEDAECHTNIS, ABLAGE, STIMMEN):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def python_exe():
    """python.exe aus Watsons eigener Umgebung (für Werkzeuge, die ein Konsolen-Python brauchen)."""
    exe = Path(sys.executable)
    cand = exe.with_name("python.exe")
    return str(cand if cand.exists() else exe)


def mcp_vorbereiten():
    """Beim ersten Start einer installierten Version: Werkzeug-Liste aus der Vorlage anlegen."""
    if MCP_JSON.exists():
        return
    vorlage = PROGRAMM / "mcp-vorlage.json"
    if not vorlage.exists():
        return
    text = vorlage.read_text(encoding="utf-8")
    ersatz = {"${PYTHON}": python_exe(), "${PROGRAMM}": str(PROGRAMM), "${DATEN}": str(DATEN),
              "${ABLAGE}": str(ABLAGE), "${NODE}": shutil.which("node") or r"C:\Program Files\nodejs\node.exe"}
    for k, v in ersatz.items():
        text = text.replace(k, json.dumps(v)[1:-1])      # Backslashes JSON-gerecht
    MCP_JSON.write_text(text, encoding="utf-8")


def gedaechtnis_vorbereiten():
    """Neue Nutzer bekommen eine kurze Anleitung in ihren Gedächtnis-Ordner."""
    liesmich = GEDAECHTNIS / "LIES-MICH.md"
    if INSTALLIERT and not any(GEDAECHTNIS.glob("*.md")):
        liesmich.write_text(
            "# Watsons Gedächtnis-Ordner\n\n"
            "Alles, was in diesem Ordner als `.md`-Datei liegt, liest Watson als Grundwissen über dich.\n"
            "Du kannst hier z. B. eine Datei `ueber-mich.md` anlegen und hineinschreiben, wer du bist und was dir wichtig ist.\n"
            "Watson merkt sich außerdem selbst Dinge – die findest du in Watson unter „Gedächtnis“.\n",
            encoding="utf-8")
