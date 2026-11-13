# Watson – Installer / Einrichtungs-Assistent (nur Windows-Bordmittel, keine Admin-Rechte nötig)
# Standard-Sprache Englisch, umschaltbar auf Deutsch. Fragt Land, Sprache, Name, Grundhaltung und Datenschutz,
# lädt die passende Stimme und zeigt einen Fortschrittsbalken mit Zeitschätzung.
param([switch]$Still, [string]$Ziel = "", [switch]$Test)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Quelle = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Ziel) { $Ziel = Join-Path $env:LOCALAPPDATA "Programs\Watson" }
$Daten = Join-Path $env:LOCALAPPDATA "Watson"
$Version = (Get-Content (Join-Path $Quelle "version.txt") -ErrorAction SilentlyContinue) -join ""
if (-not $Version) { $Version = "1.0" }

# ---------------- Texte (Englisch = Standard, Deutsch) ----------------
$T = @{
 en = @{
  title = "Install Watson"; sub = "Your personal assistant – version {0}"; back = "Back"; next = "Next"; cancel = "Cancel"
  install = "Install"; close = "Close"; start = "Start Watson"; retry = "Try again"
  p1h = "Welcome"; p1t = "Watson is a personal assistant that lives on your computer. He listens, speaks, remembers things for you and can help you on your PC.`n`nThis assistant will ask you a few short questions so that Watson fits you: where you live, which language he should speak, and how he should be.`n`nWatson is installed only for you – no administrator rights needed."
  p2h = "Where do you live?"; p2t = "Watson respects the laws of the country you live in. Your country also helps to suggest the right language."
  p2hint = "Watson does not know every law exactly. With sensitive matters he warns you and advises you to ask official bodies or an expert."
  p3h = "Which language should Watson speak?"; p3t = "Watson will listen, answer and speak in this language. Watson's menus are available in English and German."
  p3other = "Show all languages"; p3menu = "Menus and buttons:"
  p4h = "About you"; p4name = "Your name:"; p4bot = "Name of your assistant:"; p4formal = "Formal address (e.g. Sie / vous / u)"
  p4att = "What basis should Watson have?"; p4c = "Christian – polite, honest, the Bible as the standard"
  p4n = "Without religion – friendly, honest, the laws of your country as the standard"
  p4o = "Describe it myself"; p4law = "In every case Watson respects the laws of your country."
  p5h = "Privacy and options"
  p5t = "What stays on your computer: your conversations, memory, settings, voice and recordings.`r`n`r`nWhat goes to the internet: the questions you ask Watson are sent to the AI service OpenRouter (and the AI models it uses) so that Watson can think. Do not share passwords or very private data in conversations.`r`n`r`nYour keys are stored encrypted in the Windows vault. You can uninstall Watson at any time under Settings → Apps."
  p5ok = "I have read and understood this"; p5voice = "Install a voice for the chosen language"; p5desk = "Icon on the desktop"
  p5auto = "Start Watson automatically when I turn on the computer"
  p6h = "Installing …"; p6est = "Estimating the time …"; p6left = "About {0} minutes left"; p6min = "Less than a minute left"
  p7h = "Done!"; p7t = "Watson is installed.`n`nWhen Watson starts for the first time, it may take 15–30 seconds. He will then help you to get a free key for the AI brains (takes about 2 minutes)."
  needOk = "Please confirm that you have read the privacy note."; needName = "Please enter your name."
  chkDisk = "Not enough free disk space: {0} GB free, at least {1} GB needed."; chkNet = "No internet connection. Watson needs the internet during installation."
  s_dir = "Watson is installed to: {0}"; s_copy = "Copying program files …"; s_py = "Preparing Python (once) …"
  s_pkg = "Downloading components – this takes a few minutes …"; s_voice = "Looking for a voice for {0} …"; s_voiceok = "Voice: {0} (license: {1})"
  s_novoice = "No freely licensed voice found for {0} – Watson will answer in writing in this language."; s_voicedl = "Downloading voice: {0}"
  s_cfg = "Saving your settings …"; s_links = "Creating shortcuts …"; s_auto = "Autostart switched on."; s_done = "Done! Watson is installed. 🎉"
  s_test = "Test mode: no shortcuts, no entry in Apps, no autostart."; s_speed = "Internet speed: about {0} MB/s – estimated time: about {1} minutes."
  err = "The installation did not work:`n`n{0}`n`nPlease check the internet and try again."
 }
 de = @{
  title = "Watson installieren"; sub = "Dein persönlicher Assistent – Version {0}"; back = "Zurück"; next = "Weiter"; cancel = "Abbrechen"
  install = "Installieren"; close = "Schließen"; start = "Watson starten"; retry = "Erneut versuchen"
  p1h = "Willkommen"; p1t = "Watson ist ein persönlicher Assistent, der auf deinem Computer wohnt. Er hört zu, spricht, merkt sich Dinge für dich und kann dir am PC helfen.`n`nDieser Assistent stellt dir ein paar kurze Fragen, damit Watson zu dir passt: wo du wohnst, welche Sprache er sprechen soll und wie er sein soll.`n`nWatson wird nur für dich installiert – ohne Administrator-Rechte."
  p2h = "Wo wohnst du?"; p2t = "Watson achtet die Gesetze des Landes, in dem du wohnst. Dein Land hilft außerdem, die passende Sprache vorzuschlagen."
  p2hint = "Watson kennt nicht jedes Gesetz genau. Bei heiklen Dingen warnt er dich und rät, offizielle Stellen oder eine Fachperson zu fragen."
  p3h = "Welche Sprache soll Watson sprechen?"; p3t = "Watson hört, antwortet und spricht in dieser Sprache. Watsons Menüs gibt es auf Englisch und Deutsch."
  p3other = "Alle Sprachen zeigen"; p3menu = "Menüs und Knöpfe:"
  p4h = "Über dich"; p4name = "Dein Name:"; p4bot = "Name deines Assistenten:"; p4formal = "Höfliche Anrede (z. B. Sie / vous / u)"
  p4att = "Welche Grundlage soll Watson haben?"; p4c = "Christlich – höflich, ehrlich, die Bibel als Maßstab"
  p4n = "Ohne Religion – freundlich, ehrlich, die Gesetze deines Landes als Maßstab"
  p4o = "Selbst beschreiben"; p4law = "In jedem Fall achtet Watson die Gesetze deines Landes."
  p5h = "Datenschutz und Optionen"
  p5t = "Was auf deinem Computer bleibt: deine Gespräche, das Gedächtnis, Einstellungen, Stimme und Aufnahmen.`r`n`r`nWas ins Internet geht: die Fragen, die du Watson stellst, gehen an den KI-Dienst OpenRouter (und die KI-Modelle, die er nutzt), damit Watson denken kann. Teile in Gesprächen keine Passwörter oder sehr privaten Daten.`r`n`r`nDeine Schlüssel liegen verschlüsselt im Windows-Tresor. Du kannst Watson jederzeit unter Einstellungen → Apps deinstallieren."
  p5ok = "Ich habe das gelesen und verstanden"; p5voice = "Stimme für die gewählte Sprache installieren"; p5desk = "Symbol auf dem Desktop"
  p5auto = "Watson automatisch starten, wenn ich den Computer anmache"
  p6h = "Wird installiert …"; p6est = "Die Zeit wird geschätzt …"; p6left = "Noch etwa {0} Minuten"; p6min = "Noch weniger als eine Minute"
  p7h = "Fertig!"; p7t = "Watson ist installiert.`n`nBeim ersten Start braucht Watson 15–30 Sekunden. Danach hilft er dir, einen kostenlosen Schlüssel für die KI-Gehirne zu holen (dauert etwa 2 Minuten)."
  needOk = "Bitte bestätige, dass du den Datenschutz-Hinweis gelesen hast."; needName = "Bitte gib deinen Namen ein."
  chkDisk = "Zu wenig freier Speicher: {0} GB frei, mindestens {1} GB nötig."; chkNet = "Keine Internetverbindung. Watson braucht beim Installieren das Internet."
  s_dir = "Watson wird installiert nach: {0}"; s_copy = "Programm-Dateien werden kopiert …"; s_py = "Python wird vorbereitet (einmalig) …"
  s_pkg = "Bausteine werden geladen – das dauert ein paar Minuten …"; s_voice = "Suche eine Stimme für {0} …"; s_voiceok = "Stimme: {0} (Lizenz: {1})"
  s_novoice = "Keine frei lizenzierte Stimme für {0} gefunden – Watson antwortet in dieser Sprache schriftlich."; s_voicedl = "Stimme wird geladen: {0}"
  s_cfg = "Deine Einstellungen werden gespeichert …"; s_links = "Verknüpfungen werden angelegt …"; s_auto = "Autostart eingeschaltet."; s_done = "Fertig! Watson ist installiert. 🎉"
  s_test = "Test-Modus: keine Verknüpfungen, kein Eintrag in Apps, kein Autostart."; s_speed = "Internet: etwa {0} MB/s – geschätzte Dauer: etwa {1} Minuten."
  err = "Die Installation hat nicht geklappt:`n`n{0}`n`nBitte Internet prüfen und erneut versuchen."
 }
}
$script:UI = "en"
function L($k) { $T[$script:UI][$k] }

# Sprachen, in denen Watson sprechen kann (Kürzel = wie in studio\sprachen.py)
$SPRACHLISTE = [ordered]@{
 de = @("German","Deutsch","Deutsch"); en = @("English","Englisch","English"); nl = @("Dutch","Niederländisch","Nederlands")
 fr = @("French","Französisch","Français"); es = @("Spanish","Spanisch","Español"); it = @("Italian","Italienisch","Italiano")
 pt = @("Portuguese","Portugiesisch","Português"); pl = @("Polish","Polnisch","Polski"); cs = @("Czech","Tschechisch","Čeština")
 sk = @("Slovak","Slowakisch","Slovenčina"); sl = @("Slovenian","Slowenisch","Slovenščina"); hu = @("Hungarian","Ungarisch","Magyar")
 ro = @("Romanian","Rumänisch","Română"); da = @("Danish","Dänisch","Dansk"); sv = @("Swedish","Schwedisch","Svenska")
 no = @("Norwegian","Norwegisch","Norsk"); fi = @("Finnish","Finnisch","Suomi"); is = @("Icelandic","Isländisch","Íslenska")
 lb = @("Luxembourgish","Luxemburgisch","Lëtzebuergesch"); el = @("Greek","Griechisch","Ελληνικά"); tr = @("Turkish","Türkisch","Türkçe")
 ru = @("Russian","Russisch","Русский"); uk = @("Ukrainian","Ukrainisch","Українська"); sr = @("Serbian","Serbisch","Српски")
 ka = @("Georgian","Georgisch","ქართული"); kk = @("Kazakh","Kasachisch","Қазақ"); ar = @("Arabic","Arabisch","العربية")
 fa = @("Persian","Persisch","فارسی"); hi = @("Hindi","Hindi","हिन्दी"); ne = @("Nepali","Nepalesisch","नेपाली")
 vi = @("Vietnamese","Vietnamesisch","Tiếng Việt"); zh = @("Chinese","Chinesisch","中文"); sw = @("Swahili","Suaheli","Kiswahili")
 ca = @("Catalan","Katalanisch","Català"); cy = @("Welsh","Walisisch","Cymraeg"); lv = @("Latvian","Lettisch","Latviešu")
}
function SprName($code) { $s = $SPRACHLISTE[[string]$code]; if (-not $s) { return $code }; if ($script:UI -eq "de") { $s[1] } else { $s[0] } }
function NormSprache($two) { switch ($two) { "nb" { "no" } "nn" { "no" } default { $two } } }

# Länder aus Windows (.NET) – mit den dort gesprochenen Sprachen
$script:Laender = @{}
foreach ($c in [System.Globalization.CultureInfo]::GetCultures([System.Globalization.CultureTypes]::SpecificCultures)) {
    try { $r = New-Object System.Globalization.RegionInfo($c.Name) } catch { continue }
    $iso = $r.TwoLetterISORegionName; if ($iso.Length -ne 2 -or $iso -match '\d') { continue }
    if (-not $script:Laender.ContainsKey($iso)) { $script:Laender[$iso] = @{ iso = $iso; en = $r.EnglishName; de = $r.DisplayName; geo = $r.GeoId; spr = New-Object System.Collections.ArrayList } }
    $s = NormSprache $c.TwoLetterISOLanguageName
    if ($SPRACHLISTE.Contains($s) -and -not $script:Laender[$iso].spr.Contains($s)) { [void]$script:Laender[$iso].spr.Add($s) }
}
$homeGeo = try { (Get-WinHomeLocation).GeoId } catch { 0 }
$winSprache = NormSprache ([System.Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName)
# Der Installer startet immer auf Englisch (Standard); oben rechts kann man auf Deutsch umschalten.

# ---------------- Fenster ----------------
$blau = [System.Drawing.Color]::FromArgb(24, 95, 165)
$f = New-Object System.Windows.Forms.Form
$f.AutoScaleMode = "Dpi"; $f.ClientSize = New-Object System.Drawing.Size(648, 520); $f.StartPosition = "CenterScreen"; $f.FormBorderStyle = "FixedDialog"; $f.MaximizeBox = $false
$f.BackColor = [System.Drawing.Color]::White; $f.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$ico = Join-Path $Quelle "watson.ico"; if (Test-Path $ico) { $f.Icon = New-Object System.Drawing.Icon($ico) }
function Ctl($typ, $x, $y, $w, $h, $parent) { $c = New-Object "System.Windows.Forms.$typ"; $c.Location = New-Object System.Drawing.Point($x, $y); if ($w) { $c.Size = New-Object System.Drawing.Size($w, $h) } else { $c.AutoSize = $true }; $parent.Controls.Add($c); $c }

$logo = Ctl PictureBox 28 20 56 56 $f; $png = Join-Path $Quelle "watson-logo.png"; if (Test-Path $png) { $logo.Image = [System.Drawing.Image]::FromFile($png) }; $logo.SizeMode = "Zoom"
$titel = Ctl Label 96 18 0 0 $f; $titel.Text = "Watson"; $titel.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 20)
$untertitel = Ctl Label 99 56 0 0 $f; $untertitel.ForeColor = [System.Drawing.Color]::DimGray
$uiWahl = Ctl ComboBox 500 26 120 28 $f; $uiWahl.DropDownStyle = "DropDownList"; [void]$uiWahl.Items.AddRange(@("English", "Deutsch"))

$seiten = @(); for ($i = 0; $i -lt 7; $i++) { $p = Ctl Panel 24 92 600 360 $f; $p.Visible = $false; $seiten += $p }
function Kopf($p) { $h = Ctl Label 4 0 590 30 $p; $h.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 13); $h }
function Text($p, $y, $h) { $t = Ctl Label 6 $y 585 $h $p; $t }

# Seite 1: Willkommen
$h1 = Kopf $seiten[0]; $t1 = Text $seiten[0] 40 300
# Seite 2: Land
$h2 = Kopf $seiten[1]; $t2 = Text $seiten[1] 38 48
$land = Ctl ComboBox 8 96 380 28 $seiten[1]; $land.DropDownStyle = "DropDownList"; $land.MaxDropDownItems = 18
$hint2 = Text $seiten[1] 140 60; $hint2.ForeColor = [System.Drawing.Color]::DimGray
# Seite 3: Sprache
$h3 = Kopf $seiten[2]; $t3 = Text $seiten[2] 38 48
$spr = Ctl ListBox 8 92 380 170 $seiten[2]
$alle = Ctl CheckBox 400 94 190 24 $seiten[2]
$menuLbl = Ctl Label 8 276 0 0 $seiten[2]; $menuWahl = Ctl ComboBox 190 272 160 28 $seiten[2]; $menuWahl.DropDownStyle = "DropDownList"; [void]$menuWahl.Items.AddRange(@("English", "Deutsch"))
# Seite 4: Über dich
$h4 = Kopf $seiten[3]
$nameLbl = Ctl Label 8 44 0 0 $seiten[3]; $nameBox = Ctl TextBox 230 40 250 26 $seiten[3]; $nameBox.Text = ""
$botLbl = Ctl Label 8 80 0 0 $seiten[3]; $botBox = Ctl TextBox 230 76 250 26 $seiten[3]; $botBox.Text = "Watson"
$formal = Ctl CheckBox 8 114 470 24 $seiten[3]
$attLbl = Ctl Label 8 150 0 0 $seiten[3]; $attLbl.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 10)
$rbC = Ctl RadioButton 14 176 570 24 $seiten[3]; $rbN = Ctl RadioButton 14 202 570 24 $seiten[3]; $rbO = Ctl RadioButton 14 228 570 24 $seiten[3]; $rbN.Checked = $true
$eigen = Ctl TextBox 34 256 550 52 $seiten[3]; $eigen.Multiline = $true; $eigen.Enabled = $false
$rbO.Add_CheckedChanged({ $eigen.Enabled = $rbO.Checked })
$law = Ctl Label 8 318 0 0 $seiten[3]; $law.ForeColor = [System.Drawing.Color]::DimGray
# Seite 5: Datenschutz + Optionen
$h5 = Kopf $seiten[4]
$t5 = Ctl TextBox 8 38 580 160 $seiten[4]; $t5.Multiline = $true; $t5.ReadOnly = $true; $t5.ScrollBars = "Vertical"; $t5.BackColor = [System.Drawing.Color]::FromArgb(246, 245, 242)
$ok5 = Ctl CheckBox 8 206 580 24 $seiten[4]; $ok5.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 10)
$cbStimme = Ctl CheckBox 8 244 580 24 $seiten[4]; $cbStimme.Checked = $true
$cbDesk = Ctl CheckBox 8 270 580 24 $seiten[4]; $cbDesk.Checked = $true
$cbAuto = Ctl CheckBox 8 296 580 24 $seiten[4]; $cbAuto.Checked = $true
# Seite 6: Installieren
$h6 = Kopf $seiten[5]
$bar = Ctl ProgressBar 8 44 580 22 $seiten[5]; $bar.Maximum = 1000
$eta = Ctl Label 8 72 0 0 $seiten[5]; $eta.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 10)
$log = Ctl TextBox 8 100 580 250 $seiten[5]; $log.Multiline = $true; $log.ReadOnly = $true; $log.ScrollBars = "Vertical"
$log.BackColor = [System.Drawing.Color]::FromArgb(246, 245, 242); $log.Font = New-Object System.Drawing.Font("Segoe UI", 9)
# Seite 7: Fertig
$h7 = Kopf $seiten[6]; $t7 = Text $seiten[6] 40 200

$zurueck = Ctl Button 300 464 100 38 $f; $zurueck.FlatStyle = "Flat"
$weiter = Ctl Button 410 464 150 38 $f; $weiter.BackColor = $blau; $weiter.ForeColor = [System.Drawing.Color]::White; $weiter.FlatStyle = "Flat"; $weiter.FlatAppearance.BorderSize = 0
$abbr = Ctl Button 24 464 110 38 $f; $abbr.FlatStyle = "Flat"; $abbr.Add_Click({ $f.Close() })

function LaenderFuellen {
    $sel = if ($land.SelectedItem) { $land.SelectedItem.Tag } else { $null }
    $land.Items.Clear()
    $liste = $script:Laender.Values | Sort-Object { if ($script:UI -eq "de") { $_.de } else { $_.en } }
    foreach ($l in $liste) {
        $item = New-Object PSObject -Property @{ Tag = $l.iso; Name = $(if ($script:UI -eq "de") { $l.de } else { $l.en }) }
        $item | Add-Member ScriptMethod ToString { $this.Name } -Force
        $idx = $land.Items.Add($item)
        if (($sel -and $l.iso -eq $sel) -or (-not $sel -and $l.geo -eq $homeGeo)) { $land.SelectedIndex = $idx }
    }
    if ($land.SelectedIndex -lt 0) { $land.SelectedIndex = 0 }
}
function SprachenFuellen {
    $alt = if ($spr.SelectedItem) { $spr.SelectedItem.Tag } else { $null }
    $spr.Items.Clear()
    $iso = $land.SelectedItem.Tag
    # Reihenfolge: 1) Sprache, die man in Windows benutzt  2) Hauptsprache des Landes (z. B. nl für NL, en für US)
    # 3) weitere Sprachen des Landes  4) Englisch
    $landSpr = @($script:Laender[$iso].spr)
    $haupt = @($landSpr | Where-Object { try { [System.Globalization.CultureInfo]::CreateSpecificCulture($_).Name -like "*-$iso" } catch { $false } })
    $vorschlag = @(@($winSprache) + $haupt + @($landSpr | Where-Object { $_ -ne "en" }) + @("en") |
                   Where-Object { $SPRACHLISTE.Contains([string]$_) } | Select-Object -Unique)
    $codes = if ($alle.Checked) { @($vorschlag) + @($SPRACHLISTE.Keys | Where-Object { $vorschlag -notcontains $_ }) } else { $vorschlag }
    foreach ($code in $codes) {
        $code = [string]$code; $item = New-Object PSObject -Property @{ Tag = $code; Name = "$(SprName $code) – $($SPRACHLISTE[$code][2])" }
        $item | Add-Member ScriptMethod ToString { $this.Name } -Force
        [void]$spr.Items.Add($item)
    }
    $wunsch = if ($alt) { $alt } elseif ($vorschlag.Count) { $vorschlag[0] } else { "en" }
    for ($i = 0; $i -lt $spr.Items.Count; $i++) { if ($spr.Items[$i].Tag -eq $wunsch) { $spr.SelectedIndex = $i } }
    if ($spr.SelectedIndex -lt 0) { $spr.SelectedIndex = 0 }
}
$land.Add_SelectedIndexChanged({ $spr.Items.Clear() })
$alle.Add_CheckedChanged({ SprachenFuellen })
# Menüs folgen der gewählten Sprache: Deutsch -> deutsche Menüs, alle anderen -> englische (änderbar)
$spr.Add_SelectedIndexChanged({ if ($spr.SelectedItem) { $menuWahl.SelectedIndex = $(if ($spr.SelectedItem.Tag -eq "de") { 1 } else { 0 }) } })

function TexteSetzen {
    $f.Text = L "title"; $untertitel.Text = (L "sub") -f $Version
    $h1.Text = L "p1h"; $t1.Text = L "p1t"; $h2.Text = L "p2h"; $t2.Text = L "p2t"; $hint2.Text = L "p2hint"
    $h3.Text = L "p3h"; $t3.Text = L "p3t"; $alle.Text = L "p3other"; $menuLbl.Text = L "p3menu"
    $h4.Text = L "p4h"; $nameLbl.Text = L "p4name"; $botLbl.Text = L "p4bot"; $formal.Text = L "p4formal"; $attLbl.Text = L "p4att"
    $rbC.Text = L "p4c"; $rbN.Text = L "p4n"; $rbO.Text = L "p4o"; $law.Text = L "p4law"
    $h5.Text = L "p5h"; $t5.Text = L "p5t"; $ok5.Text = L "p5ok"; $cbStimme.Text = L "p5voice"; $cbDesk.Text = L "p5desk"; $cbAuto.Text = L "p5auto"
    $h6.Text = L "p6h"; $h7.Text = L "p7h"; $t7.Text = L "p7t"
    $zurueck.Text = L "back"; $abbr.Text = L "cancel"; Knoepfe
    LaenderFuellen; if ($spr.Items.Count) { SprachenFuellen }
}
$uiWahl.Add_SelectedIndexChanged({ $script:UI = @("en", "de")[$uiWahl.SelectedIndex]; TexteSetzen })

$script:seite = 0
function Knoepfe {
    $zurueck.Visible = $script:seite -gt 0 -and $script:seite -lt 5
    $weiter.Text = switch ($script:seite) { 4 { L "install" } 5 { L "install" } 6 { L "start" } default { L "next" } }
    $weiter.Enabled = $script:seite -ne 5
    $abbr.Text = if ($script:seite -eq 6) { L "close" } else { L "cancel" }
    $abbr.Enabled = $script:seite -ne 5
}
function Zeige($n) {
    for ($i = 0; $i -lt $seiten.Count; $i++) { $seiten[$i].Visible = ($i -eq $n) }
    $script:seite = $n
    if ($n -eq 2 -and -not $spr.Items.Count) { SprachenFuellen }
    Knoepfe
}

# ---------------- Installation ----------------
$script:t0 = $null
function Say($text, $pct = -1) {
    $log.AppendText((Get-Date -Format "HH:mm:ss") + "  " + $text + "`r`n")
    if ($pct -ge 0) { Fortschritt $pct }
    [System.Windows.Forms.Application]::DoEvents()
}
function Fortschritt($pct) {
    $bar.Value = [int]([Math]::Min(100, [Math]::Max(0, $pct)) * 10)
    if (-not $script:t0) { return }
    $vergangen = ((Get-Date) - $script:t0).TotalSeconds
    # Anfangs gilt die Schätzung aus der Tempo-Messung, später immer mehr der echte Fortschritt
    $hatPlan = [bool]$script:schaetzung
    $hatEcht = ($pct -ge 5) -and ($vergangen -ge 8)
    $plan = 0.0; $echt = 0.0
    if ($hatPlan) { $plan = [Math]::Max(0, $script:schaetzung * 60 - $vergangen) }
    if ($hatEcht) { $echt = $vergangen / $pct * (100 - $pct) }
    if (-not $hatPlan -and -not $hatEcht) { return }
    $gewicht = 0.0
    if ($hatEcht) { $gewicht = 1.0; if ($hatPlan) { $gewicht = [Math]::Min(1.0, $pct / 60.0) } }
    $rest = $echt * $gewicht + $plan * (1 - $gewicht)
    # nicht hin und her springen: die Anzeige darf höchstens langsam wieder steigen
    if ($script:letzteRest -and $rest -gt $script:letzteRest) { $rest = $script:letzteRest + ($rest - $script:letzteRest) * 0.2 }
    $script:letzteRest = $rest
    if ($rest -lt 60) { $eta.Text = L "p6min" } else { $eta.Text = (L "p6left") -f [Math]::Ceiling($rest / 60) }
}
function Run($exe, [string[]]$argv, $pctFrom, $pctTo, $sekunden) {
    # Startet ein Programm und hält das Fenster lebendig; der Balken wandert nach erwarteter Dauer weiter
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe; $psi.Arguments = ($argv | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join " "
    $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    foreach ($k in "UV_PYTHON_INSTALL_DIR", "UV_CACHE_DIR", "UV_LINK_MODE") { $psi.EnvironmentVariables[$k] = [Environment]::GetEnvironmentVariable($k) }
    $p = [System.Diagnostics.Process]::Start($psi)
    $errTask = $p.StandardError.ReadToEndAsync(); $outTask = $p.StandardOutput.ReadToEndAsync()
    $start = Get-Date
    while (-not $p.HasExited) {
        Start-Sleep -Milliseconds 300
        $anteil = 1 - [Math]::Exp(-((Get-Date) - $start).TotalSeconds / [Math]::Max(5, $sekunden))   # nähert sich 100 %, ohne es zu erreichen
        Fortschritt ($pctFrom + ($pctTo - $pctFrom) * $anteil * 0.97)
        [System.Windows.Forms.Application]::DoEvents()
    }
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw ("Fehler bei: " + (Split-Path $exe -Leaf) + "`r`n" + (($errTask.Result -split "`n" | Select-Object -Last 6) -join "`r`n")) }
    Fortschritt $pctTo
}
function New-Link($path, $target, $arguments, $icon) {
    $sh = New-Object -ComObject WScript.Shell
    $l = $sh.CreateShortcut($path); $l.TargetPath = $target; $l.Arguments = $arguments
    $l.WorkingDirectory = $Ziel; $l.IconLocation = "$icon,0"; $l.Description = "Watson"; $l.Save()
}
function Laden($url, $datei) {
    $wc = New-Object System.Net.WebClient; $wc.Headers.Add("User-Agent", "Watson-Setup")
    $wc.DownloadFile($url, $datei)
}

# Passende Stimme im offiziellen Piper-Katalog suchen – nur mit freier Lizenz (Weitergabe erlaubt)
function StimmeSuchen($code, $iso) {
    $base = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    $kat = Join-Path $env:TEMP "watson-voices.json"; Laden "$base/voices.json" $kat
    $katalog = (Get-Content $kat -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $_.Value }
    $q = @{ high = 0; medium = 1; low = 2; x_low = 3 }
    $kand = $katalog | Where-Object { $_.language.family -eq $code } |
        Sort-Object @{ e = { if ($_.language.region -eq $iso) { 0 } else { 1 } } }, @{ e = { $q[$_.quality] } }, @{ e = { $_.key } }
    foreach ($v in $kand) {
        $onnx = ($v.files.PSObject.Properties.Name | Where-Object { $_ -like "*.onnx" } | Select-Object -First 1)
        if (-not $onnx) { continue }
        $karte = ($onnx -replace '/[^/]+$', '') + "/MODEL_CARD"
        try { $mc = (New-Object System.Net.WebClient).DownloadString("$base/$karte") } catch { continue }
        $lz = if ($mc -match '(?im)licen[cs]e\W*[:\-]?\s*\**\s*\[?([^\r\n\]\)]+)') { $Matches[1].Trim() } else { "" }
        if ($lz -match '(?i)\bnc\b|non-?commercial|unknown|^$') { continue }
        if ($lz -notmatch '(?i)cc0|cc[- ]by|creative commons|mit|apache|public domain|bsd|cc-by') { continue }
        return @{ key = $v.key; onnx = $onnx; json = "$onnx.json"; md5 = $v.files.$onnx.md5_digest; lizenz = $lz; base = $base }
    }
    return $null
}

function Install {
    $script:t0 = Get-Date; $script:schaetzung = $null; $script:letzteRest = $null
    if (-not $spr.SelectedItem) { SprachenFuellen }
    $code = $spr.SelectedItem.Tag; $iso = $land.SelectedItem.Tag
    Say ((L "s_dir") -f $Ziel) 1
    # Vorab-Prüfung: Speicherplatz und Internet
    $frei = [Math]::Round((Get-PSDrive ($Ziel.Substring(0, 1))).Free / 1GB, 1)
    if ($frei -lt 3) { throw ((L "chkDisk") -f $frei, 3) }
    try {
        # Tempo messen: bis zu 3 Sekunden lang ein Stück einer großen Datei laden (kleine Dateien messen nur die Wartezeit)
        $req = [System.Net.HttpWebRequest]::Create("https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx")
        $req.UserAgent = "Watson-Setup"; $req.AddRange(0, 16MB); $req.Timeout = 15000
        $resp = $req.GetResponse(); $st = $resp.GetResponseStream(); $buf = New-Object byte[] 65536; $n = 0
        $tTest = Get-Date
        while (((Get-Date) - $tTest).TotalSeconds -lt 3) { $r = $st.Read($buf, 0, $buf.Length); if ($r -le 0) { break }; $n += $r }
        $sek = [Math]::Max(0.3, ((Get-Date) - $tTest).TotalSeconds); $st.Close(); $resp.Close()
        $mbs = [Math]::Max(0.2, ($n / 1MB) / $sek)
        $script:schaetzung = [Math]::Max(2, [Math]::Ceiling((450 / $mbs) / 60 + 1.5))   # ca. 450 MB laden + Auspacken/Einrichten
        Say ((L "s_speed") -f [Math]::Round($mbs, 1), $script:schaetzung)
        $eta.Text = (L "p6left") -f $script:schaetzung
    } catch { throw (L "chkNet") }
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like "*$Ziel*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Force $Ziel, $Daten | Out-Null
    Say (L "s_copy") 3
    Expand-Archive -Path (Join-Path $Quelle "watson-programm.zip") -DestinationPath $Ziel -Force
    Copy-Item (Join-Path $Quelle "uv.exe") (Join-Path $Ziel "uv.exe") -Force
    Set-Content (Join-Path $Ziel "installiert.txt") "Watson $Version – $(Get-Date -Format 'yyyy-MM-dd')" -Encoding UTF8
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Ziel "python"; $env:UV_CACHE_DIR = Join-Path $Daten "uv-cache"; $env:UV_LINK_MODE = "copy"
    $uv = Join-Path $Ziel "uv.exe"
    Say (L "s_py") 6
    Run $uv @("venv", "--allow-existing", "--python", "cpython-3.12-windows-x86_64-none", (Join-Path $Ziel ".venv")) 6 18 40
    Say (L "s_pkg") 18
    Run $uv @("pip", "install", "--python", (Join-Path $Ziel ".venv\Scripts\python.exe"), "-r", (Join-Path $Ziel "requirements.txt")) 18 82 ([Math]::Max(90, $script:schaetzung * 45))
    $stimme = $null
    if ($cbStimme.Checked) {
        Say ((L "s_voice") -f (SprName $code)) 83
        $v = StimmeSuchen $code $iso
        if (-not $v) { Say ((L "s_novoice") -f (SprName $code)) 90 }
        else {
            $sd = Join-Path $Daten "stimmen"; New-Item -ItemType Directory -Force $sd | Out-Null
            Say ((L "s_voicedl") -f $v.key) 85
            $ziel1 = Join-Path $sd ($v.key + ".onnx"); $ziel2 = Join-Path $sd ($v.key + ".onnx.json")
            Laden "$($v.base)/$($v.onnx)" $ziel1; Laden "$($v.base)/$($v.json)" $ziel2
            $md5 = (Get-FileHash $ziel1 -Algorithm MD5).Hash.ToLower()
            if ($v.md5 -and $md5 -ne $v.md5) { Remove-Item $ziel1, $ziel2 -Force; throw "Voice download damaged (MD5)." }
            Say ((L "s_voiceok") -f $v.key, $v.lizenz) 92
            $stimme = "piper:" + $v.key
        }
    }
    # Antworten aus dem Assistenten in Watsons Einstellungen schreiben
    Say (L "s_cfg") 93
    $vorlage = if ($rbC.Checked) { "christlich" } elseif ($rbO.Checked) { "eigene" } else { "freundlich" }
    $landName = $script:Laender[$iso].de    # Watsons Anweisungen sind deutsch – Landname dazu passend
    $antw = @{ ui_sprache = @("en", "de")[$menuWahl.SelectedIndex]; piper_voice = $stimme
               charakter = @{ name = $botBox.Text.Trim(); nutzer = $nameBox.Text.Trim(); anrede = $(if ($formal.Checked) { "Sie" } else { "du" })
                              vorlage = $vorlage; eigenes = $(if ($rbO.Checked) { $eigen.Text.Trim() } else { "" })
                              land = $iso; land_name = $landName; sprache = $code } }
    $aDatei = Join-Path $env:TEMP "watson-antworten.json"
    [IO.File]::WriteAllText($aDatei, ($antw | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
    $py = Join-Path $Ziel ".venv\Scripts\python.exe"
    Run $py @("-X", "utf8", (Join-Path $Ziel "einrichtung.py"), $aDatei) 93 95 5
    Remove-Item $aDatei -ErrorAction SilentlyContinue
    $pyw = Join-Path $Ziel ".venv\Scripts\pythonw.exe"; $main = '"' + (Join-Path $Ziel "watson_studio.py") + '"'
    $icon = Join-Path $Ziel "assets\watson.ico"
    $script:startCmd = @($pyw, $main)
    if ($Test) { Say (L "s_test") 100; $eta.Text = ""; return }
    Say (L "s_links") 96
    New-Link (Join-Path ([Environment]::GetFolderPath("Programs")) "Watson.lnk") $pyw $main $icon
    if ($cbDesk.Checked) { New-Link (Join-Path ([Environment]::GetFolderPath("Desktop")) "Watson.lnk") $pyw $main $icon }
    if ($cbAuto.Checked) { Set-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Watson" -Value "`"$pyw`" $main"; Say (L "s_auto") }
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Watson"
    New-Item -Force $key | Out-Null
    $un = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Ziel\deinstallieren.ps1`""
    @{ DisplayName = "Watson"; DisplayVersion = $Version; Publisher = "Watson"; DisplayIcon = $icon; InstallLocation = $Ziel
       UninstallString = $un; NoModify = 1; NoRepair = 1 }.GetEnumerator() | ForEach-Object {
        if ($_.Value -is [int]) { New-ItemProperty $key -Name $_.Key -Value $_.Value -PropertyType DWord -Force | Out-Null }
        else { New-ItemProperty $key -Name $_.Key -Value $_.Value -PropertyType String -Force | Out-Null } }
    Say (L "s_done") 100; $eta.Text = ""
}

$weiter.Add_Click({
    switch ($script:seite) {
        3 { if (-not $nameBox.Text.Trim()) { [System.Windows.Forms.MessageBox]::Show((L "needName"), "Watson") | Out-Null; return } ; Zeige 4 }
        4 {
            if (-not $ok5.Checked) { [System.Windows.Forms.MessageBox]::Show((L "needOk"), "Watson") | Out-Null; return }
            Zeige 5
            try { Install; Zeige 6 }
            catch {
                Say ("❌ " + $_.Exception.Message)
                [System.Windows.Forms.MessageBox]::Show(((L "err") -f $_.Exception.Message), "Watson", "OK", "Error") | Out-Null
                $script:seite = 4; $weiter.Text = L "retry"; $weiter.Enabled = $true; $abbr.Enabled = $true; $zurueck.Visible = $true
            }
        }
        6 { if (-not $Test) { Start-Process $script:startCmd[0] -ArgumentList $script:startCmd[1] -WorkingDirectory $Ziel }; $f.Close() }
        default { Zeige ($script:seite + 1) }
    }
})
$zurueck.Add_Click({ if ($script:seite -gt 0) { Zeige ($script:seite - 1) } })

$uiWahl.SelectedIndex = $(if ($script:UI -eq "de") { 1 } else { 0 })
TexteSetzen; Zeige 0
if ($Still) { $f.Add_Shown({ $ok5.Checked = $true; Zeige 4; $weiter.PerformClick() }) }
[void]$f.ShowDialog()
