"""
MCP-Werkzeuge online suchen – im offiziellen MCP-Verzeichnis (registry.modelcontextprotocol.io).

Ehrlich gesagt: Das Verzeichnis sammelt Werkzeuge von vielen Firmen und Privatleuten. Es prüft nicht, ob ein
Werkzeug gut oder sicher ist. Darum steckt Watson nie selbst etwas ein – das entscheidet immer der Nutzer,
und eingesteckte Werkzeuge fragen vor jeder Benutzung um Erlaubnis.
"""
import hashlib
import json
import re
import urllib.parse
import urllib.request

REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"


def _holen(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Watson-Assistent", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _text(s, n=400):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def _sicherer_name(name):
    teile = str(name).split("/")
    teil = teile[-1] or str(name)
    if teil.lower() in ("mcp", "server", "mcp-server", "main", "app") and len(teile) > 1:
        teil = teile[0].split(".")[-1] or teil          # z. B. com.githubcard/mcp -> githubcard
    return re.sub(r"[^A-Za-z0-9_-]", "-", teil).strip("-")[:30] or "werkzeug"


def _einstecken_plan(srv):
    """Wie man dieses Werkzeug in Watson einsteckt – oder ehrlich, warum (noch) nicht."""
    pakete = srv.get("packages") or []
    sid = str(srv.get("name", ""))      # eigener Schlüssel-Platz je Anbieter (kurzer Name + eindeutige Kennung)
    basis = "mcp_" + re.sub(r"[^a-z0-9]", "", _sicherer_name(sid).lower())[:16] + "_" + \
            hashlib.sha1(sid.encode()).hexdigest()[:5] + "_"
    npm = next((p for p in pakete if p.get("registryType") == "npm"
                and (p.get("transport") or {}).get("type", "stdio") == "stdio"), None)
    if npm:
        args = ["-y", f"{npm['identifier']}@{npm['version']}" if npm.get("version") else npm["identifier"]]
        offen = []
        for a in npm.get("packageArguments") or []:
            wert = a.get("value") or a.get("default")
            if a.get("type") == "named" and a.get("name"):
                if wert:
                    args += [a["name"], str(wert)]
                elif a.get("isRequired"):
                    offen.append(a["name"])
            elif wert:
                args.append(str(wert))
            elif a.get("isRequired"):
                offen.append(a.get("valueHint") or "Angabe")
        env, schluessel = {}, []
        for e in npm.get("environmentVariables") or []:
            name = str(e.get("name") or "")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,60}", name):
                continue
            if e.get("isSecret") or re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I):
                kid = basis + name.lower()
                env[name] = "${WATSON:" + kid + "}"         # Schlüssel kommt verschlüsselt aus dem Tresor
                schluessel.append({"id": kid, "env": name, "pflicht": bool(e.get("isRequired")),
                                   "info": _text(e.get("description"), 160)})
            elif e.get("value") or e.get("default"):
                env[name] = str(e.get("value") or e.get("default"))
            elif e.get("isRequired"):
                offen.append(name)
        if offen:
            return {"art": "npm", "einsteckbar": False, "paket": npm["identifier"],
                    "grund": "Braucht eigene Angaben (" + ", ".join(offen[:4]) + ") – bitte nach der Anleitung des Herstellers einrichten.",
                    "eintrag": {"command": "npx", "args": args, **({"env": env} if env else {})}, "schluessel": schluessel}
        return {"art": "npm", "einsteckbar": True, "paket": npm["identifier"], "eintrag": {"command": "npx", "args": args, **({"env": env} if env else {})},
                "schluessel": schluessel}
    if any(p.get("registryType") == "pypi" for p in pakete):
        return {"art": "python", "einsteckbar": False, "grund": "Python-Werkzeug – braucht das Programm „uv“, das auf diesem Computer fehlt."}
    if any(p.get("registryType") in ("oci", "docker") for p in pakete):
        return {"art": "docker", "einsteckbar": False, "grund": "Läuft nur mit Docker – das ist auf diesem Computer nicht eingerichtet."}
    for rem in srv.get("remotes") or []:
        url = str(rem.get("url") or "")
        if rem.get("type") != "streamable-http" or not url.startswith("https://") or "{" in url:
            continue
        kopf, schluessel, offen = {}, [], []
        for h in rem.get("headers") or []:
            name, wert = str(h.get("name") or ""), str(h.get("value") or "")
            if not re.fullmatch(r"[A-Za-z0-9-]{1,60}", name):
                continue
            platz = re.findall(r"\{(\w+)\}", wert)
            if h.get("isSecret") or platz:
                feld = platz[0] if platz else name
                kid = basis + re.sub(r"[^a-z0-9_]", "_", feld.lower())[:40]
                kopf[name] = re.sub(r"\{\w+\}", "${WATSON:" + kid + "}", wert) if platz else "${WATSON:" + kid + "}"
                schluessel.append({"id": kid, "env": feld, "pflicht": bool(h.get("isRequired")),
                                   "info": _text(h.get("description"), 160)})
            elif wert:
                kopf[name] = wert
            elif h.get("isRequired"):
                offen.append(name)
        if offen:
            continue
        return {"art": "online", "einsteckbar": True, "paket": url,
                "eintrag": {"url": url, **({"headers": kopf} if kopf else {})}, "schluessel": schluessel}
    if srv.get("remotes"):
        return {"art": "online", "einsteckbar": False,
                "grund": "Online-Dienst mit besonderer Verbindungsart – kann Watsons Steckdose noch nicht verbinden."}
    return {"art": "?", "einsteckbar": False, "grund": "Keine Angaben zum Einstecken."}


# Das Verzeichnis ist englisch – häufige deutsche Suchwörter übersetzen, wenn deutsch nichts gefunden wird
WOERTER = {"wetter": "weather", "kalender": "calendar", "termin": "calendar", "mail": "email", "e-mail": "email",
           "notiz": "notes", "notizen": "notes", "datei": "file", "dateien": "files", "ordner": "filesystem",
           "bibel": "bible", "karte": "maps", "karten": "maps", "übersetzen": "translate", "übersetzung": "translate",
           "musik": "music", "bild": "image", "bilder": "image", "foto": "photo", "suche": "search", "suchen": "search",
           "nachrichten": "news", "aufgabe": "task", "aufgaben": "todo", "einkauf": "shopping", "geld": "finance",
           "bank": "banking", "rechnung": "invoice", "tabelle": "spreadsheet", "dokument": "document",
           "browser": "browser", "webseite": "web", "internet": "web", "zeit": "time", "uhrzeit": "time",
           "erinnerung": "reminder", "video": "video", "sprache": "speech", "stimme": "voice", "zug": "train",
           "bahn": "train", "reise": "travel", "rezept": "recipe", "kochen": "recipe", "gesundheit": "health"}


def suchen(begriff, weiter=None, anzahl=30):
    begriff = _text(begriff, 80)
    if len(begriff) < 2:
        return {"error": "Bitte mindestens 2 Buchstaben eingeben."}
    r = _suchen(begriff, weiter, anzahl)
    englisch = WOERTER.get(begriff.lower())
    if not weiter and englisch and "treffer" in r and not r["treffer"]:
        r = _suchen(englisch, None, anzahl)
        if "treffer" in r:
            r["uebersetzt"] = f"Auf Deutsch gab es nichts – ich habe nach „{englisch}“ gesucht."
    return r


def _suchen(begriff, weiter, anzahl):
    q = {"search": begriff, "limit": max(1, min(int(anzahl), 50)), "version": "latest"}
    if weiter:
        q["cursor"] = str(weiter)[:200]
    try:
        d = _holen(REGISTRY + "?" + urllib.parse.urlencode(q))
    except Exception as e:
        return {"error": f"Das MCP-Verzeichnis ist gerade nicht erreichbar ({type(e).__name__}). Bitte später nochmal."}
    treffer = [t for t in (_aufbereiten(e) for e in d.get("servers") or []) if t]
    treffer.sort(key=lambda t: not t["einsteckbar"])          # was Watson einstecken kann, zuerst
    return {"treffer": treffer, "weiter": (d.get("metadata") or {}).get("nextCursor"), "begriff": begriff}


def _aufbereiten(eintrag):
    srv = eintrag.get("server") or {}
    meta = (eintrag.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
    if meta.get("status") not in (None, "active"):
        return None                                    # zurückgezogene/veraltete Werkzeuge nicht zeigen
    repo = (srv.get("repository") or {}).get("url") or ""
    web = srv.get("websiteUrl") or ""
    return {"id": srv.get("name", ""), "name": _sicherer_name(srv.get("name", "")),
            "titel": _text(srv.get("title") or srv.get("name"), 80),
            "beschreibung": _text(srv.get("description")), "version": _text(srv.get("version"), 20),
            "quelle": repo if repo.startswith("https://") else "", "webseite": web if web.startswith("https://") else "",
            "datum": (meta.get("updatedAt") or meta.get("publishedAt") or "")[:10],
            **_einstecken_plan(srv)}


def holen(server_id):
    """Ein Werkzeug frisch aus dem Verzeichnis holen (beim Einstecken nie den Angaben der Oberfläche trauen)."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+", str(server_id or "")) or len(server_id) > 200:
        return None
    try:
        return _aufbereiten(_holen(f"{REGISTRY}/{urllib.parse.quote(server_id, safe='')}/versions/latest"))
    except Exception:
        return None


def einstecken(server_id, mcp_json, cfg):
    """Ein Werkzeug aus dem Verzeichnis in mcp.json eintragen. Immer mit Nachfrage vor jeder Benutzung (nicht „trusted“).
    Legt leere Schlüssel-Plätze an, die der Nutzer im Schlüsseltresor selbst ausfüllt."""
    treffer = holen(server_id)
    if not treffer:
        return {"error": "Dieses Werkzeug wurde im MCP-Verzeichnis nicht (mehr) gefunden."}
    if not treffer.get("einsteckbar") or not treffer.get("eintrag"):
        return {"error": treffer.get("grund") or "Dieses Werkzeug kann Watson nicht automatisch einstecken."}
    eintrag = treffer["eintrag"]
    gueltig = (eintrag.get("command") == "npx" and all(isinstance(a, str) for a in eintrag.get("args", []))) or \
              (str(eintrag.get("url", "")).startswith("https://") and "command" not in eintrag)
    if not gueltig:
        return {"error": "Unerwarteter Eintrag – aus Sicherheitsgründen nicht eingesteckt."}
    try:
        daten = json.loads(mcp_json.read_text(encoding="utf-8")) if mcp_json.exists() else {}
    except ValueError as e:
        return {"error": f"mcp.json hat einen Schreibfehler: {e}"}
    server = daten.setdefault("mcpServers", {})
    paket = treffer.get("paket") or ""
    for n, s in server.items():
        if s.get("quelle") == treffer.get("id") or (paket and s.get("url") == paket) or \
                any(str(a) == paket or str(a).startswith(paket + "@") for a in s.get("args", [])):
            return {"error": f"Dieses Werkzeug steckt schon drin (als „{n}“)."}
    name, i = treffer.get("name") or "werkzeug", 2
    while name in server:
        name, i = f"{treffer.get('name')}-{i}", i + 1
    server[name] = {**eintrag, "trusted": False, "quelle": treffer.get("id", ""),
                    "hinweis": "Aus dem MCP-Verzeichnis eingesteckt – fragt vor jeder Benutzung."}
    mcp_json.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    # Schlüssel-Plätze im Tresor-Bereich anlegen (leer – der Nutzer trägt den Schlüssel selbst ein)
    neu = []
    vorhanden = {s.get("id") for s in cfg.get("schluessel", [])}
    for k in treffer.get("schluessel") or []:
        if k["id"] not in vorhanden:
            cfg.setdefault("schluessel", []).append({"id": k["id"], "name": f"{name}: {k['env']}", "geaendert": ""})
            neu.append(k)
    return {"ok": True, "name": name, "schluessel": treffer.get("schluessel") or [], "neue_plaetze": bool(neu)}
