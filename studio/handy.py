"""
Watson auf dem Handy – über einen privaten, verschlüsselten Tunnel (Tailscale).

Sicherheit in Schichten:
  1. Der Handy-Server hört NUR auf 127.0.0.1 (diesen Computer). Aus dem Internet oder WLAN ist er nicht erreichbar.
  2. Nur über „tailscale serve“ (nicht „funnel“!) wird er für die EIGENEN Geräte des Nutzers freigegeben –
     Ende-zu-Ende verschlüsselt mit WireGuard, mit HTTPS-Zertifikat.
  3. Zusätzlich PIN-Anmeldung (gespeichert nur als gesalzener Hash im Windows-Tresor), Sperre nach 5 Fehlversuchen,
     Sitzungen laufen nach 30 Tagen ab.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import numpy as np

import pfade
import tresor

PORT = 8765
HIER = Path(__file__).resolve().parent
SITZUNGEN = {}                    # sha256(token) -> ablauf (nur Hashes werden gespeichert)
SITZUNGS_DATEI = pfade.DATEN / "handy_sitzungen.json"


def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _sitzungen_laden():
    try:
        SITZUNGEN.update({k: v for k, v in json.loads(SITZUNGS_DATEI.read_text(encoding="utf-8")).items() if v > time.time()})
    except Exception:
        pass


def _sitzungen_speichern():
    try:
        SITZUNGS_DATEI.write_text(json.dumps({k: v for k, v in SITZUNGEN.items() if v > time.time()}), encoding="utf-8")
    except OSError:
        pass
FEHLVERSUCHE = {"anzahl": 0, "gesperrt_bis": 0, "sperren": 0}
ERHOEHT = {}                      # sha256(sitzung) -> bis wann die Fingerabdruck-Bestätigung gilt
ERHOEHT_SEKUNDEN = 300            # 5 Minuten


def _fehlversuch():
    """Nach 5 Fehlern sperren: 15 Minuten, dann 30, 60 … bis höchstens 24 Stunden."""
    FEHLVERSUCHE["anzahl"] += 1
    if FEHLVERSUCHE["anzahl"] >= 5:
        dauer = min(900 * 2 ** FEHLVERSUCHE["sperren"], 86400)
        FEHLVERSUCHE.update(anzahl=0, gesperrt_bis=time.time() + dauer, sperren=FEHLVERSUCHE["sperren"] + 1)
        sicherheit_log(f"Gesperrt für {dauer // 60} Minuten nach 5 falschen Anmeldeversuchen")


def sicherheit_log(text):
    """Heikle Vorgänge vom Handy protokollieren (lesbar im Handy-Menü und in der Datei am Laptop)."""
    try:
        with open(pfade.DATEN / "handy_sicherheit.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%d.%m.%Y %H:%M:%S')}  {text}\n")
    except OSError:
        pass
    try:
        if "protokoll" in H:
            H["protokoll"]("watson__handy_sicherheit", {}, text)
    except Exception:
        pass


def sicherheit_log_lesen(n=30):
    try:
        return (pfade.DATEN / "handy_sicherheit.log").read_text(encoding="utf-8").splitlines()[-n:][::-1]
    except OSError:
        return []
H = {}                            # api (Api-Instanz), mund, stimme() -> auswahl, name() -> Watsons Name
_server = None
TAILSCALE = r"C:\Program Files\Tailscale\tailscale.exe"


def init(**helfer):
    H.update(helfer)


# ---------------- PIN ----------------
def passwort_pruefen_staerke(pw):
    """Ein starkes Passwort: mindestens 12 Zeichen, mit Buchstaben UND Ziffern oder Sonderzeichen."""
    pw = str(pw or "")
    if len(pw) < 12:
        return "Das Passwort braucht mindestens 12 Zeichen."
    if len(pw) > 128:
        return "Das Passwort ist zu lang (höchstens 128 Zeichen)."
    if not any(c.isalpha() for c in pw) or all(c.isalpha() for c in pw):
        return "Bitte Buchstaben UND Ziffern oder Sonderzeichen mischen."
    if len(set(pw)) < 6:
        return "Das Passwort ist zu einfach (zu viele gleiche Zeichen)."
    return None


def pin_setzen(pin):
    """Setzt das Handy-Passwort (früher PIN). Nur noch starke Passwörter werden angenommen."""
    pin = str(pin or "")
    fehler = passwort_pruefen_staerke(pin)
    if fehler:
        raise ValueError(fehler)
    salz = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salz), 200_000).hex()
    tresor.speichern("handy_pin", f"{salz}:{h}")
    tresor.speichern("handy_pin_art", "passwort")
    SITZUNGEN.clear()             # neues Passwort -> alle alten Anmeldungen ungültig
    ERHOEHT.clear()
    _sitzungen_speichern()


def ist_passwort():
    """True, wenn schon ein starkes Passwort gesetzt ist (nicht mehr die alte Ziffern-PIN)."""
    return tresor.lesen("handy_pin_art") == "passwort"


def pin_gesetzt():
    return bool(tresor.lesen("handy_pin"))


ERST_PIN_SPERRE = threading.Lock()


def _ueber_tunnel(host):
    """True, wenn die Anfrage über die private Tailscale-Adresse (…ts.net) kommt."""
    return (host or "").split(":")[0].lower().endswith(".ts.net")


def erst_pin_setzen(pin, host):
    """Erste PIN direkt vom Handy – NUR solange noch keine PIN existiert und NUR über den Tailscale-Tunnel
    (den nur die eigenen Geräte erreichen). Danach ist dieser Weg sofort zu: Ändern geht nur am Laptop."""
    if not _ueber_tunnel(host):
        raise PermissionError("Die erste PIN kann nur über die sichere Tunnel-Adresse (…ts.net) festgelegt werden.")
    with ERST_PIN_SPERRE:     # zwei gleichzeitige Versuche: nur der erste gewinnt
        if pin_gesetzt():
            raise PermissionError("Es gibt schon eine PIN. Ändern geht nur in Watson am Laptop (Einstellungen).")
        pin_setzen(pin)


def _pin_pruefen(pin):
    gespeichert = tresor.lesen("handy_pin") or ""
    if ":" not in gespeichert:
        return False
    salz, h = gespeichert.split(":", 1)
    versuch = hashlib.pbkdf2_hmac("sha256", str(pin).encode(), bytes.fromhex(salz), 200_000).hex()
    return hmac.compare_digest(versuch, h)


# ---------------- Fingerabdruck (Passkeys / WebAuthn) ----------------
# Der Fingerabdruck verlässt nie das Handy. Das Handy erzeugt ein Schlüsselpaar; Watson speichert nur den
# ÖFFENTLICHEN Schlüssel und prüft damit die Unterschrift des Handys bei jeder Anmeldung.
PASSKEYS = pfade.DATEN / "handy_passkeys.json"
HERAUSFORDERUNGEN = {}            # schlüssel -> (challenge, ablauf)


def _passkeys():
    try:
        return json.loads(PASSKEYS.read_text(encoding="utf-8"))
    except Exception:
        return []


def _passkeys_speichern(liste):
    PASSKEYS.write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")


def passkeys_liste():
    return [{k: p[k] for k in ("id", "name", "datum", "zuletzt", "rp_id")} for p in _passkeys()]


def passkey_loeschen(pid):
    _passkeys_speichern([p for p in _passkeys() if p["id"] != pid])


def _rp(host):
    """Name und Adresse, für die der Fingerabdruck gilt. Nur die Tailscale-Adresse (…ts.net) oder localhost (Test)."""
    host = (host or "").split(":")[0].lower()
    if host.endswith(".ts.net") or host == "localhost":
        return host
    return None


def _herausforderung(schluessel, challenge=None):
    jetzt = time.time()
    for k in [k for k, (_, t) in HERAUSFORDERUNGEN.items() if t < jetzt]:
        HERAUSFORDERUNGEN.pop(k, None)
    if challenge is not None:
        HERAUSFORDERUNGEN[schluessel] = (challenge, jetzt + 300)
        return challenge
    c = HERAUSFORDERUNGEN.pop(schluessel, None)
    return c[0] if c else None


# ---------------- Tailscale ----------------
def tailscale_status():
    exe = TAILSCALE if os.path.exists(TAILSCALE) else shutil.which("tailscale")
    if not exe:
        return {"installiert": False}
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=20, creationflags=0x08000000)
        j = json.loads(r.stdout or "{}")
        selbst = j.get("Self") or {}
        dns = (selbst.get("DNSName") or "").rstrip(".")
        s = subprocess.run([exe, "serve", "status"], capture_output=True, text=True, timeout=20, creationflags=0x08000000)
        return {"installiert": True, "angemeldet": j.get("BackendState") == "Running", "adresse": dns,
                "tunnel_an": f"127.0.0.1:{PORT}" in (s.stdout or ""), "zustand": j.get("BackendState")}
    except Exception as e:
        return {"installiert": True, "fehler": str(e)[:200]}


def tunnel(an):
    exe = TAILSCALE if os.path.exists(TAILSCALE) else shutil.which("tailscale")
    if not exe:
        return {"error": "Tailscale ist noch nicht installiert."}
    # „serve“ = nur für die eigenen Geräte im privaten Netz. NIE „funnel“ (das wäre öffentlich).
    if not an:
        r = subprocess.run([exe, "serve", "--https=443", "off"], capture_output=True, text=True, timeout=60,
                           creationflags=0x08000000)
        if r.returncode != 0:
            return {"error": (r.stderr or r.stdout or "unbekannter Fehler").strip()[-400:]}
        return {"ok": True, **tailscale_status()}
    # Beim allerersten Mal ist „Serve“ im Tailscale-Konto noch nicht freigegeben. Dann nennt Tailscale einen Link und
    # WARTET, bis der Nutzer dort „Enable“ klickt. Wir zeigen den Link an und lassen den Befehl im Hintergrund weiter
    # warten – sobald freigegeben ist, geht der Tunnel von selbst an.
    p = subprocess.Popen([exe, "serve", "--bg", "--https=443", f"http://127.0.0.1:{PORT}"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, creationflags=0x08000000)
    ausgabe, link, fertig = [], [None], threading.Event()

    def lesen():
        for zeile in p.stdout:
            ausgabe.append(zeile)
            if "login.tailscale.com" in zeile and not link[0]:
                link[0] = zeile.strip().split()[-1]
                fertig.set()
        fertig.set()
    threading.Thread(target=lesen, daemon=True).start()
    fertig.wait(timeout=45)
    if link[0] and p.poll() is None:
        uhr = threading.Timer(1800, lambda: p.poll() is None and p.kill())   # nach 30 Min. aufgeben
        uhr.daemon = True                                                      # hält Watson beim Beenden nicht auf
        uhr.start()
        return {"freigabe_link": link[0],
                "error": "Einmalig nötig: „Serve“ ist in deinem Tailscale-Konto noch nicht freigegeben. "
                         "Öffne den Link, melde dich an und klicke auf „Enable“ – danach geht der Tunnel von selbst an."}
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        return {"error": "Tailscale antwortet nicht. Ist Tailscale gestartet und angemeldet?"}
    if p.returncode != 0:
        return {"error": "".join(ausgabe).strip()[-400:] or "unbekannter Fehler"}
    return {"ok": True, **tailscale_status()}


# ---------------- Server ----------------
def _wav(audio, rate):
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "Watson"

    def log_message(self, *a):          # keine Konsolen-Ausgabe
        pass

    def _antwort(self, code, daten, art="application/json; charset=utf-8", kopf=None):
        body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", art)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (kopf or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _angemeldet(self):
        for teil in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = teil.strip().partition("=")
            if k == "watson_sitzung" and v and SITZUNGEN.get(_h(v), 0) > time.time():
                _benutzt()                           # Nutzer ist gerade auf dem Handy -> Laptop still
                return True
        return False

    def _sitzung_hash(self):
        for teil in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = teil.strip().partition("=")
            if k == "watson_sitzung" and v:
                return _h(v)
        return None

    def _rp_origin(self):
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        rp = _rp(host)
        if not rp:
            return None, None
        origin = f"http://{host}" if rp == "localhost" else f"https://{rp}"
        return rp, origin

    def _neue_sitzung(self):
        token = secrets.token_urlsafe(32)
        SITZUNGEN[_h(token)] = time.time() + 30 * 86400
        _sitzungen_speichern()
        return {"Set-Cookie": f"watson_sitzung={token}; Path=/; Max-Age={30 * 86400}; HttpOnly; Secure; SameSite=Strict"}

    def _passkey(self, pfad, d):
        """Fingerabdruck: einrichten (nur angemeldet) und anmelden."""
        import webauthn
        from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
        from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                              ResidentKeyRequirement, UserVerificationRequirement)
        rp, origin = self._rp_origin()
        if not rp:
            return self._antwort(400, {"error": "Fingerabdruck geht nur über die sichere Tunnel-Adresse (…ts.net)."})
        eigene = [p for p in _passkeys() if p.get("rp_id") == rp]
        if pfad == "/api/passkey/login_start":
            if FEHLVERSUCHE["gesperrt_bis"] > time.time():
                return self._antwort(429, {"error": "Zu viele falsche Versuche. Bitte in ein paar Minuten noch einmal."})
            if not eigene:
                return self._antwort(404, {"error": "Auf diesem Handy ist noch kein Fingerabdruck eingerichtet."})
            opt = webauthn.generate_authentication_options(
                rp_id=rp, user_verification=UserVerificationRequirement.REQUIRED,
                allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["id"])) for p in eigene])
            vorgang = secrets.token_urlsafe(16)
            _herausforderung("login:" + vorgang, opt.challenge)
            return self._antwort(200, {"vorgang": vorgang, "optionen": json.loads(webauthn.options_to_json(opt))})
        if pfad == "/api/passkey/login":
            challenge = _herausforderung("login:" + str(d.get("vorgang", "")))
            cred = d.get("credential") or {}
            p = next((x for x in eigene if x["id"] == cred.get("id")), None)
            if not challenge or not p:
                return self._antwort(401, {"error": "Anmeldung abgelaufen oder unbekanntes Handy. Bitte nochmal."})
            try:
                v = webauthn.verify_authentication_response(
                    credential=cred, expected_challenge=challenge, expected_rp_id=rp, expected_origin=origin,
                    credential_public_key=base64url_to_bytes(p["schluessel"]),
                    credential_current_sign_count=p.get("zaehler", 0), require_user_verification=True)
            except Exception as e:
                _fehlversuch()
                return self._antwort(401, {"error": f"Fingerabdruck-Anmeldung abgelehnt ({str(e)[:80]})."})
            alle = _passkeys()
            for x in alle:
                if x["id"] == p["id"]:
                    x["zaehler"], x["zuletzt"] = v.new_sign_count, time.strftime("%d.%m.%Y %H:%M")
            _passkeys_speichern(alle)
            FEHLVERSUCHE.update(anzahl=0, sperren=0)
            return self._antwort(200, {"ok": True}, kopf=self._neue_sitzung())
        # --- ab hier nur für angemeldete Nutzer (Einrichten eines neuen Fingerabdrucks) ---
        if not self._angemeldet():
            return self._antwort(401, {"error": "Bitte zuerst mit deiner PIN anmelden."})
        if pfad == "/api/passkey/bestaetigen_start":
            if not eigene:
                return self._antwort(404, {"error": "Auf diesem Handy ist noch kein Fingerabdruck eingerichtet. Richte ihn zuerst unter Sicherheit ein."})
            opt = webauthn.generate_authentication_options(
                rp_id=rp, user_verification=UserVerificationRequirement.REQUIRED,
                allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["id"])) for p in eigene])
            _herausforderung("best:" + (self._sitzung_hash() or ""), opt.challenge)
            return self._antwort(200, {"optionen": json.loads(webauthn.options_to_json(opt))})
        if pfad == "/api/passkey/bestaetigen":
            sh = self._sitzung_hash() or ""
            challenge = _herausforderung("best:" + sh)
            cred = d.get("credential") or {}
            p = next((x for x in eigene if x["id"] == cred.get("id")), None)
            if not challenge or not p:
                return self._antwort(401, {"error": "Bestätigung abgelaufen. Bitte nochmal."})
            try:
                v = webauthn.verify_authentication_response(
                    credential=cred, expected_challenge=challenge, expected_rp_id=rp, expected_origin=origin,
                    credential_public_key=base64url_to_bytes(p["schluessel"]),
                    credential_current_sign_count=p.get("zaehler", 0), require_user_verification=True)
            except Exception as e:
                _fehlversuch()
                return self._antwort(401, {"error": f"Bestätigung abgelehnt ({str(e)[:80]})."})
            alle = _passkeys()
            for x in alle:
                if x["id"] == p["id"]:
                    x["zaehler"], x["zuletzt"] = v.new_sign_count, time.strftime("%d.%m.%Y %H:%M")
            _passkeys_speichern(alle)
            ERHOEHT[sh] = time.time() + ERHOEHT_SEKUNDEN
            return self._antwort(200, {"ok": True, "sekunden": ERHOEHT_SEKUNDEN})
        if pfad == "/api/passkey/einrichten_start":
            opt = webauthn.generate_registration_options(
                rp_id=rp, rp_name="Watson", user_name=H["name"]() + "-Nutzer", user_id=b"watson-nutzer-1",
                user_display_name="Watson auf dem Handy",
                authenticator_selection=AuthenticatorSelectionCriteria(
                    user_verification=UserVerificationRequirement.REQUIRED,
                    resident_key=ResidentKeyRequirement.PREFERRED),
                exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["id"])) for p in eigene])
            _herausforderung("reg:" + (self._sitzung_hash() or ""), opt.challenge)
            return self._antwort(200, {"optionen": json.loads(webauthn.options_to_json(opt))})
        if pfad == "/api/passkey/einrichten":
            challenge = _herausforderung("reg:" + (self._sitzung_hash() or ""))
            if not challenge:
                return self._antwort(400, {"error": "Einrichtung abgelaufen. Bitte nochmal starten."})
            try:
                v = webauthn.verify_registration_response(
                    credential=d.get("credential") or {}, expected_challenge=challenge, expected_rp_id=rp,
                    expected_origin=origin, require_user_verification=True)
            except Exception as e:
                return self._antwort(400, {"error": f"Einrichtung fehlgeschlagen ({str(e)[:100]})."})
            alle = _passkeys()
            alle.append({"id": bytes_to_base64url(v.credential_id), "schluessel": bytes_to_base64url(v.credential_public_key),
                         "zaehler": v.sign_count, "name": str(d.get("name") or "Mein Handy")[:40],
                         "datum": time.strftime("%d.%m.%Y %H:%M"), "zuletzt": "", "rp_id": rp})
            _passkeys_speichern(alle)
            sicherheit_log(f"Neuer Fingerabdruck eingerichtet ({str(d.get('name') or 'Mein Handy')[:40]})")
            return self._antwort(200, {"ok": True})
        return self._antwort(404, {"error": "Nicht gefunden"})

    def _json(self):
        n = min(int(self.headers.get("Content-Length") or 0), 200_000)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        pfad = self.path.split("?")[0]
        if pfad in ("/", "/index.html"):
            return self._antwort(200, (HIER / "handy.html").read_bytes(), "text/html; charset=utf-8")
        if pfad == "/manifest.json":
            return self._antwort(200, {"name": H["name"](), "short_name": H["name"](), "start_url": "/",
                                       "display": "standalone", "background_color": "#16181c", "theme_color": "#185FA5",
                                       "icons": [{"src": "/logo.png", "sizes": "512x512", "type": "image/png"}]},
                                 "application/manifest+json")
        if pfad == "/i18n.js":
            return self._antwort(200, (HIER / "i18n.js").read_bytes(), "text/javascript; charset=utf-8")
        if pfad == "/logo.png":
            return self._antwort(200, (HIER / "assets" / "watson-logo.png").read_bytes(), "image/png",
                                 {"Cache-Control": "max-age=86400"})
        if pfad == "/api/status":
            rp, _ = self._rp_origin()
            return self._antwort(200, {"angemeldet": self._angemeldet(), "pin_gesetzt": pin_gesetzt(), "passwort": ist_passwort(),
                                       "name": H["name"](), "fingerabdruck_moeglich": bool(rp),
                                       "ui_sprache": (H["config_laden"]().get("ui_sprache") if "config_laden" in H else None) or "de",
                                       "erst_pin_moeglich": (not pin_gesetzt()) and _ueber_tunnel(
                                           self.headers.get("X-Forwarded-Host") or self.headers.get("Host")),
                                       "fingerabdruck_eingerichtet": any(p.get("rp_id") == rp for p in _passkeys())})
        if not self._angemeldet():
            return self._antwort(401, {"error": "Bitte zuerst mit deiner PIN anmelden."})
        if pfad == "/api/fragen":
            return self._antwort(200, {"fragen": H["offene_fragen"]()})
        if pfad.startswith("/api/stimme/"):
            import stimmtraining
            if pfad == "/api/stimme/status":
                return self._antwort(200, stimmtraining.status())
            if pfad == "/api/stimme/satz":
                return self._antwort(200, stimmtraining.satz(self._nr()))
            if pfad == "/api/stimme/audio":
                daten = stimmtraining.audio(self._nr())
                if daten is None:
                    return self._antwort(404, {"error": "Noch keine Aufnahme."})
                return self._antwort(200, daten, "audio/wav")
        return self._antwort(404, {"error": "Nicht gefunden"})

    # Was das Handy darf (bewusst begrenzt: keine Schlüssel, kein Tresor, keine Vertrauensstufe)
    HANDY_EINSTELLUNGEN = ("model", "piper_voice", "tts_engine", "voice")

    def _handy_aktion(self, aktion, d):
        api = H["api"]
        if aktion == "einstellungen":
            cfg = api.get_config()
            return {k: cfg.get(k) for k in self.HANDY_EINSTELLUNGEN}
        if aktion == "einstellungen_setzen":
            teil = {k: d[k] for k in self.HANDY_EINSTELLUNGEN if k in d}
            if "voice" in teil:
                teil["voice"] = bool(teil["voice"])
            api.save_config(teil)
            return {"ok": True}
        if aktion == "gehirne":
            m = api.get_models()
            if isinstance(m, dict):
                return m
            return {"gehirne": [{"id": x.get("id"), "name": x.get("name"), "free": x.get("free")} for x in m]}
        if aktion == "gespraeche":
            return {"gespraeche": api.list_chats()}
        if aktion == "gespraech":
            return {"nachrichten": [x for x in api.load_chat(int(d.get("id", 0))) if x.get("role") in ("user", "assistant")]}
        if aktion == "gespraech_loeschen":
            return api.delete_chat(int(d.get("id", 0)))
        if aktion == "ablaeufe":
            return api.n8n_status()
        if aktion == "ablauf_starten":
            pfade_ok = [a.get("pfad") for a in (api.n8n_status().get("ablaeufe") or [])]
            if d.get("pfad") not in pfade_ok:
                return {"error": "Diesen Ablauf gibt es nicht."}
            return api.n8n_test(d["pfad"])
        if aktion == "termine":
            return api.kalender_termine(int(d.get("tage", 7)))
        if aktion == "merkzettel":
            return api.facts()
        if aktion == "merkzettel_neu":
            t = str(d.get("text", "")).strip()[:500]
            return api.add_fact(t) if t else {"error": "Leerer Eintrag."}
        if aktion == "merkzettel_loeschen":
            return api.delete_fact(int(d.get("id", 0)))
        if aktion == "rezepte":
            return api.rezepte_liste()
        if aktion == "wissen":
            r = api.wissen_liste()
            try:
                import wachstum
                r["interessen"] = wachstum.interessen()
            except Exception:
                r["interessen"] = []
            return r
        if aktion == "werkzeuge":
            st = api.mcp_status()
            return {"anzahl": st.get("count", 0), "server": [{"name": x["name"], "ok": x["ok"], "fehler": x.get("error"),
                                                             "werkzeuge": len(x.get("tools") or [])} for x in st.get("servers", [])]}
        if aktion == "werkzeug_suchen":
            begriff = str(d.get("begriff", "")).strip()[:100]
            if not begriff:
                return {"error": "Gib ein Wort ein, was Watson können soll."}
            return api.mcp_suchen(begriff, d.get("weiter") or None)
        if aktion == "werkzeug_einstecken":
            return api.mcp_einstecken(str(d.get("id", ""))[:200])
        return {"error": "Unbekannte Aktion."}

    def _erhoeht(self):
        sh = self._sitzung_hash()
        return bool(sh) and ERHOEHT.get(sh, 0) > time.time()

    def _heikel(self, aktion, d):
        """Schlüssel, Tresor, Vertrauensstufe, Passwort: nur mit frischer Fingerabdruck-Bestätigung."""
        api = H["api"]
        if aktion == "sicherheit":      # Übersicht darf jeder Angemeldete sehen (ohne Geheimnisse)
            sh = self._sitzung_hash()
            rp, _ = self._rp_origin()
            return {"bestaetigt_bis": max(0, int(ERHOEHT.get(sh, 0) - time.time())), "passwort": ist_passwort(),
                    "fingerabdruecke": [p.get("name") for p in _passkeys() if p.get("rp_id") == rp],
                    "fingerabdruck_moeglich": bool(rp), "protokoll": sicherheit_log_lesen(),
                    "use_system": bool(H["config_laden"]().get("use_system"))}
        if not self._erhoeht():
            return {"error": "Bitte zuerst mit Fingerabdruck oder Gesicht bestätigen.", "bestaetigen": True}
        if aktion == "schluessel":
            return {"schluessel": api.keys_list()}
        if aktion == "schluessel_setzen":
            cfg = H["config_laden"]()
            kennung = re.sub(r"[^a-z0-9_]", "", str(d.get("id") or "").lower())[:40]
            name = str(d.get("name") or "").strip()[:60]
            wert = str(d.get("wert") or "").strip()
            if not wert:
                return {"error": "Bitte einen Schlüssel eingeben."}
            if len(wert) > 4000:
                return {"error": "Der Schlüssel ist zu lang."}
            if not kennung:
                kennung = ("eigen_" + re.sub(r"[^a-z0-9]", "", name.lower())[:20]) if name else f"eigen_{int(time.time())}"
            neu = not tresor.vorhanden(kennung)
            tresor.speichern(kennung, wert)
            liste = [x for x in cfg.get("schluessel", []) if x.get("id") != kennung]
            liste.append({"id": kennung, "name": (name or tresor.BEKANNT.get(kennung, kennung))[:60],
                          "geaendert": time.strftime("%d.%m.%Y")})
            cfg["schluessel"] = liste
            H["config_speichern"](cfg)
            sicherheit_log(f"Schlüssel „{kennung}“ {'eingetragen' if neu else 'geändert'} (vom Handy)")
            return {"ok": True}
        if aktion == "schluessel_loeschen":
            kennung = str(d.get("id") or "")
            cfg = H["config_laden"]()
            if kennung not in H["schluessel_ids"](cfg):
                return {"error": "Unbekannter Schlüssel."}
            tresor.loeschen(kennung)
            if kennung not in tresor.BEKANNT:
                cfg["schluessel"] = [x for x in cfg.get("schluessel", []) if x.get("id") != kennung]
                H["config_speichern"](cfg)
            sicherheit_log(f"Schlüssel „{kennung}“ gelöscht (vom Handy)")
            return {"ok": True}
        if aktion == "system_setzen":
            an = bool(d.get("an"))
            api.save_config({"use_system": an})
            sicherheit_log(f"System-Werkzeuge (Auskunft + PowerShell) {'ERLAUBT' if an else 'ausgeschaltet'} (vom Handy)")
            return {"ok": True, "an": an}
        if aktion == "vertrauen":
            v = api.vertrauen_status()
            return {"stufe": v.get("stufe"), "stufen": v.get("stufen"), "grenzen": v.get("grenzen")}
        if aktion == "vertrauen_setzen":
            r = api.vertrauen_setzen(int(d.get("stufe", 0)))
            if r.get("ok"):
                sicherheit_log(f"Vertrauensstufe auf {r['stufe']} gesetzt (vom Handy)")
            return r
        if aktion == "passwort_setzen":
            neu, wdh = str(d.get("neu") or ""), str(d.get("wiederholung") or "")
            if neu != wdh:
                return {"error": "Die beiden Passwörter sind nicht gleich."}
            try:
                pin_setzen(neu)
            except ValueError as e:
                return {"error": str(e)}
            sicherheit_log("Passwort geändert (vom Handy) – alle anderen Anmeldungen wurden abgemeldet")
            return {"ok": True, "_neue_sitzung": True}
        return {"error": "Unbekannte Aktion."}

    def _handy_datei(self):
        """Datei vom Handy annehmen, in der Ablage speichern und den Text herauslesen."""
        from urllib.parse import parse_qs, urlparse, unquote
        n = int(self.headers.get("Content-Length") or 0)
        if not self._angemeldet():
            self.rfile.read(min(n, 20_000_000))
            return self._antwort(401, {"error": "Bitte zuerst mit deiner PIN anmelden."})
        if n <= 0 or n > 20_000_000:
            return self._antwort(400, {"error": "Die Datei ist leer oder größer als 20 MB."})
        daten = self.rfile.read(n)
        name = unquote(parse_qs(urlparse(self.path).query).get("name", ["datei"])[0])
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(". ")[:120] or "datei"
        ziel = pfade.ABLAGE / "vom-handy"
        ziel.mkdir(parents=True, exist_ok=True)
        pfad = ziel / name
        if pfad.exists():
            pfad = ziel / f"{pfad.stem}-{int(time.time())}{pfad.suffix}"
        pfad.write_bytes(daten)
        r = H["api"].dokument_lesen(str(pfad))
        r["gespeichert"] = str(pfad)
        return self._antwort(200, r)

    def _nr(self):
        from urllib.parse import parse_qs, urlparse
        try:
            return int(parse_qs(urlparse(self.path).query).get("nr", ["0"])[0])
        except ValueError:
            return 0

    def _stimme_aufnahme(self):
        """Eine Aufnahme fürs Stimm-Training (WAV vom Handy) entgegennehmen."""
        n = int(self.headers.get("Content-Length") or 0)
        if not self._angemeldet():
            self.rfile.read(min(n, 5_000_000))
            return self._antwort(401, {"error": "Bitte zuerst mit deiner PIN anmelden."})
        if n <= 0 or n > 5_000_000:
            return self._antwort(400, {"error": "Die Aufnahme ist leer oder zu groß."})
        daten = self.rfile.read(n)
        try:
            import stimmtraining
            return self._antwort(200, stimmtraining.speichern(self._nr(), daten))
        except Exception as e:
            if "fehler_melden" in H:
                H["fehler_melden"]("Handy/Stimm-Training", e)
            return self._antwort(500, {"error": f"Fehler beim Speichern: {e}"})

    def _hoeren(self):
        """Gesprächsmodus am Handy: Aufnahme (WAV 16 kHz mono) -> Text mit Whisper auf dem Laptop."""
        n = int(self.headers.get("Content-Length") or 0)
        if not self._angemeldet():
            self.rfile.read(min(n, 4_000_000))
            return self._antwort(401, {"error": "Bitte zuerst mit deiner PIN anmelden."})
        if n <= 44 or n > 4_000_000:
            self.rfile.read(min(n, 4_000_000))
            return self._antwort(400, {"error": "Die Aufnahme ist leer oder zu lang."})
        ohren = H.get("ohren")
        if not ohren:
            self.rfile.read(n)
            return self._antwort(503, {"error": "Spracherkennung ist auf dem Laptop nicht verfügbar."})
        daten = self.rfile.read(n)
        try:
            with wave.open(BytesIO(daten)) as w:
                if w.getsampwidth() != 2 or w.getnchannels() != 1:
                    return self._antwort(400, {"error": "Falsches Tonformat."})
                rate = w.getframerate()
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            if rate != 16000 and len(pcm):            # zur Sicherheit auf 16 kHz bringen
                m = int(len(pcm) * 16000 / rate)
                pcm = np.interp(np.linspace(0, len(pcm) - 1, m), np.arange(len(pcm)), pcm).astype(np.float32)
            if len(pcm) < 16000 * 0.3:
                return self._antwort(200, {"text": ""})
            import stimme
            t0 = time.time()
            text = ohren.transcribe(pcm, sicher=True)
            ende = bool(text) and bool(stimme.GESPRAECH_ENDE_RE.match(text))
            return self._antwort(200, {"text": text, "ende": ende, "sekunden": round(time.time() - t0, 1)})
        except Exception as e:
            if "fehler_melden" in H:
                H["fehler_melden"]("Handy/Hören", e)
            return self._antwort(500, {"error": f"Spracherkennung: {e}"})

    def do_POST(self):
        pfad = self.path.split("?")[0]
        if pfad == "/api/stimme/aufnahme":
            return self._stimme_aufnahme()
        if pfad == "/api/hoeren":
            return self._hoeren()
        if pfad == "/api/handy/datei":
            try:
                return self._handy_datei()
            except Exception as e:
                if "fehler_melden" in H:
                    H["fehler_melden"]("Handy/Datei", e)
                return self._antwort(500, {"error": f"Fehler: {e}"})
        d = self._json()
        if pfad.startswith("/api/passkey/"):
            try:
                return self._passkey(pfad, d)
            except Exception as e:
                if "fehler_melden" in H:
                    H["fehler_melden"]("Handy/Fingerabdruck", e)
                return self._antwort(500, {"error": f"Fehler: {e}"})
        if pfad == "/api/pin_erstmals":
            pin, wdh = str(d.get("pin", "")).strip(), str(d.get("wiederholung", "")).strip()
            if pin != wdh:
                return self._antwort(400, {"error": "Die beiden PINs sind nicht gleich."})
            try:
                erst_pin_setzen(pin, self.headers.get("X-Forwarded-Host") or self.headers.get("Host"))
            except PermissionError as e:
                return self._antwort(403, {"error": str(e)})
            except ValueError as e:
                return self._antwort(400, {"error": str(e)})
            return self._antwort(200, {"ok": True}, kopf=self._neue_sitzung())
        if pfad == "/api/login":
            if FEHLVERSUCHE["gesperrt_bis"] > time.time():
                return self._antwort(429, {"error": "Zu viele falsche Versuche. Bitte in ein paar Minuten noch einmal."})
            if not pin_gesetzt():
                return self._antwort(403, {"error": "Es ist noch keine PIN festgelegt (in Watson unter Einstellungen)."})
            if not _pin_pruefen(d.get("pin", "")):
                _fehlversuch()
                time.sleep(1)
                return self._antwort(401, {"error": "Das Passwort stimmt nicht."})
            FEHLVERSUCHE.update(anzahl=0, sperren=0)
            token = secrets.token_urlsafe(32)
            SITZUNGEN[_h(token)] = time.time() + 30 * 86400
            _sitzungen_speichern()
            return self._antwort(200, {"ok": True}, kopf={
                "Set-Cookie": f"watson_sitzung={token}; Path=/; Max-Age={30 * 86400}; HttpOnly; Secure; SameSite=Strict"})
        if not self._angemeldet():
            return self._antwort(401, {"error": "Bitte zuerst mit deiner PIN anmelden."})
        api = H["api"]
        try:
            if pfad == "/api/chat":
                text = str(d.get("text", "")).strip()[:8000]
                if not text:
                    return self._antwort(400, {"error": "Leere Nachricht"})
                r = api.chat({"text": text, "chat_id": d.get("chat_id"), "von_handy": True})
                return self._antwort(200, {k: r.get(k) for k in ("text", "model", "chat_id", "tools", "lern_id",
                                                                 "lehrer", "error")})
            if pfad == "/api/antwort":
                return self._antwort(200, api.frage_antwort(str(d.get("id", "")), bool(d.get("ok"))))
            if pfad == "/api/bewerten":
                if not d.get("lern_id"):
                    return self._antwort(400, {"error": "Zu dieser Antwort gibt es nichts zu bewerten."})
                return self._antwort(200, api.bewerten(int(d["lern_id"]), int(d.get("wert", 0))))
            if pfad == "/api/stopp":
                return self._antwort(200, api.stop())
            if pfad.startswith("/api/sicher/"):
                r = self._heikel(pfad[len("/api/sicher/"):], d)
                if r.pop("_neue_sitzung", False):
                    return self._antwort(200, r, kopf=self._neue_sitzung())
                return self._antwort(403 if r.get("bestaetigen") else 200, r)
            if pfad.startswith("/api/handy/"):
                return self._antwort(200, self._handy_aktion(pfad[len("/api/handy/"):], d))
            if pfad == "/api/stimme/loeschen":
                import stimmtraining
                return self._antwort(200, stimmtraining.loeschen(int(d.get("nr", 0))))
            if pfad == "/api/sprich":
                text = str(d.get("text", "")).strip()[:1500]
                text = H["mund"]._clean(text).strip() or "…"     # Formatierungszeichen, Links, Emojis nicht vorlesen
                audio, rate = H["mund"].synth_ganz(text, H["stimme"]())   # Stück für Stück wie am Laptop, mit Atempausen
                return self._antwort(200, _wav(audio, rate), "audio/wav")
            if pfad == "/api/abmelden":
                for teil in (self.headers.get("Cookie") or "").split(";"):
                    k, _, v = teil.strip().partition("=")
                    if k == "watson_sitzung" and v:
                        SITZUNGEN.pop(_h(v), None)
                _sitzungen_speichern()
                return self._antwort(200, {"ok": True}, kopf={
                    "Set-Cookie": "watson_sitzung=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict"})
        except Exception as e:
            if "fehler_melden" in H:
                H["fehler_melden"]("Handy", e)
            return self._antwort(500, {"error": f"Fehler: {e}"})
        return self._antwort(404, {"error": "Nicht gefunden"})


LETZTE_NUTZUNG = [0.0]            # wann das Handy zuletzt benutzt wurde
HANDY_MODUS_MINUTEN = 15


def handy_modus():
    """True, solange der Nutzer gerade über das Handy mit Watson spricht (letzte Nutzung < 15 Min.).
    Dann bleibt der Laptop still: kein Ton, kein Fenster, keine Fragen auf dem Laptop-Bildschirm."""
    return bool(_server) and time.time() - LETZTE_NUTZUNG[0] < HANDY_MODUS_MINUTEN * 60


ZULETZT_DATEI = pfade.DATEN / "handy_zuletzt.txt"   # damit Watson auch nach einem Neustart weiß: Nutzer ist am Handy


def _zuletzt_merken():
    try:
        ZULETZT_DATEI.write_text(str(LETZTE_NUTZUNG[0]), encoding="utf-8")
    except Exception:
        pass


def _benutzt():
    alt = LETZTE_NUTZUNG[0]
    LETZTE_NUTZUNG[0] = time.time()
    if LETZTE_NUTZUNG[0] - alt > 60:      # höchstens einmal pro Minute auf die Platte schreiben
        _zuletzt_merken()


def laptop_benutzt():
    """Nutzer arbeitet am Laptop -> Handy-Modus sofort beenden."""
    if LETZTE_NUTZUNG[0]:
        LETZTE_NUTZUNG[0] = 0.0
        _zuletzt_merken()


def aktiv():
    """Ist gerade jemand auf dem Handy angemeldet (gültige Sitzung)?"""
    jetzt = time.time()
    return bool(_server) and any(t > jetzt for t in SITZUNGEN.values())


def starten():
    """Startet den Handy-Server (nur 127.0.0.1). Gibt False zurück, wenn der Port belegt ist."""
    global _server
    if _server:
        return True
    _sitzungen_laden()
    try:
        _server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        return False
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    try:                                  # weiß noch von vor dem Neustart, ob der Nutzer am Handy war
        LETZTE_NUTZUNG[0] = float(ZULETZT_DATEI.read_text(encoding="utf-8").strip() or 0)
    except Exception:
        pass
    return True
