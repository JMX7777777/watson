"""
Watsons Schlüsseltresor.

- Die Schlüssel liegen VERSCHLÜSSELT in der Windows-Anmeldeinformationsverwaltung (über „keyring“),
  gebunden an das Windows-Konto – nicht mehr als lesbarer Text in einstellungen.json.
- Ansehen, Ändern und Löschen nur nach Windows Hello (Fingerabdruck, Gesicht, PIN oder Passwort).
- In einstellungen.json stehen nur noch die NAMEN der Schlüssel, nie die Schlüssel selbst.
"""
import ctypes
import time
import uuid
from ctypes import POINTER, byref, c_int, c_void_p, wintypes

import keyring

SERVICE = "Watson"
# Schlüssel, die Watson kennt: Kennung -> Anzeigename
BEKANNT = {"api_key": "OpenRouter (Gehirne)", "n8n_api_key": "n8n (Abläufe)"}


# ---------------- Tresor ----------------
def lesen(kennung):
    try:
        return keyring.get_password(SERVICE, kennung) or ""
    except Exception:
        return ""


def speichern(kennung, wert):
    wert = (wert or "").strip()
    if wert:
        keyring.set_password(SERVICE, kennung, wert)
    else:
        loeschen(kennung)


def loeschen(kennung):
    try:
        keyring.delete_password(SERVICE, kennung)
    except Exception:
        pass


def vorhanden(kennung):
    return bool(lesen(kennung))


# ---------------- Windows Hello ----------------
_IID_INTEROP = "39E050C3-4E74-441A-8DC0-B81104DF949C"          # IUserConsentVerifierInterop
_IID_ASYNC_OP = "FD596FFD-2318-558F-9DBE-D21DF43764A5"         # IAsyncOperation<UserConsentVerificationResult>
_IID_INSPECTABLE = "AF86E2E0-B12D-4C6A-9C5A-D7AA65101E90"
_IID_ASYNC_INFO = "00000036-0000-0000-C000-000000000046"
ERGEBNIS = {0: "bestätigt", 1: "kein Gerät für Windows Hello", 2: "Windows Hello ist nicht eingerichtet",
            3: "durch Richtlinie gesperrt", 4: "Gerät ist beschäftigt", 5: "zu viele Fehlversuche", 6: "abgebrochen"}


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]


def _guid(s):
    return _GUID.from_buffer_copy(uuid.UUID(s).bytes_le)


def _vt(obj, index, *argtypes):
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    return ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtbl[index])


def _release(obj):
    if obj:
        ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0][2])(obj)


def _find_window(title="Watson"):
    u = ctypes.windll.user32
    u.FindWindowW.restype = c_void_p
    return u.FindWindowW(None, title)


def hello(grund, hwnd=None, timeout=120):
    """Fragt Windows Hello (Fingerabdruck/Gesicht/PIN/Passwort). Gibt (ok, text) zurück.
    Das Fenster erscheint direkt vor dem Watson-Fenster."""
    combase = ctypes.windll.combase
    combase.RoInitialize(1)                      # schon initialisiert? Dann egal.
    hwnd = hwnd or _find_window()
    cls = "Windows.Security.Credentials.UI.UserConsentVerifier"
    h_cls, h_msg = c_void_p(), c_void_p()
    combase.WindowsCreateString(ctypes.c_wchar_p(cls), len(cls), byref(h_cls))
    combase.WindowsCreateString(ctypes.c_wchar_p(grund), len(grund), byref(h_msg))
    factory, op, info = c_void_p(), c_void_p(), c_void_p()
    try:
        iid = _guid(_IID_INTEROP)
        hr = combase.RoGetActivationFactory(h_cls, byref(iid), byref(factory))
        if hr != 0 or not factory:
            return False, "Windows Hello ist auf diesem Gerät nicht verfügbar."
        request = _vt(factory, 6, wintypes.HWND, c_void_p, POINTER(_GUID), POINTER(c_void_p))
        hr = request(factory, hwnd, h_msg, byref(_guid(_IID_ASYNC_OP)), byref(op))
        if hr != 0:
            hr = request(factory, hwnd, h_msg, byref(_guid(_IID_INSPECTABLE)), byref(op))
        if hr != 0 or not op:
            return False, f"Windows Hello konnte nicht gestartet werden (Fehler {hr & 0xFFFFFFFF:#x})."
        _vt(op, 0, POINTER(_GUID), POINTER(c_void_p))(op, byref(_guid(_IID_ASYNC_INFO)), byref(info))
        get_status = _vt(info, 7, POINTER(c_int))
        status, t0 = c_int(0), time.time()
        while True:
            get_status(info, byref(status))
            if status.value != 0:
                break
            if time.time() - t0 > timeout:
                _vt(info, 9)(info)               # Cancel
                return False, "Zeit abgelaufen."
            time.sleep(0.15)
        if status.value != 1:
            return False, "abgebrochen"
        result = c_int(-1)
        _vt(op, 8, POINTER(c_int))(op, byref(result))   # GetResults
        return result.value == 0, ERGEBNIS.get(result.value, f"unbekannt ({result.value})")
    finally:
        _release(info)
        _release(op)
        _release(factory)
        combase.WindowsDeleteString(h_cls)
        combase.WindowsDeleteString(h_msg)


def hello_starten_und_abbrechen(hwnd=None):
    """Nur für Tests: startet die Abfrage und bricht sie sofort wieder ab (prüft, ob alles verbunden ist)."""
    combase = ctypes.windll.combase
    combase.RoInitialize(1)
    hwnd = hwnd or _find_window()
    cls = "Windows.Security.Credentials.UI.UserConsentVerifier"
    msg = "Watson-Test"
    h_cls, h_msg = c_void_p(), c_void_p()
    combase.WindowsCreateString(ctypes.c_wchar_p(cls), len(cls), byref(h_cls))
    combase.WindowsCreateString(ctypes.c_wchar_p(msg), len(msg), byref(h_msg))
    factory, op, info = c_void_p(), c_void_p(), c_void_p()
    hr = combase.RoGetActivationFactory(h_cls, byref(_guid(_IID_INTEROP)), byref(factory))
    if hr:
        return f"Fabrik-Fehler {hr & 0xFFFFFFFF:#x}"
    req = _vt(factory, 6, wintypes.HWND, c_void_p, POINTER(_GUID), POINTER(c_void_p))
    hr = req(factory, hwnd, h_msg, byref(_guid(_IID_ASYNC_OP)), byref(op))
    which = "IAsyncOperation"
    if hr:
        which = f"IInspectable (IAsyncOperation-Fehler {hr & 0xFFFFFFFF:#x})"
        hr = req(factory, hwnd, h_msg, byref(_guid(_IID_INSPECTABLE)), byref(op))
    if hr:
        return f"Start-Fehler {hr & 0xFFFFFFFF:#x}"
    _vt(op, 0, POINTER(_GUID), POINTER(c_void_p))(op, byref(_guid(_IID_ASYNC_INFO)), byref(info))
    time.sleep(1.5)
    st = c_int(-1)
    _vt(info, 7, POINTER(c_int))(info, byref(st))
    _vt(info, 9)(info)
    time.sleep(0.5)
    st2 = c_int(-1)
    _vt(info, 7, POINTER(c_int))(info, byref(st2))
    _release(info); _release(op); _release(factory)
    return f"gestartet über {which}, Status vorher {st.value} (0=läuft), nach Abbruch {st2.value} (2=abgebrochen)"
