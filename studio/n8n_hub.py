"""
Verbindung zwischen Watson Studio und n8n (Abläufe / Automatisierungen).

n8n läuft nativ für ARM in einem kleinen Linux (Ubuntu in WSL, in Windows eingebaut).
Watson startet es im Hintergrund mit, zeigt es in einem eigenen Fenster und kann
Abläufe über "Webhooks" (eine Art Klingel-Adresse pro Ablauf) auslösen.
Erreichbar nur von diesem Laptop: http://127.0.0.1:5678
"""
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

DISTRO = "Ubuntu-24.04"
NODE = "/opt/node24/bin/node"
N8N_JS = "/opt/watson-n8n/node_modules/n8n/bin/n8n"
DATA_DIR = "/opt/watson-n8n/daten"
PORT = 5678
BASE = f"http://127.0.0.1:{PORT}"
LOG = Path(__file__).resolve().parent.parent / "n8n-linux" / "n8n.log"
NOWIN = 0x08000000   # kein schwarzes Fenster

ENV = {
    "PATH": "/opt/node24/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "N8N_USER_FOLDER": DATA_DIR,
    "N8N_PORT": str(PORT),
    "N8N_LISTEN_ADDRESS": "0.0.0.0",              # im Linux; von außen nur über Windows-localhost erreichbar
    "N8N_HOST": "localhost",
    "WEBHOOK_URL": f"http://localhost:{PORT}/",
    "N8N_SECURE_COOKIE": "false",
    "N8N_DIAGNOSTICS_ENABLED": "false",           # keine Nutzungsdaten an n8n senden
    "N8N_PERSONALIZATION_ENABLED": "false",
    "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
    "N8N_HIRING_BANNER_ENABLED": "false",
    "GENERIC_TIMEZONE": "Europe/Berlin",
    "TZ": "Europe/Berlin",
    "N8N_DEFAULT_LOCALE": "de",
}

_proc = None
_installed = None


def _wsl(*cmd):
    env_args = [f"{k}={v}" for k, v in ENV.items()]
    return ["wsl.exe", "-d", DISTRO, "-u", "root", "--exec", "/usr/bin/env", *env_args, *cmd]


def installed():
    global _installed
    if _installed is None:
        try:
            r = subprocess.run(["wsl.exe", "-d", DISTRO, "-u", "root", "--exec", "test", "-f", N8N_JS],
                               capture_output=True, timeout=60, creationflags=NOWIN)
            _installed = r.returncode == 0
        except Exception:
            _installed = False
    return _installed


def running():
    try:
        with urllib.request.urlopen(BASE + "/healthz", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start(wait=120):
    """n8n im Linux im Hintergrund starten. Gibt True zurück, wenn es läuft."""
    global _proc
    if running():
        return True
    if not installed():
        return False
    LOG.parent.mkdir(exist_ok=True)
    log = open(LOG, "a", encoding="utf-8")
    _proc = subprocess.Popen(_wsl(NODE, N8N_JS, "start"), stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, creationflags=NOWIN)
    t = time.time()
    while time.time() - t < wait:
        if running():
            return True
        if _proc.poll() is not None:
            return False
        time.sleep(2)
    return running()


def stop():
    """n8n beenden (nur wenn Watson es gestartet hat)."""
    global _proc
    if _proc is not None:
        _kill()
        _proc = None


def _kill():
    # n8n benennt seine Prozesse um ("n8n start", "n8n task-runner") -> danach suchen
    subprocess.run(["wsl.exe", "-d", DISTRO, "-u", "root", "--exec", "bash", "-c",
                    "pkill -f '^n8n (start|task-runner)'; sleep 4; pkill -9 -f '^n8n (start|task-runner)'; true"],
                   capture_output=True, timeout=40, creationflags=NOWIN)


def cli(*args, timeout=180):
    """n8n-Befehl im Linux ausführen (z. B. Ablauf importieren)."""
    r = subprocess.run(_wsl(NODE, N8N_JS, *args), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=NOWIN)
    return r.returncode, (r.stdout + r.stderr)[-3000:]


def export_workflows(folder: Path):
    """Alle Abläufe (ohne Zugangsdaten) als einzelne JSON-Dateien in einen Windows-Ordner exportieren."""
    if not installed():
        raise RuntimeError("n8n ist nicht installiert")
    code, out = cli("export:workflow", "--all", "--separate", "--output=" + win_to_wsl(folder) + "/")
    if code != 0 and "No workflows found" not in out:
        raise RuntimeError(out[-300:])
    return len(list(Path(folder).glob("*.json")))


def import_workflows(folder: Path):
    code, out = cli("import:workflow", "--separate", "--input=" + win_to_wsl(folder))
    return code == 0, out[-500:]


def win_to_wsl(path: Path):
    p = str(path.resolve()).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def trigger(path, data=None, timeout=120):
    """Einen Ablauf über seine Webhook-Adresse starten und die Antwort zurückgeben."""
    path = path.strip("/").replace("webhook/", "")
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/webhook/{path}", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")[:6000]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (f"Den Ablauf „{path}“ gibt es nicht oder er ist nicht aktiv. "
                    "In n8n muss der Ablauf einen Webhook-Start haben und aktiviert sein.")
        return f"n8n meldet Fehler {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
    except urllib.error.URLError:
        return "n8n läuft gerade nicht."


TOOL = {"type": "function", "function": {
    "name": "watson__ablauf_starten",
    "description": "Startet einen n8n-Ablauf (Automatisierung) über seine Webhook-Adresse und gibt das Ergebnis zurück. "
                   "Bekannte Abläufe stehen im System-Text unter 'Deine Abläufe'.",
    "parameters": {"type": "object", "properties": {
        "pfad": {"type": "string", "description": "Webhook-Pfad des Ablaufs, z. B. 'watson-test'"},
        "daten": {"type": "object", "description": "Optionale Daten, die der Ablauf bekommt"}},
        "required": ["pfad"]}}}
