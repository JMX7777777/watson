"""ChatGPT-Plan: Watson denkt mit dem ChatGPT-Abo (Plus/Pro) des Besitzers – offiziell erlaubt über
„Sign in with ChatGPT“ von OpenAI (für Open-Source- und lokal laufende Programme, ohne Antrag; seit 29.09.2026).
Doku: https://developers.openai.com/siwc/quickstart

So einfach wie möglich für den Nutzer:  Knopf „Mit ChatGPT anmelden“ -> Browser -> „Erlauben“ -> fertig.

Technik (genau nach der OpenAI-Anleitung):
  - OAuth 2.0 mit PKCE (S256), ohne Geheimnis. Beim ersten Mal registriert sich Watson selbst
    (client_id=dynamic_agent_client); OpenAI gibt eine eigene client_id zurück, die Watson sich merkt.
  - Rückruf an http://127.0.0.1:1455/auth/callback (nur der Port darf abweichen, nie „localhost“).
  - Der Erneuerungs-Schlüssel (30 Tage, wird bei jeder Erneuerung ersetzt) liegt verschlüsselt im Windows-Tresor.
    Der Zugangs-Schlüssel (1 Stunde) bleibt nur im Arbeitsspeicher.
  - Denken über POST https://api.openai.com/v1/responses mit store=false und stream=true.
  - Ist der Plan aufgebraucht oder nicht berechtigt, bricht die Anfrage ab (OpenAI rechnet nie still anders ab).
    Watson springt dann von sich aus auf seine Gratis-Gehirne zurück und sagt das.
Watson bekommt dabei KEINEN Zugriff auf die ChatGPT-Gespräche oder das Konto des Nutzers.
"""
import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

import tresor

AUTH_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
OIDC_URL = "https://auth.openai.com/.well-known/openid-configuration"
API = "https://api.openai.com/v1"
RESOURCE = "https://api.openai.com/v1"      # feste Kennung der OpenAI-Schnittstelle (auch wenn API umgeleitet wird)
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PORTS = (1455, 1456, 1457, 1458)
NAME = "Watson"
PREFIX = "chatgpt/"                    # Gehirn-Kennung in Watson: chatgpt/<modell>
NUTZUNG_URL = "https://chatgpt.com/settings/usage"
TRESOR_TEILE = 8                       # Erneuerungs-Schlüssel ggf. in Stücke geteilt (Windows-Tresor fasst wenig)
TEIL_LAENGE = 1000

H = {}                                 # Helfer aus watson_studio: load_config, save_config, fehler_melden
_lock = threading.Lock()
_zugang = {"token": "", "bis": 0.0}    # Zugangs-Schlüssel nur im Arbeitsspeicher
_anmeldung = {"laeuft": False, "status": "", "fehler": ""}


def init(**helfer):
    H.update(helfer)


def _cfg():
    return H["load_config"]() if "load_config" in H else {}


def _cfg_setzen(**werte):
    if "load_config" not in H:
        return
    c = H["load_config"]()
    for k, v in werte.items():
        if v is None:
            c.pop(k, None)
        else:
            c[k] = v
    H["save_config"](c)


# ---------------- Tresor (Erneuerungs-Schlüssel, ggf. in Stücken) ----------------
def _refresh_lesen():
    teile = []
    for i in range(TRESOR_TEILE):
        t = tresor.lesen(f"chatgpt_refresh_{i}")
        if not t:
            break
        teile.append(t)
    return "".join(teile)


def _refresh_speichern(wert):
    wert = wert or ""
    stuecke = [wert[i:i + TEIL_LAENGE] for i in range(0, len(wert), TEIL_LAENGE)]
    if len(stuecke) > TRESOR_TEILE:
        raise RuntimeError("Der ChatGPT-Schlüssel ist zu lang für den Tresor.")
    for i in range(TRESOR_TEILE):
        if i < len(stuecke):
            tresor.speichern(f"chatgpt_refresh_{i}", stuecke[i])
        else:
            tresor.loeschen(f"chatgpt_refresh_{i}")


# ---------------- Zustand ----------------
def angemeldet():
    return bool(_cfg().get("chatgpt_client_id")) and bool(_refresh_lesen())


def aktiv(cfg=None):
    """Soll Watson gerade mit dem ChatGPT-Plan denken? (angemeldet, eingeschaltet, Plan berechtigt)"""
    cfg = cfg or _cfg()
    return bool(cfg.get("chatgpt_an")) and bool(cfg.get("chatgpt_client_id")) and \
        cfg.get("chatgpt_status") not in ("kein_plan", "neu_anmelden") and bool(_refresh_lesen())


def modell_id(cfg=None):
    cfg = cfg or _cfg()
    return PREFIX + (cfg.get("chatgpt_modell") or "")


def ist_chatgpt(model):
    return str(model or "").startswith(PREFIX)


def status():
    cfg = _cfg()
    pause = cfg.get("chatgpt_pause_bis", 0) or 0
    return {"angemeldet": angemeldet(), "an": bool(cfg.get("chatgpt_an")), "modell": cfg.get("chatgpt_modell", ""),
            "modelle": cfg.get("chatgpt_modelle", []), "email": cfg.get("chatgpt_email", ""),
            "zustand": cfg.get("chatgpt_status", ""), "willkommen_gezeigt": bool(cfg.get("chatgpt_willkommen")),
            "pause_bis": time.strftime("%H:%M", time.localtime(pause)) if pause > time.time() else "",
            "anmeldung": dict(_anmeldung), "nutzung_url": NUTZUNG_URL}


# ---------------- Anmelden (OAuth + PKCE, Rückruf auf 127.0.0.1) ----------------
def _b64url(daten):
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode("ascii")


def _host_id():
    cfg = _cfg()
    hid = cfg.get("chatgpt_host_id")
    if not hid:
        hid = "urn:uuid:" + str(uuid.uuid4())       # stabil pro Computer, ohne persönliche Angaben
        _cfg_setzen(chatgpt_host_id=hid)
    return hid


SEITE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Watson</title>
<style>body{{font-family:Segoe UI,system-ui,sans-serif;background:#16181c;color:#e9e9e6;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0}}div{{text-align:center;max-width:460px;padding:24px}}h1{{font-size:28px}}
p{{color:#9ea1a6;font-size:17px;line-height:1.5}}</style></head><body><div><h1>{titel}</h1><p>{text}</p></div></body></html>"""


def anmelden_starten():
    """Startet die Anmeldung im Hintergrund und öffnet den Browser. Fortschritt über status()['anmeldung']."""
    if _anmeldung["laeuft"]:
        return {"ok": True, "laeuft": True}
    _anmeldung.update(laeuft=True, status="Browser wird geöffnet …", fehler="")
    threading.Thread(target=_anmelden, daemon=True).start()
    return {"ok": True}


def _anmelden(wartezeit=300):
    server = None
    try:
        verifier = _b64url(secrets.token_bytes(48))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state, nonce = _b64url(secrets.token_bytes(24)), _b64url(secrets.token_bytes(24))
        ergebnis = {}
        fertig = threading.Event()

        class Rueckruf(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                if url.path != "/auth/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
                ergebnis.update(q)
                ok = q.get("state") == state and q.get("code") and not q.get("error")
                titel, text = (("✅ Geschafft!", "Watson ist jetzt mit deinem ChatGPT-Plan verbunden. "
                                "Du kannst dieses Fenster schließen und zu Watson zurückgehen.") if ok else
                               ("Abgebrochen", "Es hat nicht geklappt oder du hast nicht erlaubt. Du kannst dieses "
                                "Fenster schließen. In Watson kannst du es jederzeit nochmal versuchen."))
                body = SEITE.format(titel=titel, text=text).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                fertig.set()

        port = None
        for p in PORTS:                       # Port 1455 bevorzugt; nur der Port darf abweichen
            try:
                server = http.server.HTTPServer(("127.0.0.1", p), Rueckruf)
                port = p
                break
            except OSError:
                continue
        if not server:
            raise RuntimeError("Kein freier Anschluss für die Anmeldung (Ports 1455–1458 belegt).")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        redirect = f"http://127.0.0.1:{port}/auth/callback"
        cfg = _cfg()
        client_id = cfg.get("chatgpt_client_id") or "dynamic_agent_client"
        params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect, "scope": SCOPES,
                  "resource": RESOURCE, "state": state, "nonce": nonce, "code_challenge": challenge,
                  "code_challenge_method": "S256", "ext_agent_host_id": _host_id()}
        if client_id == "dynamic_agent_client":
            params["agent_name_hint"] = NAME          # nur bei der ersten Registrierung
        webbrowser.open(AUTH_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))
        _anmeldung["status"] = "Bitte im Browser bei ChatGPT anmelden und „Erlauben“ drücken …"
        if not fertig.wait(wartezeit):
            raise RuntimeError("Die Anmeldung hat zu lange gedauert (5 Minuten). Bitte nochmal versuchen.")
        if ergebnis.get("error") == "access_denied":
            raise RuntimeError("Du hast im Browser nicht erlaubt. Kein Problem – Watson bleibt bei den Gratis-Gehirnen.")
        if ergebnis.get("error"):
            raise RuntimeError(f"ChatGPT meldet: {ergebnis.get('error_description') or ergebnis['error']}")
        if ergebnis.get("state") != state:
            raise RuntimeError("Sicherheitsprüfung fehlgeschlagen (falscher Rückruf). Bitte nochmal versuchen.")
        neue_id = ergebnis.get("client_id")
        if client_id != "dynamic_agent_client" and neue_id and neue_id != client_id:
            raise RuntimeError("Sicherheitsprüfung fehlgeschlagen (fremde Kennung). Bitte nochmal versuchen.")
        client_id = neue_id or (client_id if client_id != "dynamic_agent_client" else "")
        if not client_id:
            raise RuntimeError("ChatGPT hat keine Kennung für Watson zurückgegeben. Bitte nochmal versuchen.")
        if "chatgpt.tokens.use.direct" not in (ergebnis.get("scope") or SCOPES):
            raise RuntimeError("Die Erlaubnis für die Nutzung deines ChatGPT-Plans wurde nicht erteilt.")
        _anmeldung["status"] = "Verbinde …"
        antwort = _token_anfrage({"grant_type": "authorization_code", "client_id": client_id,
                                  "code": ergebnis["code"], "code_verifier": verifier, "redirect_uri": redirect,
                                  "resource": RESOURCE})
        if "chatgpt.tokens.use.direct" not in (antwort.get("scope") or ""):
            raise RuntimeError("Die Erlaubnis für die Nutzung deines ChatGPT-Plans fehlt. Bitte nochmal anmelden "
                               "und alles erlauben.")
        with _lock:
            _refresh_speichern(antwort.get("refresh_token", ""))
            _zugang.update(token=antwort.get("access_token", ""), bis=time.time() + int(antwort.get("expires_in", 3600)) - 120)
        email = _email_aus(antwort.get("id_token", ""))
        _cfg_setzen(chatgpt_client_id=client_id, chatgpt_email=email, chatgpt_an=True, chatgpt_status="ok",
                    chatgpt_pause_bis=None)
        _anmeldung["status"] = "Suche deine ChatGPT-Gehirne …"
        try:
            modelle_laden()
        except PlanFehler as e:
            if e.art == "kein_plan":
                raise RuntimeError("Angemeldet – aber dein ChatGPT-Konto hat keinen Plan, der das erlaubt (nötig: "
                                   "ChatGPT Plus oder Pro). Watson bleibt bei den Gratis-Gehirnen.")
        except Exception:
            pass                                     # Liste kommt beim nächsten Mal
        _anmeldung.update(status="fertig", fehler="")
    except Exception as e:
        _anmeldung.update(status="fehler", fehler=str(e)[:300])
        if "fehler_melden" in H and not isinstance(e, RuntimeError):
            H["fehler_melden"]("ChatGPT/Anmelden", e)
    finally:
        _anmeldung["laeuft"] = False
        if server:
            threading.Thread(target=server.shutdown, daemon=True).start()


def _email_aus(id_token):
    """Nur zum Anzeigen („angemeldet als …“) – die Unterschrift prüft OpenAI beim Benutzen selbst."""
    try:
        teil = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(teil + "=" * (-len(teil) % 4))).get("email", "")
    except Exception:
        return ""


def _token_anfrage(felder):
    req = urllib.request.Request(TOKEN_URL, urllib.parse.urlencode(felder).encode("ascii"),
                                 {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8", "replace"))
        except ValueError:
            d = {}
        raise TokenFehler(str(d.get("error") or e.code), str(d.get("error_description") or ""))
    except urllib.error.URLError:
        raise RuntimeError("Keine Verbindung zu ChatGPT (Internet?).")


class TokenFehler(RuntimeError):
    def __init__(self, code, text=""):
        super().__init__(f"{code}: {text}".strip(": "))
        self.code = code


ENDGUELTIG = {"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
              "refresh_token_invalidated", "refresh_token_reused"}


def zugang():
    """Gültiger Zugangs-Schlüssel – erneuert ihn bei Bedarf (nacheinander, nie gleichzeitig)."""
    with _lock:
        if _zugang["token"] and time.time() < _zugang["bis"]:
            return _zugang["token"]
        cfg = _cfg()
        rt, cid = _refresh_lesen(), cfg.get("chatgpt_client_id")
        if not (rt and cid):
            raise PlanFehler("neu_anmelden", "Watson ist nicht (mehr) mit ChatGPT verbunden.")
        try:
            a = _token_anfrage({"grant_type": "refresh_token", "client_id": cid, "refresh_token": rt, "resource": RESOURCE})
        except TokenFehler as e:
            if e.code in ENDGUELTIG:
                _refresh_speichern("")
                _zugang.update(token="", bis=0)
                _cfg_setzen(chatgpt_status="neu_anmelden")
                raise PlanFehler("neu_anmelden", "Die ChatGPT-Verbindung ist abgelaufen. Bitte einmal neu anmelden.")
            raise PlanFehler("fehler", f"ChatGPT-Anmeldung: {e}")
        if a.get("refresh_token"):
            _refresh_speichern(a["refresh_token"])          # jede Erneuerung gibt einen neuen – immer den neuesten
        _zugang.update(token=a.get("access_token", ""), bis=time.time() + int(a.get("expires_in", 3600)) - 120)
        return _zugang["token"]


def abmelden():
    """Erneuerungs-Schlüssel bei OpenAI zurückziehen und alles löschen."""
    rt, cid = _refresh_lesen(), _cfg().get("chatgpt_client_id")
    if rt and cid:
        try:
            with urllib.request.urlopen(OIDC_URL, timeout=15) as r:
                ende = json.loads(r.read().decode("utf-8")).get("revocation_endpoint")
            if ende:
                req = urllib.request.Request(ende, urllib.parse.urlencode(
                    {"token": rt, "token_type_hint": "refresh_token", "client_id": cid}).encode("ascii"),
                    {"Content-Type": "application/x-www-form-urlencoded"})
                urllib.request.urlopen(req, timeout=15).close()
        except Exception:
            pass                                             # lokal trotzdem löschen
    with _lock:
        _refresh_speichern("")
        _zugang.update(token="", bis=0)
    _cfg_setzen(chatgpt_an=False, chatgpt_status=None, chatgpt_email=None, chatgpt_pause_bis=None)
    return status()


# ---------------- Gehirne (Modelle) ----------------
def modelle_laden():
    req = urllib.request.Request(API + "/models", headers={"Authorization": "Bearer " + zugang()})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            daten = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        _http_fehler(e)
    # Die Liste kommt je nach Stand als „models“ oder „data“, mit „slug“ oder „id“ (so auch in Sentient, 2026);
    # OpenAI gibt eine Rangfolge vor („priority“, kleiner = zuerst), sonst gilt die Reihenfolge der Liste.
    roh = [m for m in (daten.get("models") or daten.get("data") or []) if isinstance(m, dict)]
    eintraege = [(m.get("priority") if isinstance(m.get("priority"), (int, float)) else 1e9, i, m.get("slug") or m.get("id"))
                 for i, m in enumerate(roh) if m.get("visibility", "list") == "list" and (m.get("slug") or m.get("id"))]
    liste = [s for _, _, s in sorted(eintraege)]
    cfg = _cfg()
    gewaehlt = cfg.get("chatgpt_modell") if cfg.get("chatgpt_modell") in liste else (liste[0] if liste else "")
    _cfg_setzen(chatgpt_modelle=liste, chatgpt_modell=gewaehlt)
    return liste


# ---------------- Denken (Responses API) ----------------
class PlanFehler(RuntimeError):
    """Anfrage über den ChatGPT-Plan ging nicht – Watson soll auf ein Gratis-Gehirn ausweichen."""
    def __init__(self, art, text):
        super().__init__("ChatGPT-Plan: " + text)
        self.art = art


def _http_fehler(e):
    try:
        d = json.loads(e.read().decode("utf-8", "replace"))
    except ValueError:
        d = {}
    err = d.get("error") if isinstance(d.get("error"), dict) else {}
    code = err.get("code") or ""
    _fehler_code(code, e.code, err.get("message") or d.get("detail") or "")


def _fehler_code(code, http=0, text=""):
    if code == "subscription_sharing_usage_limit_exceeded":
        _cfg_setzen(chatgpt_pause_bis=time.time() + 30 * 60, chatgpt_status="grenze")
        raise PlanFehler("grenze", "Nutzungsgrenze deines ChatGPT-Plans erreicht.")
    if code == "subscription_sharing_user_not_eligible":
        _cfg_setzen(chatgpt_status="kein_plan")
        raise PlanFehler("kein_plan", "Dein ChatGPT-Konto hat keinen Plan, der das erlaubt (nötig: Plus oder Pro).")
    if code == "subscription_sharing_invalid_user" or http == 401:
        _zugang.update(token="", bis=0)
        raise PlanFehler("anmeldung", "ChatGPT hat die Anmeldung nicht angenommen.")
    if code in ("subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable") or http == 503:
        _cfg_setzen(chatgpt_pause_bis=time.time() + 5 * 60)
        raise PlanFehler("pause", "ChatGPT ist gerade nicht erreichbar.")
    if code == "subscription_sharing_unsupported_capability":
        raise PlanFehler("kann_nicht", f"Diese Anfrage geht über den ChatGPT-Plan nicht ({text[:120]}).")
    raise PlanFehler("fehler", f"Fehler {http or ''} {code} {text[:160]}".strip())


def bereit(cfg=None):
    """Darf Watson jetzt den ChatGPT-Plan fragen? (aktiv und nicht in einer Pause wegen Grenze/Störung)"""
    cfg = cfg or _cfg()
    return aktiv(cfg) and (cfg.get("chatgpt_pause_bis") or 0) < time.time() and bool(cfg.get("chatgpt_modell"))


def _text(inhalt):
    if isinstance(inhalt, str):
        return inhalt
    if isinstance(inhalt, list):                 # Chat-Format mit Teilen -> nur Text übernehmen
        return "\n".join(t.get("text", "") for t in inhalt if isinstance(t, dict) and t.get("type") == "text")
    return str(inhalt or "")


def umwandeln(messages, tools=None):
    """Watsons Gesprächsformat (wie OpenRouter/Chat-Completions) -> Responses-API-Format."""
    anweisungen, eingabe = [], []
    for m in messages:
        rolle = m.get("role")
        if rolle == "system":
            anweisungen.append(_text(m.get("content")))      # System-Einträge sind dort nicht erlaubt -> instructions
        elif rolle == "tool":
            eingabe.append({"type": "function_call_output", "call_id": m.get("tool_call_id") or "",
                            "output": _text(m.get("content"))})
        elif rolle == "assistant":
            if _text(m.get("content")).strip():
                eingabe.append({"role": "assistant", "content": _text(m.get("content"))})
            for c in m.get("tool_calls") or []:
                f = c.get("function") or {}
                eingabe.append({"type": "function_call", "call_id": c.get("id") or "", "name": f.get("name", ""),
                                "arguments": f.get("arguments") or "{}"})
        else:
            eingabe.append({"role": "user", "content": _text(m.get("content"))})
    body = {"instructions": "\n\n".join(a for a in anweisungen if a), "input": eingabe, "store": False, "stream": True}
    if tools:
        body["tools"] = [{"type": "function", "name": t["function"]["name"],
                          "description": t["function"].get("description", ""),
                          "parameters": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                         for t in tools if t.get("type") == "function"]
        body["tool_choice"] = "auto"                 # wie in Sentient; „any“/erzwungen ist nicht erlaubt
    return body


def nachricht(model, messages, tools=None, timeout=180):
    """Wie brain_message: -> ({"content": text, "tool_calls": [...]}, benutztes_modell)."""
    if not bereit():
        raise PlanFehler("aus", "nicht bereit (aus, Pause oder nicht angemeldet).")
    modell = str(model)[len(PREFIX):] if ist_chatgpt(model) else model
    body = umwandeln(messages, tools)
    body["model"] = modell
    for versuch in range(2):            # Lehnt OpenAI den Zugang ab (401), einmal erneuern und nochmal (wie Shelley)
        try:
            fertig, gesammelt = _streamen(body, zugang(), timeout)
            break
        except PlanFehler as e:
            if e.art != "anmeldung" or versuch:
                raise
            _zugang.update(token="", bis=0)
    if fertig.get("status") not in (None, "completed"):
        grund = (fertig.get("incomplete_details") or {}).get("reason") or fertig.get("status")
        raise PlanFehler("fehler", f"Antwort unvollständig ({grund}).")
    if (_cfg().get("chatgpt_status") or "ok") != "ok":
        _cfg_setzen(chatgpt_status="ok")
    # Bei store=false kann die Schluss-Meldung ohne „output“ kommen -> dann die unterwegs gesammelten Teile nehmen
    # (so machen es auch Sentient und Codex: Antwort aus den einzelnen Stream-Ereignissen zusammensetzen)
    text, aufrufe = [], []
    for item in fertig.get("output") or gesammelt["items"]:
        if item.get("type") == "message":
            for teil in item.get("content") or []:
                if teil.get("type") in ("output_text", "text"):
                    text.append(teil.get("text", ""))
        elif item.get("type") == "function_call":
            aufrufe.append({"id": item.get("call_id") or item.get("id") or "", "type": "function",
                            "function": {"name": item.get("name", ""), "arguments": item.get("arguments") or "{}"}})
    if not text and not aufrufe and gesammelt["text"]:
        text = gesammelt["text"]                     # nur Text-Stückchen kamen an
    msg = {"role": "assistant", "content": "".join(text)}
    if aufrufe:
        msg["tool_calls"] = aufrufe
    return msg, PREFIX + (fertig.get("model") or modell)


def _streamen(body, token, timeout):
    """Eine Anfrage an /v1/responses; liest den Stream. -> (Schluss-Antwort, unterwegs gesammelte Teile)."""
    req = urllib.request.Request(API + "/responses", json.dumps(body).encode("utf-8"), {
        "Content-Type": "application/json", "Accept": "text/event-stream", "Authorization": "Bearer " + token})
    fertig, ende = None, time.time() + timeout
    gesammelt = {"items": [], "text": [], "args": {}}
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            daten = []
            for roh in r:                                    # Server-Sent Events: „event:“/„data:“-Zeilen
                if time.time() > ende:
                    raise PlanFehler("pause", "Zeitgrenze überschritten.")
                zeile = roh.decode("utf-8", "replace").rstrip("\r\n")
                if zeile.startswith("data:"):
                    daten.append(zeile[5:].strip())
                    continue
                if zeile or not daten:
                    continue
                text, daten = "\n".join(daten), []
                if text == "[DONE]":
                    break
                try:
                    ev = json.loads(text)
                except ValueError:
                    continue
                typ = ev.get("type")
                if typ == "response.output_text.delta" and ev.get("delta"):
                    gesammelt["text"].append(ev["delta"])
                elif typ == "response.function_call_arguments.done" and ev.get("arguments") is not None:
                    gesammelt["args"][ev.get("item_id") or ""] = ev["arguments"]
                elif typ == "response.output_item.done" and isinstance(ev.get("item"), dict):
                    item = dict(ev["item"])
                    if item.get("type") == "function_call" and not item.get("arguments"):
                        item["arguments"] = gesammelt["args"].get(item.get("id") or "", "")
                    gesammelt["items"].append(item)
                elif typ in ("response.completed", "response.incomplete"):
                    fertig = ev.get("response") or {}
                    break
                elif typ in ("response.failed", "error"):
                    err = (ev.get("response") or {}).get("error") or ev.get("error") or {}
                    _fehler_code(err.get("code") or "", 0, err.get("message") or "")
    except urllib.error.HTTPError as e:
        _http_fehler(e)
    except urllib.error.URLError:
        raise PlanFehler("pause", "Keine Verbindung zu ChatGPT (Internet?).")
    if fertig is None:
        raise PlanFehler("fehler", "Antwort kam nicht vollständig an.")    # ohne „completed“ gilt sie als Fehler
    return fertig, gesammelt
