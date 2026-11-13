# Baut Watson-Setup.exe – nur mit Windows-Bordmitteln (Compress-Archive + eingebauter .NET-Compiler csc.exe).
# Nimmt NUR Programm-Dateien mit – keine Einstellungen, Gespräche, Schlüssel oder Gedächtnis.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Studio = Join-Path (Split-Path -Parent $Root) "studio"
$Bau = Join-Path $Root "bau"; $Prog = Join-Path $Bau "programm"; $Aus = Join-Path $Root "Ausgabe"
$Version = "1.0." + (Get-Date -Format "yyMMdd")
Remove-Item $Bau -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Prog, $Aus | Out-Null
$utf8bom = New-Object System.Text.UTF8Encoding($true)

# 1) Programm-Dateien einsammeln
Get-ChildItem $Studio -Filter *.py | Where-Object { $_.Name -notlike "test*" } | Copy-Item -Destination $Prog
"app.html", "handy.html", "i18n.js", "ANLEITUNG-HANDY.md", "mcp-vorlage.json", "requirements.txt" | ForEach-Object { Copy-Item (Join-Path $Studio $_) $Prog }
Copy-Item (Join-Path $Studio "assets") (Join-Path $Prog "assets") -Recurse
Copy-Item (Join-Path $Studio "eigene-stimme") (Join-Path $Prog "eigene-stimme") -Recurse   # Anleitung + Einrichtung eigene Stimme
[IO.File]::WriteAllText((Join-Path $Prog "deinstallieren.ps1"), [IO.File]::ReadAllText((Join-Path $Root "deinstallieren.ps1")), $utf8bom)
# Sicherheits-Prüfung: nichts Persönliches im Paket
$verboten = "einstellungen.json", "watson.db", "protokoll.log", "mcp.json"
$fund = Get-ChildItem $Prog -Recurse -File | Where-Object { $verboten -contains $_.Name }
if ($fund) { throw "Persönliche Datei im Paket gefunden: $($fund.Name -join ', ')" }
$text = (Get-ChildItem $Prog -Recurse -File -Include *.py, *.html, *.json, *.txt, *.ps1 | Get-Content -Raw) -join "`n"
if ($text -match "sk-or-v1-[0-9a-f]{20,}") { throw "Ein Schlüssel steckt im Programm-Code!" }
Compress-Archive -Path (Join-Path $Prog "*") -DestinationPath (Join-Path $Bau "watson-programm.zip") -Force
Remove-Item $Prog -Recurse -Force

# 2) uv (Python-Installer von Astral) – feste Version, Prüfsumme kontrolliert
$uvZip = Join-Path $Bau "uv.zip"
Invoke-WebRequest "https://github.com/astral-sh/uv/releases/download/0.13.5/uv-x86_64-pc-windows-msvc.zip" -OutFile $uvZip -UseBasicParsing
$hash = (Get-FileHash $uvZip -Algorithm SHA256).Hash.ToLower()
if ($hash -ne "a38b8d1902b7cfbc76b423ba1bb456f623f42064cdc72628b6075b89afd1019a") { throw "uv-Prüfsumme stimmt nicht: $hash" }
Expand-Archive $uvZip (Join-Path $Bau "uvtmp") -Force
Copy-Item (Get-ChildItem (Join-Path $Bau "uvtmp") -Recurse -Filter uv.exe | Select-Object -First 1).FullName (Join-Path $Bau "uv.exe")
Remove-Item $uvZip, (Join-Path $Bau "uvtmp") -Recurse -Force

# 3) Installer-Fenster + Logo + Version
[IO.File]::WriteAllText((Join-Path $Bau "setup.ps1"), [IO.File]::ReadAllText((Join-Path $Root "setup.ps1")), $utf8bom)
Copy-Item (Join-Path $Studio "assets\watson.ico"), (Join-Path $Studio "assets\watson-logo.png") $Bau
Set-Content (Join-Path $Bau "version.txt") $Version -Encoding ascii

# 4) Alles in eine Datei: payload.zip als Ressource in Watson-Setup.exe
$payload = Join-Path $Root "payload.zip"
Remove-Item $payload -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $Bau "*") -DestinationPath $payload -Force
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe" }
$target = Join-Path $Aus "Watson-Setup.exe"
Remove-Item $target -ErrorAction SilentlyContinue
Push-Location $Root
& $csc /nologo /target:winexe /optimize+ "/out:$target" "/win32icon:$(Join-Path $Studio 'assets\watson.ico')" `
    "/win32manifest:starter.manifest" "/resource:payload.zip,payload.zip" `
    /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll starter.cs
Pop-Location
Remove-Item $payload -ErrorAction SilentlyContinue
if (-not (Test-Path $target)) { throw "Setup-Datei wurde nicht erzeugt." }
"Fertig: $target  ($([math]::Round((Get-Item $target).Length / 1MB, 1)) MB, Version $Version)"
