"""
Verbindung zwischen Watson Studio und n8n (Abläufe / Automatisierungen).

n8n läuft nativ für ARM in einem kleinen Linux (Ubuntu in WSL, in Windows eingebaut).
Watson startet es im Hintergrund mit, zeigt es in einem eigenen Fenster und kann
Abläufe über "Webhooks" (eine Art Klingel-Adresse pro Ablauf) auslösen.
Erreichbar nur von diesem Laptop: http://127.0.0.1:5678
"""
import json
import shlex
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
    "N8N_WEBHOOK_URL": f"http://localhost:{PORT}/",   # neuer Name ab n8n 2.48 (der alte bleibt für ältere Versionen)
    "N8N_SECURE_COOKIE": "false",
    "N8N_USER_MANAGEMENT_JWT_DURATION_HOURS": "8760",   # Anmeldung 1 Jahr gültig (Wunsch des Besitzers, 20.11.2026; n8n nur am Laptop erreichbar)
    "N8N_DIAGNOSTICS_ENABLED": "false",           # keine Nutzungsdaten an n8n senden
    "N8N_PERSONALIZATION_ENABLED": "false",
    "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
    "N8N_HIRING_BANNER_ENABLED": "false",
    "GENERIC_TIMEZONE": "Europe/Berlin",
    "TZ": "Europe/Berlin",
    "N8N_DEFAULT_LOCALE": "de",
}

# ---- Docker-Betrieb (seit 20.11.2026): n8n läuft als offizielle „Kiste“ im Docker des Ubuntu ----
# Gibt es die Marker-Datei, nimmt Watson Docker; sonst die alte Art (n8n direkt mit Node) als Rückweg.
DOCKER_MARKER = "/opt/watson-n8n/docker"
N8N_VERSION = "2.48.7"
IMAGE = f"n8nio/n8n:{N8N_VERSION}"
RUNNER_IMAGE = f"n8nio/runners:{N8N_VERSION}"   # führt Code-Schritte aus (JavaScript und Python)
CONTAINER = "watson-n8n"
RUNNER_CONTAINER = "watson-n8n-runners"
TOKEN_FILE = "/opt/watson-n8n/runner_token"      # Geheimnis zwischen n8n und Runner, bleibt im Linux
DOCKER_ENV = {k: v for k, v in ENV.items() if k not in ("PATH", "N8N_USER_FOLDER")}
DOCKER_ENV.update({"N8N_RUNNERS_ENABLED": "true", "N8N_RUNNERS_MODE": "external",
                   "N8N_RUNNERS_BROKER_LISTEN_ADDRESS": "127.0.0.1"})

_proc = None
_installed = None
_modus = None      # "docker" | "nativ" | ""


def _wsl(*cmd):
    env_args = [f"{k}={v}" for k, v in ENV.items()]
    return ["wsl.exe", "-d", DISTRO, "-u", "root", "--exec", "/usr/bin/env", *env_args, *cmd]


def _bash(script):
    return ["wsl.exe", "-d", DISTRO, "-u", "root", "--exec", "bash", "-c", script]


def modus():
    global _modus
    if _modus is None:
        try:
            r = subprocess.run(_bash(f"if test -f {DOCKER_MARKER} && command -v docker >/dev/null; then echo docker; "
                                     f"elif test -f {N8N_JS}; then echo nativ; fi"),
                               capture_output=True, text=True, timeout=60, creationflags=NOWIN)
            _modus = r.stdout.strip()
        except Exception:
            _modus = ""
    return _modus


def installed():
    global _installed
    if _installed is None:
        _installed = modus() in ("docker", "nativ")
    return _installed


def _docker_start_skript():
    """Ein bash-Skript: Runner im Hintergrund, n8n im Vordergrund (hält den WSL-Prozess offen wie bisher)."""
    e = " ".join(f"-e {shlex.quote(f'{k}={v}')}" for k, v in DOCKER_ENV.items())
    return ("for i in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 1; done; "   # nach dem Hochfahren auf Docker warten
            f"docker rm -f {CONTAINER} {RUNNER_CONTAINER} >/dev/null 2>&1; "
            f"T=$(cat {TOKEN_FILE}); "
            f"docker run -d --rm --name {RUNNER_CONTAINER} --network host "
            f"-e N8N_RUNNERS_TASK_BROKER_URI=http://127.0.0.1:5679 -e N8N_RUNNERS_AUTH_TOKEN=\"$T\" {RUNNER_IMAGE} >/dev/null; "
            f"docker run --rm --name {CONTAINER} --network host -v {DATA_DIR}/.n8n:/home/node/.n8n "
            f"-e N8N_RUNNERS_AUTH_TOKEN=\"$T\" {e} {IMAGE} start; rc=$?; "
            f"docker stop -t 5 {RUNNER_CONTAINER} >/dev/null 2>&1; exit $rc")


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
    befehl = _bash(_docker_start_skript()) if modus() == "docker" else _wsl(NODE, N8N_JS, "start")
    _proc = subprocess.Popen(befehl, stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, creationflags=NOWIN)
    t = time.time()
    while time.time() - t < wait:
        if bereit():          # erst fertig, wenn die Datenbank bereit ist (nicht schon beim ersten Lebenszeichen)
            return True
        if _proc.poll() is not None:
            return False
        time.sleep(2)
    return bereit()


def bereit():
    """n8n läuft UND hat seine Datenbank fertig (wichtig nach Updates, wenn n8n sie umbaut)."""
    try:
        with urllib.request.urlopen(BASE + "/healthz/readiness", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def stop():
    """n8n beenden (nur wenn Watson es gestartet hat)."""
    global _proc
    if _proc is not None:
        _kill()
        _proc = None


def _kill():
    if modus() == "docker":
        subprocess.run(_bash(f"docker stop -t 15 {CONTAINER} >/dev/null 2>&1; docker stop -t 5 {RUNNER_CONTAINER} >/dev/null 2>&1; true"),
                       capture_output=True, timeout=60, creationflags=NOWIN)
        return
    # n8n benennt seine Prozesse um ("n8n start", "n8n task-runner") -> danach suchen
    subprocess.run(_bash("pkill -f '^n8n (start|task-runner)'; sleep 4; pkill -9 -f '^n8n (start|task-runner)'; true"),
                   capture_output=True, timeout=40, creationflags=NOWIN)


def cli(*args, timeout=180):
    """n8n-Befehl im Linux ausführen (z. B. Ablauf importieren)."""
    if modus() == "docker":
        a = " ".join(shlex.quote(x) for x in args)
        befehl = _bash(f"if docker ps -q -f name=^{CONTAINER}$ | grep -q .; then docker exec -u node {CONTAINER} n8n {a}; "
                       f"else docker run --rm --network none -v {DATA_DIR}/.n8n:/home/node/.n8n {IMAGE} {a}; fi")
    else:
        befehl = _wsl(NODE, N8N_JS, *args)
    r = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=NOWIN)
    return r.returncode, (r.stdout + r.stderr)[-3000:]


AUSTAUSCH = "austausch-watson"   # Ordner in den n8n-Daten, den die Kiste und Windows beide erreichen


def _ueber_austausch(befehl_args, win_ordner: Path, richtung):
    """Docker-Kiste sieht Windows nicht: Dateien über einen Ordner in den n8n-Daten hin- bzw. zurückkopieren."""
    innen, aussen, win = f"/home/node/.n8n/{AUSTAUSCH}", f"{DATA_DIR}/.n8n/{AUSTAUSCH}", shlex.quote(win_to_wsl(win_ordner))
    vor = f"rm -rf {aussen} && mkdir -p {aussen} && chown 1000:1000 {aussen}"
    if richtung == "rein":
        vor += f" && cp -r {win}/. {aussen}/ && chown -R 1000:1000 {aussen}"
    subprocess.run(_bash(vor), capture_output=True, timeout=120, creationflags=NOWIN)
    code, out = cli(*[x.replace("{ORDNER}", innen) for x in befehl_args])
    nach = (f"mkdir -p {win} && cp -r {aussen}/. {win}/; " if richtung == "raus" else "") + f"rm -rf {aussen}"
    subprocess.run(_bash(nach), capture_output=True, timeout=120, creationflags=NOWIN)
    return code, out


def export_workflows(folder: Path):
    """Alle Abläufe (ohne Zugangsdaten) als einzelne JSON-Dateien in einen Windows-Ordner exportieren."""
    if not installed():
        raise RuntimeError("n8n ist nicht installiert")
    if modus() == "docker":
        Path(folder).mkdir(parents=True, exist_ok=True)
        code, out = _ueber_austausch(["export:workflow", "--all", "--separate", "--output={ORDNER}/"], folder, "raus")
    else:
        code, out = cli("export:workflow", "--all", "--separate", "--output=" + win_to_wsl(folder) + "/")
    if code != 0 and "No workflows found" not in out:
        raise RuntimeError(out[-300:])
    return len(list(Path(folder).glob("*.json")))


def import_workflows(folder: Path):
    if modus() == "docker":
        code, out = _ueber_austausch(["import:workflow", "--separate", "--input={ORDNER}"], folder, "rein")
    else:
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
