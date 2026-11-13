"""
Gerätetest: Kann dieser Computer Watsons eigene Stimme (omnivoice.cpp, Stimm-Klon) gut rechnen?
Ergebnis in drei Stufen:  "gut" (sehr gut)  ·  "mittel" (geht, aber mit Wartezeit)  ·  "nein" (geht nicht).
Alles lokal und lautlos: misst Prozessor, Arbeitsspeicher, freien Platz, Linux-Bereich (WSL) und ein kurzes Rechentempo.
Aufruf zum Ausprobieren:  python geraetetest.py
"""
import ctypes
import os
import platform
import shutil
import subprocess
import time

import numpy as np

# Bezugswert: Entwickler-Laptop (Snapdragon X Plus, 8 Kerne, 24 GB) – gemessen 09.11.2026.
# Dort braucht omnivoice.cpp etwa 3 Sekunden Rechenzeit pro Sekunde Sprache (8 Schritte, 5-s-Stimmprobe).
# Achtung, ehrlich: Dieser Rechentest ist nur eine grobe Vorab-Schätzung (gemessen mit Watsons Python, das auf
# Entwickler-Laptop (ARM) emuliert läuft). Die sichere Antwort gibt erst echttest() mit der eingerichteten Stimme.
REF_TEMPO = 426.0         # GFLOPS auf dem Entwickler-Laptop, 09.11.2026
REF_SEK_PRO_SEK = 3.0

# Grenzen (Sekunden Rechenzeit pro Sekunde Sprache). Der Entwickler-Laptop misst 2,6–4,1 und ist "sehr gut".
GUT = 5
MITTEL = 12
PLATZ_GB = 4              # Ubuntu-Werkzeuge, Quellcode, Bau, Modelle (~1 GB) mit Reserve
KEIN = 0x08000000         # kein Konsolenfenster öffnen


def _ram_gb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS(); m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys / 1024 ** 3


def _cpu_name():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except Exception:
        return platform.processor() or "unbekannt"


def _arch():
    """Echte Prozessor-Art von Windows (nicht die der Python-Umgebung, die auf ARM-Laptops emuliert sein kann)."""
    a = ""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
        a = winreg.QueryValueEx(k, "PROCESSOR_ARCHITECTURE")[0]
    except Exception:
        pass
    a = (a or os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or "").upper()
    return {"AMD64": "x64", "ARM64": "ARM64", "X86": "32-Bit"}.get(a, a or "unbekannt")


def _wsl():
    """(eingerichtet, Text). Nur lesen – es wird nichts installiert oder geändert."""
    if not shutil.which("wsl.exe"):
        return False, "Der Linux-Bereich (WSL) ist noch nicht eingerichtet."
    try:
        out = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=20, creationflags=KEIN).stdout
        namen = [n.strip() for n in out.decode("utf-16-le", "ignore").replace("\x00", "").splitlines() if n.strip()]
    except Exception:
        namen = []
    if any("ubuntu" in n.lower() for n in namen):
        return True, "Linux-Bereich ist da: " + ", ".join(namen)
    if namen:
        return False, "Linux-Bereich ist da, aber noch ohne Ubuntu (" + ", ".join(namen) + ")."
    return False, "Der Linux-Bereich (WSL) ist noch nicht eingerichtet."


def _virtualisierung():
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_ComputerSystem).HypervisorPresent;"
                              "(Get-CimInstance Win32_Processor | Select -First 1).VirtualizationFirmwareEnabled"],
                             capture_output=True, text=True, timeout=30, creationflags=KEIN).stdout.split()
        return "True" in out
    except Exception:
        return None


def _tempo(sekunden=2.0):
    """Kurzer Rechentest (Matrix-Rechnung, alle Kerne). Ergebnis in GFLOPS – nur eine grobe Schätzung."""
    n = 768
    a = np.random.rand(n, n).astype(np.float32)
    b = np.random.rand(n, n).astype(np.float32)
    a @ b                                             # aufwärmen
    t0, runden = time.perf_counter(), 0
    while time.perf_counter() - t0 < sekunden:
        a @ b; runden += 1
    return 2 * n ** 3 * runden / (time.perf_counter() - t0) / 1e9


def pruefen():
    punkte = []          # (ok: True/False/None, Text)
    harte_grenze = False

    arch, kerne, ram = _arch(), os.cpu_count() or 1, _ram_gb()
    frei = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\").free / 1024 ** 3
    build = int((platform.version().split(".") + ["0", "0", "0"])[2] or 0)

    punkte.append((None, f"Prozessor: {_cpu_name()} ({arch}, {kerne} Kerne)"))
    if arch == "32-Bit":
        punkte.append((False, "32-Bit-Windows: dafür gibt es den Linux-Bereich nicht.")); harte_grenze = True
    if kerne < 4:
        punkte.append((False, f"Nur {kerne} Kerne – mindestens 4 nötig.")); harte_grenze = True

    ok = ram >= 16
    punkte.append((ok if ram >= 8 else False, f"Arbeitsspeicher: {ram:.0f} GB "
                   + ("(sehr gut)" if ok else "(reicht knapp)" if ram >= 8 else "(zu wenig, mindestens 8 GB)")))
    harte_grenze |= ram < 7.5

    punkte.append((frei >= PLATZ_GB, f"Freier Platz auf Laufwerk C: {frei:.0f} GB (nötig etwa {PLATZ_GB} GB)"))
    harte_grenze |= frei < PLATZ_GB

    if build and build < 19041:
        punkte.append((False, "Windows ist zu alt für den Linux-Bereich (WSL 2). Bitte Windows aktualisieren."))
        harte_grenze = True

    wsl_ok, wsl_text = _wsl()
    punkte.append((True if wsl_ok else None, wsl_text + ("" if wsl_ok else " (lässt sich einrichten – siehe Anleitung, Schritt 1)")))
    if not wsl_ok:
        v = _virtualisierung()
        if v is False:
            punkte.append((False, "Virtualisierung ist im BIOS/UEFI ausgeschaltet. Ohne sie läuft der Linux-Bereich nicht. "
                                  "Einschalten kann man sie nur selbst beim Starten des Computers (Anleitung, Hinweis)."))

    gflops = _tempo()
    ref = REF_TEMPO or gflops
    sek_pro_sek = REF_SEK_PRO_SEK * ref / max(gflops, 0.1)
    antwort = 8 * sek_pro_sek                       # typische Antwort: 2 Sätze ≈ 8 s Sprache
    punkte.append((sek_pro_sek <= GUT if sek_pro_sek <= MITTEL else False,
                   f"Rechentempo: {gflops:.0f} GFLOPS → geschätzt {sek_pro_sek:.0f} s Rechenzeit pro Sekunde Sprache "
                   f"(eine Antwort aus 2 Sätzen ≈ {antwort:.0f} s Wartezeit)"))

    if harte_grenze or sek_pro_sek > MITTEL:
        stufe = "nein"
    elif sek_pro_sek <= GUT and ram >= 15.5:
        stufe = "gut"
    else:
        stufe = "mittel"

    titel = {"gut": "✅ Sehr gut – die eigene Stimme läuft flüssig auf diesem Gerät.",
             "mittel": "🟡 Mittel – die eigene Stimme geht, aber mit spürbarer Wartezeit.",
             "nein": "❌ Geht leider nicht gut – besser die eingebauten Stimmen (Thorsten/Kerstin) nutzen."}[stufe]
    hinweis = ("Das ist eine Vorab-Schätzung. Sicher ist es erst nach dem Echttest (Anleitung, Schritt 4).")
    if arch != "ARM64":
        hinweis += (" Außerdem ehrlich: Getestet wurde die eigene Stimme bisher nur auf einem ARM-Laptop (Snapdragon). "
                    "Auf diesem Prozessor-Typ sollte es genauso gehen, ist aber noch nicht ausprobiert.")
    return {"stufe": stufe, "titel": titel, "punkte": punkte, "gflops": round(gflops, 1),
            "sek_pro_sek": round(sek_pro_sek, 1), "hinweis": hinweis, "arch": arch, "art": "schaetzung"}


def _stufe_aus_tempo(sek_pro_sek):
    return "gut" if sek_pro_sek <= GUT else "mittel" if sek_pro_sek <= MITTEL else "nein"


def echttest():
    """Zweite Stufe, nach der Einrichtung: einen echten Satz mit der eigenen Stimme rechnen und die Zeit messen.
    Lautlos – es wird nichts abgespielt."""
    import stimme
    satz = "Ich prüfe gerade, wie schnell dieser Computer mit meiner eigenen Stimme sprechen kann."
    try:
        if not stimme.Mund._ov_bereit():
            return {"stufe": None, "titel": "Der Sprachdienst startet nicht. Ist die Einrichtung (Anleitung, Schritt 2) fertig?"}
        stimme.Mund._synth_omnivoice("Kurzer Probelauf.")      # erster Lauf lädt alles – nicht mitzählen
        t0 = time.perf_counter()
        audio, rate = stimme.Mund._synth_omnivoice(satz)
        dauer = time.perf_counter() - t0
    except Exception as e:
        return {"stufe": None, "titel": f"Echttest fehlgeschlagen: {e}"}
    sprache = len(audio) / rate
    sps = dauer / max(sprache, 0.1)
    stufe = _stufe_aus_tempo(sps)
    titel = {"gut": "✅ Echttest: sehr gut.", "mittel": "🟡 Echttest: mittel – es geht, mit Wartezeit.",
             "nein": "❌ Echttest: zu langsam für Gespräche."}[stufe]
    return {"stufe": stufe, "titel": titel, "art": "echt", "sek_pro_sek": round(sps, 1),
            "punkte": [(None, f"{sprache:.1f} s Sprache in {dauer:.0f} s gerechnet → {sps:.1f} s pro Sekunde Sprache "
                              f"(eine Antwort aus 2 Sätzen ≈ {8 * sps:.0f} s Wartezeit)")]}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    e = echttest() if "--echt" in sys.argv else pruefen()
    print(e["titel"])
    for ok, t in e.get("punkte", []):
        print({True: "  ✔", False: "  ✘", None: "  •"}[ok], t)
    if e.get("hinweis"):
        print(" ", e["hinweis"])
