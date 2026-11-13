# Baut die saubere GitHub-Kopie von Watson in C:\Users\<Name>\Watson-GitHub
# Nimmt NUR eine feste Liste von Programmdateien mit (nie Einstellungen, Gespräche, Gedächtnis, Stimme, Schlüssel)
# und prüft danach alles auf Geheimnisse und persönliche Angaben. Bricht bei einem Fund ab.
param([string]$Ziel = (Join-Path $env:USERPROFILE "Watson-GitHub"))
$ErrorActionPreference = "Stop"
$Watson = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Studio = Join-Path $Watson "studio"
$utf8 = New-Object System.Text.UTF8Encoding($false)

# Alles außer dem Git-Ordner leeren (damit gelöschte Dateien auch auf GitHub verschwinden)
New-Item -ItemType Directory -Force $Ziel | Out-Null
Get-ChildItem $Ziel -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force

function Kopie($quelle, $ziel) { New-Item -ItemType Directory -Force (Split-Path -Parent $ziel) | Out-Null; Copy-Item $quelle $ziel -Force }

# 1) Programm (studio)
$ohne = "^(test|system_test|internet_test)"     # einmalige Testprogramme nicht
Get-ChildItem $Studio -Filter *.py | Where-Object { $_.Name -notmatch $ohne } | ForEach-Object { Kopie $_.FullName (Join-Path $Ziel "studio\$($_.Name)") }
foreach ($d in "app.html", "handy.html", "i18n.js", "i18n_en.json", "ANLEITUNG-HANDY.md", "mcp-vorlage.json", "requirements.txt", "ablaeufe\watson-test.json") {
    Kopie (Join-Path $Studio $d) (Join-Path $Ziel "studio\$d") }
foreach ($ordner in "assets", "eigene-stimme") {         # mit Unterordnern (z. B. assets\fonts)
    $basis = Join-Path $Studio $ordner
    Get-ChildItem $basis -File -Recurse | ForEach-Object { Kopie $_.FullName (Join-Path $Ziel ("studio\$ordner\" + $_.FullName.Substring($basis.Length + 1))) } }
# 2) Installer
foreach ($d in "setup.ps1", "bauen.ps1", "deinstallieren.ps1", "starter.cs", "starter.manifest") {
    Kopie (Join-Path $Watson "installer\$d") (Join-Path $Ziel "installer\$d") }
# 3) Werkzeuge für Entwickler
foreach ($d in "i18n_bauen.py", "i18n_texte.py", "i18n_kern.js", "jslex.py", "github_export.ps1") {
    Kopie (Join-Path $Watson "werkzeuge\$d") (Join-Path $Ziel "werkzeuge\$d") }
Kopie (Join-Path $Watson "n8n-linux\installieren.sh") (Join-Path $Ziel "n8n-linux\installieren.sh")
# 4) Texte fürs Projekt (liegen in werkzeuge\github\)
Get-ChildItem (Join-Path $Watson "werkzeuge\github") -File -Force | ForEach-Object { Copy-Item $_.FullName (Join-Path $Ziel $_.Name) -Force }

# ---------------- Prüfung: Geheimnisse und Persönliches ----------------
$muster = @(
    @("OpenRouter-Schlüssel", "sk-or-v1-[0-9a-f]{20,}"), @("GitHub-Token", "gh[opusr]_[A-Za-z0-9]{20,}|github_pat_"),
    @("privater Schlüssel", "-----BEGIN [A-Z ]*PRIVATE KEY"), @("Google-Schlüssel", "AIza[0-9A-Za-z_\-]{30,}"),
    @("Benutzerordner", "(?i)c:\\\\?users\\\\?[^\\\\\s""']+\\\\?watson"), @("Tailscale-Adresse", "(?i)\.tail[0-9a-f]{6}\.ts\.net"),
    @("E-Mail-Adresse", "[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|gmx|web|yahoo|icloud)\.[a-z]{2,}")
)
# Persönliche Suchmuster (eigener Name, Konto, Geräte …) stehen in einer PRIVATEN Datei, die nie hochgeladen wird:
# werkzeuge\github_privat.txt – eine Zeile pro Muster:  Bezeichnung<TAB>Regex
$privat = Join-Path $Watson "werkzeuge\github_privat.txt"
if (Test-Path $privat) {
    foreach ($z in Get-Content $privat -Encoding UTF8) { if ($z -match "^\s*#" -or -not $z.Contains("`t")) { continue }; $teile = $z.Split("`t", 2); $muster += , @($teile[0], $teile[1]) }
} else { "Hinweis: keine private Musterliste ($privat) – nur allgemeine Prüfung." }
$erlaubt = @()
$funde = @()
Get-ChildItem $Ziel -Recurse -File -Force | Where-Object { $_.FullName -notmatch '\\\.git\\' -and $_.Extension -notin ".png", ".ico", ".woff2" -and $_.Name -ne "github_export.ps1" } | ForEach-Object {
    $datei = $_; $text = [IO.File]::ReadAllText($datei.FullName)
    foreach ($m in $muster) {
        foreach ($t in [regex]::Matches($text, $m[1])) {
            $zeile = ($text.Substring(0, $t.Index) -split "`n").Count
            $umfeld = $text.Substring([Math]::Max(0, $t.Index - 20), [Math]::Min(60, $text.Length - [Math]::Max(0, $t.Index - 20)))
            if ($erlaubt | Where-Object { $umfeld -like "*$_*" }) { continue }
            $funde += "{0}:{1}  [{2}]  {3}" -f $datei.FullName.Substring($Ziel.Length + 1), $zeile, $m[0], ($umfeld -replace "\s+", " ")
        }
    }
}
# Verbotene Dateien (falls doch etwas durchrutscht)
$verboten = "einstellungen.json", "watson.db", "protokoll.log", "mcp.json", "handy_passkeys.json", "handy_sitzungen.json",
            "lernbuch.json", "wissensbuch.json", "wachstum.json", "reparaturen.json", "vertrauen.json", "CLAUDE.md"
Get-ChildItem $Ziel -Recurse -File -Force | Where-Object { $verboten -contains $_.Name -or $_.Extension -in ".wav", ".db", ".log", ".m4a", ".mp3" } |
    ForEach-Object { $funde += "VERBOTENE DATEI: " + $_.FullName.Substring($Ziel.Length + 1) }

$anzahl = (Get-ChildItem $Ziel -Recurse -File -Force | Where-Object { $_.FullName -notmatch '\\\.git\\' }).Count
$mb = [Math]::Round(((Get-ChildItem $Ziel -Recurse -File -Force | Where-Object { $_.FullName -notmatch '\\\.git\\' } | Measure-Object Length -Sum).Sum) / 1MB, 1)
if ($funde) { "PRÜFUNG FEHLGESCHLAGEN – $($funde.Count) Fund(e):"; $funde; exit 1 }
"OK: $anzahl Dateien ($mb MB) in $Ziel – keine Geheimnisse, keine persönlichen Angaben gefunden."
