"""
System-Werkzeuge für Watson: Windows-Auskunft (nur lesen) und PowerShell (streng bewacht).

Regeln:
- Beide Werkzeuge gibt es nur, wenn der Nutzer sie eingeschaltet hat (Einstellung „use_system“).
- Vor JEDER Nutzung fragt Watson um Erlaubnis und erklärt kurz, was er tun will und warum
  (das erledigt watson_studio._allowed – unabhängig von der Vertrauensstufe).
- PowerShell läuft ohne Administratorrechte, mit Zeitgrenze; gefährliche Befehle sind gesperrt.
"""
import os
import re
import subprocess

TIMEOUT = 60
MAX_AUSGABE = 8000

# ---------------- System-Auskunft: feste, nur lesende Abfragen ----------------
# {filter} wird NIE in den Befehl eingesetzt, sondern als Umgebungsvariable $env:WATSON_FILTER übergeben.
ABFRAGEN = {
    "system_info": ("Windows-Version, Gerät, Arbeitsspeicher, Laufzeit seit Neustart",
                    "$o=Get-CimInstance Win32_OperatingSystem; $c=Get-CimInstance Win32_ComputerSystem; "
                    "[pscustomobject]@{Windows=$o.Caption; Version=$o.Version; Build=$o.BuildNumber; "
                    "Geraet=\"$($c.Manufacturer) $($c.Model)\"; RAM_GB=[math]::Round($c.TotalPhysicalMemory/1GB,1); "
                    "Frei_RAM_GB=[math]::Round($o.FreePhysicalMemory/1MB,1); "
                    "Laeuft_seit=(Get-Date)-$o.LastBootUpTime} | Format-List | Out-String -Width 200"),
    "windows_update": ("Letzte installierte Updates und ob ein Neustart aussteht",
                       "$n=(Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired'); "
                       "\"Neustart ausstehend: $n\"; Get-HotFix | Sort-Object InstalledOn -Descending | "
                       "Select-Object -First 15 HotFixID,Description,InstalledOn | Format-Table -AutoSize | Out-String -Width 200"),
    "updates_installiert": ("Alle installierten Windows-Updates (Hotfixes)",
                            "Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object HotFixID,Description,InstalledOn "
                            "| Format-Table -AutoSize | Out-String -Width 200"),
    "dienste": ("Windows-Dienste (Filter: Teil des Namens, optional)",
                "$f=$env:WATSON_FILTER; Get-Service | Where-Object { -not $f -or $_.Name -like \"*$f*\" -or $_.DisplayName -like \"*$f*\" } "
                "| Sort-Object Status,Name | Select-Object -First 80 Status,Name,DisplayName,StartType | Format-Table -AutoSize | Out-String -Width 200"),
    "speicherplatz": ("Freier und belegter Speicher aller Laufwerke",
                      "Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{n='Belegt_GB';e={[math]::Round($_.Used/1GB,1)}},"
                      "@{n='Frei_GB';e={[math]::Round($_.Free/1GB,1)}},Root | Format-Table -AutoSize | Out-String"),
    "akku": ("Akkustand und Ladezustand",
             "Get-CimInstance Win32_Battery | Select-Object Name,EstimatedChargeRemaining,EstimatedRunTime,BatteryStatus "
             "| Format-List | Out-String"),
    "netzwerk": ("Netzwerkverbindungen, IP-Adressen und WLAN",
                 "Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object Name,InterfaceDescription,LinkSpeed | Format-Table -AutoSize | Out-String -Width 220; "
                 "Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -notlike '169.*' | Select-Object InterfaceAlias,IPAddress | Format-Table -AutoSize | Out-String; "
                 "netsh wlan show interfaces | Select-String 'SSID|Signal|Status|State' | Out-String"),
    "programme_laufend": ("Laufende Programme mit dem meisten Arbeitsspeicher (Filter optional)",
                          "$f=$env:WATSON_FILTER; Get-Process | Where-Object { -not $f -or $_.ProcessName -like \"*$f*\" } | "
                          "Sort-Object WorkingSet64 -Descending | Select-Object -First 30 ProcessName,Id,"
                          "@{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB)}},@{n='CPU_s';e={[math]::Round($_.CPU,1)}} | Format-Table -AutoSize | Out-String"),
    "programme_installiert": ("Installierte Programme mit Version (Filter optional)",
                              "$f=$env:WATSON_FILTER; $p='HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
                              "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
                              "'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; "
                              "Get-ItemProperty $p -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -and (-not $f -or $_.DisplayName -like \"*$f*\") } | "
                              "Sort-Object DisplayName -Unique | Select-Object -First 150 DisplayName,DisplayVersion,Publisher | Format-Table -AutoSize | Out-String -Width 200"),
    "autostart": ("Programme, die beim Hochfahren automatisch starten",
                  "Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location | Format-Table -AutoSize | Out-String -Width 220"),
    "fehler_ereignisse": ("Fehler und kritische Ereignisse im Windows-Protokoll der letzten 24 Stunden",
                          "Get-WinEvent -FilterHashtable @{LogName='System','Application'; Level=1,2; StartTime=(Get-Date).AddDays(-1)} "
                          "-MaxEvents 25 -ErrorAction SilentlyContinue | Select-Object TimeCreated,ProviderName,Id,"
                          "@{n='Meldung';e={($_.Message -split \"`n\")[0]}} | Format-Table -AutoSize -Wrap | Out-String -Width 220"),
    "virenschutz": ("Status von Microsoft Defender",
                    "Get-MpComputerStatus | Select-Object AMServiceEnabled,AntivirusEnabled,RealTimeProtectionEnabled,"
                    "AntivirusSignatureLastUpdated,QuickScanEndTime,FullScanEndTime | Format-List | Out-String"),
    "firewall": ("Status der Windows-Firewall",
                 "Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction | Format-Table -AutoSize | Out-String"),
    "registry_lesen": ("Einen Registry-Schlüssel LESEN (Filter = Pfad, z. B. HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion)",
                       "$f=$env:WATSON_FILTER; if (-not $f) { 'Bitte einen Registry-Pfad als Filter angeben.' } else { "
                       "Get-ItemProperty -LiteralPath $f -ErrorAction Stop | Select-Object * -ExcludeProperty PS* | Format-List | Out-String -Width 200 }"),
    "drucker": ("Installierte Drucker und Standarddrucker",
                "Get-CimInstance Win32_Printer | Select-Object Name,Default,WorkOffline,PrinterStatus | Format-Table -AutoSize | Out-String"),
}

SYSTEM_TOOL = {"type": "function", "function": {
    "name": "watson__system_auskunft",
    "description": "Fragt Informationen aus Windows ab (NUR LESEN, verändert nichts). Mögliche Abfragen: " +
                   "; ".join(f"{k} = {v[0]}" for k, v in ABFRAGEN.items()) +
                   ". Der Nutzer wird vorher um Erlaubnis gefragt.",
    "parameters": {"type": "object", "properties": {
        "abfrage": {"type": "string", "enum": list(ABFRAGEN), "description": "Welche Abfrage"},
        "filter": {"type": "string", "description": "Optional: Suchwort (z. B. Teil eines Dienst- oder Programmnamens) "
                                                    "oder bei registry_lesen der Pfad"},
        "erklaerung": {"type": "string", "description": "PFLICHT: In ein bis zwei einfachen Sätzen für den Nutzer, was du "
                                                        "nachsehen willst und warum."}},
        "required": ["abfrage", "erklaerung"]}}}

POWERSHELL_TOOL = {"type": "function", "function": {
    "name": "watson__powershell",
    "description": "Führt EINEN PowerShell-Befehl auf dem Computer des Nutzers aus (ohne Administratorrechte, höchstens 60 Sekunden). "
                   "Nur benutzen, wenn watson__system_auskunft nicht reicht. Gefährliche Befehle (Löschen, Formatieren, "
                   "Registry ändern, Benutzer/Rechte, Sicherheit abschalten, Herunterladen und Ausführen) sind gesperrt. "
                   "Der Nutzer wird vor JEDEM Befehl gefragt und sieht den genauen Befehl.",
    "parameters": {"type": "object", "properties": {
        "befehl": {"type": "string", "description": "Der PowerShell-Befehl"},
        "erklaerung": {"type": "string", "description": "PFLICHT: In ein bis zwei einfachen Sätzen für den Nutzer, was der "
                                                        "Befehl tut und warum du ihn brauchst."}},
        "required": ["befehl", "erklaerung"]}}}

TOOLS = [SYSTEM_TOOL, POWERSHELL_TOOL]
NAMES = {SYSTEM_TOOL["function"]["name"], POWERSHELL_TOOL["function"]["name"]}

HINWEIS = ("\n\nSYSTEM-WERKZEUGE: Du kannst Windows-Informationen mit watson__system_auskunft abfragen (nur lesen) "
           "und, wenn das nicht reicht, einzelne PowerShell-Befehle mit watson__powershell ausführen. Der Nutzer wird vor "
           "JEDER Nutzung gefragt. Gib im Feld „erklaerung“ immer kurz und verständlich an, was du tust und warum. "
           "Nimm lieber die System-Auskunft als PowerShell. Verändere nichts, worum der Nutzer nicht gebeten hat.")

# ---------------- PowerShell: Sperrliste ----------------
GESPERRT = [
    (r"\b(remove-item|rm|rmdir|del|erase|rd|ri)\b", "Löschen von Dateien oder Ordnern"),
    (r"\bclear-(content|item|recyclebin|disk)\b", "Inhalte oder Datenträger leeren"),
    (r"\bformat-volume\b|(^|[;|&\s])format(\.com)?\s+[a-z]:|\b(diskpart|clear-disk|initialize-disk|remove-partition|new-partition|set-partition|resize-partition)\b", "Datenträger formatieren oder partitionieren"),
    (r"\b(set|new|remove|rename|copy|move)-itemproperty\b|\breg(\.exe)?\s+(add|delete|import|copy|restore|load|unload)\b", "Registry verändern"),
    (r"\b(stop|restart)-computer\b|\bshutdown(\.exe)?\b|\blogoff\b", "Herunterfahren oder Neustarten"),
    (r"\b(new|remove|set|enable|disable|rename)-localuser\b|\b(add|remove)-localgroupmember\b|\bnet(1)?\s+(user|localgroup)\b", "Benutzer oder Gruppen ändern"),
    (r"\bset-mppreference\b|\badd-mppreference\b|\bset-netfirewall|\bnew-netfirewallrule\b|\bdisable-netfirewall|\bnetsh\s+(advfirewall|firewall)\b", "Virenschutz oder Firewall ändern"),
    (r"\bset-executionpolicy\b|\bbcdedit\b|\bvssadmin\b|\bwbadmin\b|\bcipher\b|\btakeown\b|\bicacls\b|\bcacls\b|\bset-acl\b", "Sicherheits- oder Systemeinstellungen ändern"),
    (r"\b(invoke-webrequest|iwr|invoke-restmethod|irm|curl|wget|start-bitstransfer|bitsadmin|certutil)\b|net\.webclient|downloadstring|downloadfile", "Aus dem Internet herunterladen"),
    (r"\b(invoke-expression|iex)\b|-enc(odedcommand)?\b|frombase64string|\[scriptblock\]::create|add-type", "Versteckten oder nachgeladenen Code ausführen"),
    (r"-verb\s+runas\b|\bstart-process\b[^|;]*-verb\b|\brunas(\.exe)?\b", "Mit Administratorrechten starten"),
    (r"\b(register-scheduledtask|unregister-scheduledtask|set-scheduledtask|schtasks)\b", "Geplante Aufgaben ändern"),
    (r"\b(stop|remove|set|new)-service\b|\bsc(\.exe)?\s+(stop|delete|config|create)\b", "Dienste ändern oder beenden"),
    (r"\bstop-process\b|\bkill\b|\btaskkill\b", "Programme gewaltsam beenden"),
    (r"\b(uninstall-package|uninstall-module|remove-appxpackage|winget\s+uninstall|msiexec)\b", "Programme deinstallieren oder installieren"),
    (r"\bsend-mailmessage\b|\bout-printer\b", "Nachrichten versenden oder drucken"),
    (r"\b(credential|get-credential|convertfrom-securestring|cmdkey|vaultcmd)\b|\\\.ssh\b|keyring|tresor", "Zugangsdaten auslesen"),
]


def befehl_pruefen(befehl):
    """Gibt den Sperrgrund zurück oder None, wenn der Befehl erlaubt ist."""
    b = (befehl or "").strip()
    if not b:
        return "Leerer Befehl."
    if len(b) > 2000:
        return "Der Befehl ist zu lang."
    klein = b.lower()
    for muster, grund in GESPERRT:
        if re.search(muster, klein):
            return f"Gesperrt: {grund}."
    return None


def _ausfuehren(skript, filter_wert=""):
    env = dict(os.environ)
    env["WATSON_FILTER"] = str(filter_wert or "")[:300]
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; " + skript],
                           capture_output=True, timeout=TIMEOUT, env=env, stdin=subprocess.DEVNULL,
                           creationflags=0x08000000)       # kein Fenster
    except subprocess.TimeoutExpired:
        return f"Abgebrochen: Der Befehl hat länger als {TIMEOUT} Sekunden gebraucht."
    except OSError as e:
        return f"PowerShell konnte nicht gestartet werden: {e}"
    aus = (r.stdout or b"").decode("utf-8", "replace").strip()
    fehler = (r.stderr or b"").decode("utf-8", "replace").strip()
    text = aus + (("\n\nFehlermeldung:\n" + fehler) if fehler else "")
    text = text or "(keine Ausgabe)"
    if len(text) > MAX_AUSGABE:
        text = text[:MAX_AUSGABE] + f"\n… (gekürzt, insgesamt {len(text)} Zeichen)"
    return text


def run(name, args):
    if name == SYSTEM_TOOL["function"]["name"]:
        a = ABFRAGEN.get(str(args.get("abfrage") or ""))
        if not a:
            return "Unbekannte Abfrage. Möglich: " + ", ".join(ABFRAGEN)
        return _ausfuehren(a[1], args.get("filter", ""))
    if name == POWERSHELL_TOOL["function"]["name"]:
        befehl = str(args.get("befehl") or "")
        grund = befehl_pruefen(befehl)
        if grund:
            return grund + " Dieser Befehl ist für Watson aus Sicherheitsgründen nicht erlaubt. Erkläre dem Nutzer, wie er es selbst tun kann."
        return _ausfuehren(befehl)
    return "Unbekanntes Werkzeug."


def frage_text(name, args):
    """Titel und Text für die Erlaubnis-Frage an den Nutzer."""
    erkl = str(args.get("erklaerung") or "").strip()[:600] or "(Watson hat keine Erklärung angegeben.)"
    if name == SYSTEM_TOOL["function"]["name"]:
        a = ABFRAGEN.get(str(args.get("abfrage") or ""), ("unbekannte Abfrage", ""))
        filt = str(args.get("filter") or "").strip()
        return ("🖥 Watson möchte Windows-Informationen abfragen",
                f"{erkl}\n\nAbfrage: {a[0]}" + (f"\nSuchwort/Pfad: {filt}" if filt else "") +
                "\n\nNur lesen – es wird nichts verändert.", "frage")
    befehl = str(args.get("befehl") or "")
    grund = befehl_pruefen(befehl)
    return ("⌨ Watson möchte einen PowerShell-Befehl ausführen",
            f"{erkl}\n\nBefehl:\n{befehl[:1200]}" +
            (f"\n\n⛔ {grund} Watson darf ihn nicht ausführen." if grund else
             "\n\nLäuft ohne Administratorrechte, höchstens 60 Sekunden. Prüfe den Befehl, bevor du erlaubst."),
            "kritisch")
