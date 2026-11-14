"""
Zwei-Schritt-Anmeldung für Watson auf dem Handy (zusätzlich zum Passwort).

Wege:
- "app":   Authenticator-App (Google/Microsoft Authenticator, Aegis …) – Code wechselt alle 30 Sekunden (TOTP, RFC 6238).
- "email": 6-stelliger Code per E-Mail an Watsons eingerichtete Mail-Adresse (10 Minuten gültig).
- SMS ist bewusst nicht eingebaut: kostet Geld (SMS-Dienst) und ist der unsicherste Weg (SIM-Tausch-Betrug).

Dazu 10 Ersatz-Codes zum Aufschreiben (jeder nur einmal gültig), falls das Handy weg ist.
Alles Geheime liegt verschlüsselt im Windows-Tresor (Kennungen handy_2fa_* – vom Handy aus nicht änderbar).
Die Anmeldung mit Fingerabdruck braucht keinen zweiten Schritt: sie ist schon zweistufig (Handy + Finger).
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import threading
import time
from urllib.parse import quote

import tresor

ART, GEHEIM, ERSATZ, ZAEHLER = "handy_2fa_art", "handy_2fa_geheim", "handy_2fa_ersatz", "handy_2fa_zaehler"
SPERRE = threading.Lock()
ERSATZ_ZEICHEN = "abcdefghjkmnpqrstuvwxyz23456789"     # ohne 0/o, 1/l/i – nicht verwechselbar


# ---------------- Zustand ----------------
def art():
    a = tresor.lesen(ART)
    return a if a in ("app", "email") else ""


def aktiv():
    return bool(art())


def ersatz_uebrig():
    try:
        return len(json.loads(tresor.lesen(ERSATZ) or "[]"))
    except ValueError:
        return 0


def ausschalten():
    for k in (ART, GEHEIM, ERSATZ, ZAEHLER):
        tresor.loeschen(k)


# ---------------- Authenticator-App (TOTP) ----------------
def neues_geheimnis():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def app_link(geheimnis, konto="Handy"):
    """otpauth://-Link – öffnet auf dem Handy direkt die Authenticator-App (wenn sie das unterstützt)."""
    return (f"otpauth://totp/{quote('Watson:' + konto)}?secret={geheimnis}&issuer=Watson"
            "&algorithm=SHA1&digits=6&period=30")


def _code_fuer(geheimnis, zaehler):
    key = base64.b32decode(geheimnis + "=" * (-len(geheimnis) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", zaehler), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000)


def totp_pruefen(geheimnis, code, letzter=-1, jetzt=None):
    """Gibt den benutzten Zähler zurück (oder None). Erlaubt ±30 Sekunden Uhr-Abweichung.
    Ein Code, der schon benutzt wurde (Zähler <= letzter), gilt nicht noch einmal."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6 or not geheimnis:
        return None
    z = int((jetzt if jetzt is not None else time.time()) // 30)
    for d in (0, -1, 1):
        if z + d > letzter and hmac.compare_digest(_code_fuer(geheimnis, z + d), code):
            return z + d
    return None


def app_einschalten(geheimnis):
    tresor.speichern(GEHEIM, geheimnis)
    tresor.loeschen(ZAEHLER)
    tresor.speichern(ART, "app")
    return ersatz_neu()


def email_einschalten():
    tresor.loeschen(GEHEIM)
    tresor.loeschen(ZAEHLER)
    tresor.speichern(ART, "email")
    return ersatz_neu()


# ---------------- Ersatz-Codes ----------------
def _norm(code):
    return "".join(ch for ch in str(code).lower() if ch.isalnum())


def _h(code):
    return hashlib.sha256(("watson-ersatz:" + _norm(code)).encode()).hexdigest()


def ersatz_neu():
    """10 neue Ersatz-Codes (die alten werden ungültig). Gespeichert wird nur ein Fingerabdruck (Hash) davon."""
    codes = ["".join(secrets.choice(ERSATZ_ZEICHEN) for _ in range(8)) for _ in range(10)]
    codes = [c[:4] + "-" + c[4:] for c in codes]
    tresor.speichern(ERSATZ, json.dumps([_h(c) for c in codes]))
    return codes


def _ersatz_einloesen(code):
    if len(_norm(code)) != 8:
        return False
    try:
        liste = json.loads(tresor.lesen(ERSATZ) or "[]")
    except ValueError:
        return False
    h = _h(code)
    for x in liste:
        if hmac.compare_digest(x, h):
            liste.remove(x)
            tresor.speichern(ERSATZ, json.dumps(liste)) if liste else tresor.loeschen(ERSATZ)
            return True
    return False


# ---------------- E-Mail-Code ----------------
def mail_code():
    """Neuer 6-stelliger Code + sein Hash (nur der Hash wird gemerkt)."""
    c = "%06d" % secrets.randbelow(1_000_000)
    return c, hashlib.sha256(c.encode()).hexdigest()


def mail_code_passt(code, gemerkter_hash):
    code = "".join(ch for ch in str(code) if ch.isdigit())
    return bool(gemerkter_hash) and len(code) == 6 and \
        hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(), gemerkter_hash)


# ---------------- Prüfen bei der Anmeldung ----------------
def pruefen(code, mail_hash=None):
    """Prüft den zweiten Schritt. Gibt 'app', 'email', 'ersatz' oder '' (falsch) zurück."""
    with SPERRE:
        a = art()
        if a == "app":
            try:
                letzter = int(tresor.lesen(ZAEHLER) or -1)
            except ValueError:
                letzter = -1
            z = totp_pruefen(tresor.lesen(GEHEIM), code, letzter)
            if z is not None:
                tresor.speichern(ZAEHLER, str(z))          # derselbe Code gilt kein zweites Mal
                return "app"
        if a == "email" and mail_code_passt(code, mail_hash):
            return "email"
        if a and _ersatz_einloesen(code):
            return "ersatz"
        return ""


def mail_maskiert(adresse):
    """anna@example.com -> a•••@example.com (fürs Anzeigen)."""
    if "@" not in (adresse or ""):
        return ""
    name, dom = adresse.split("@", 1)
    return name[:1] + "•" * max(2, len(name) - 1) + "@" + dom
