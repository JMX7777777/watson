# Watson deinstallieren (wird aus „Apps & Features“ aufgerufen) – Englisch oder Deutsch, je nach Watsons Menüsprache
param([switch]$Still, [switch]$DatenLoeschen)
Add-Type -AssemblyName System.Windows.Forms
$Ziel = Split-Path -Parent $MyInvocation.MyCommand.Path
$Daten = Join-Path $env:LOCALAPPDATA "Watson"
$de = $false
try { $de = ((Get-Content (Join-Path $Daten "einstellungen.json") -Raw -Encoding UTF8 | ConvertFrom-Json).ui_sprache -eq "de") } catch {}
$T = if ($de) { @{
    frage = "Watson wirklich deinstallieren?"
    daten = "Sollen auch deine persönlichen Daten gelöscht werden (Einstellungen und Gespräche)?`n`n'Nein' (empfohlen) behält sie – bei einer neuen Installation ist dann alles wieder da.`nDein Gedächtnis-Ordner (Benutzer\Watson) und deine Schlüssel im Windows-Tresor bleiben in jedem Fall erhalten."
    fertig = "Watson wurde deinstalliert." } } else { @{
    frage = "Really uninstall Watson?"
    daten = "Should your personal data be deleted too (settings and conversations)?`n`n'No' (recommended) keeps them – after a new installation everything is back.`nYour memory folder (User\Watson) and your keys in the Windows vault are kept in any case."
    fertig = "Watson has been uninstalled." } }

if (-not $Still) {
    $a = [System.Windows.Forms.MessageBox]::Show($T.frage, "Watson", "YesNo", "Question")
    if ($a -ne "Yes") { exit }
    $d = [System.Windows.Forms.MessageBox]::Show($T.daten, "Watson", "YesNo", "Question")
    $DatenLoeschen = ($d -eq "Yes")
}
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like "*$Ziel*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800
foreach ($l in @((Join-Path ([Environment]::GetFolderPath("Programs")) "Watson.lnk"), (Join-Path ([Environment]::GetFolderPath("Desktop")) "Watson.lnk"))) {
    if (Test-Path $l) {
        $t = (New-Object -ComObject WScript.Shell).CreateShortcut($l).Arguments
        if ($t -like "*$Ziel*") { Remove-Item $l -Force }      # nur UNSERE Verknüpfungen
    }
}
# Autostart nur entfernen, wenn er auf DIESE Installation zeigt
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$wert = (Get-ItemProperty $run -Name Watson -ErrorAction SilentlyContinue).Watson
if ($wert -and $wert -like "*$Ziel*") { Remove-ItemProperty $run -Name Watson -ErrorAction SilentlyContinue }
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Watson" -Recurse -Force -ErrorAction SilentlyContinue
if ($DatenLoeschen -and (Test-Path $Daten)) { Remove-Item $Daten -Recurse -Force -ErrorAction SilentlyContinue }
# Programm-Ordner löschen (die laufende Datei zuletzt über einen kurzen Hintergrund-Befehl)
Get-ChildItem $Ziel -Force | Where-Object { $_.Name -ne "deinstallieren.ps1" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Start-Process cmd.exe -ArgumentList "/c timeout /t 2 >nul & rmdir /s /q `"$Ziel`"" -WindowStyle Hidden
if (-not $Still) { [System.Windows.Forms.MessageBox]::Show($T.fertig, "Watson") | Out-Null }
