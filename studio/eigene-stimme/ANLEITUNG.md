# Watson mit deiner eigenen Stimme – Anleitung

Watson kann mit **deiner eigenen Stimme** sprechen. Dafür reicht eine kurze Aufnahme von etwa 5 Sekunden.
Alles läuft **auf deinem eigenen Computer**, ohne Internet und ohne Kosten. Deine Stimme verlässt dein Gerät nicht.

> **Wichtig, bitte ehrlich bleiben:** Nimm nur **deine eigene Stimme**, oder die Stimme eines Menschen, der dir das **ausdrücklich erlaubt** hat. Fremde Stimmen ohne Erlaubnis nachzumachen ist unfair und kann strafbar sein.

---

## Schritt 1 – Erst das Gerät prüfen (2 Minuten)

Nicht jeder Computer ist stark genug. Deshalb prüft Watson zuerst, ob es bei dir gut geht.

**So geht's:** Watson öffnen → links im Menü **Stimme** → Knopf **„Gerät prüfen“**.

Watson schaut sich Prozessor, Arbeitsspeicher, freien Platz und Rechentempo an. Es wird nichts verändert,
nichts installiert und nichts abgespielt. Danach bekommst du eins von drei Ergebnissen:

| Ergebnis | Was es heißt | Weiter mit |
|---|---|---|
| ✅ **Sehr gut** | Die eigene Stimme läuft flüssig. Eine Antwort mit 2 Sätzen braucht etwa 15–40 Sekunden. | **Weg A** |
| 🟡 **Mittel** | Es geht, aber du wartest länger, etwa 40–100 Sekunden bei 2 Sätzen. | **Weg B** |
| ❌ **Geht nicht** | Zu wenig Speicher, zu wenig Platz oder zu langsam. | **Weg C** |

*Ehrlicher Hinweis:* Dieser erste Test ist nur eine **Schätzung**. Sicher weißt du es erst nach dem **Echttest** in Schritt A4.
Bisher ist die eigene Stimme nur auf einem Laptop mit ARM-Prozessor (Snapdragon X) ausprobiert.
Auf normalen Intel-/AMD-Computern sollte es genauso gehen, getestet ist es dort aber noch nicht.

---

## Weg A – ✅ Sehr gut

### A1. Den Linux-Bereich einrichten (einmalig, ca. 10 Minuten)
Watsons Stimm-Rechner läuft in einem kleinen Linux-Bereich innerhalb von Windows. Dieser heißt **WSL**.
Falls der Gerätetest schon „Linux-Bereich ist da: Ubuntu-24.04“ gezeigt hat, **überspring diesen Schritt**.

1. Startmenü → **„Terminal“** mit der rechten Maustaste → **„Als Administrator ausführen“**.
2. Eintippen und Enter drücken:
   ```
   wsl --install -d Ubuntu-24.04
   ```
3. Den Computer **neu starten**, wenn er danach fragt.
4. Nach dem Neustart öffnet sich ein Ubuntu-Fenster. Lege dort einen **Benutzernamen und ein Passwort** an.
   Das machst du selbst; Watson tippt nie Passwörter ein.

*Wenn eine Meldung zur „Virtualisierung“ kommt:* Diese muss beim Starten des Computers im BIOS/UEFI eingeschaltet werden.
Das ist bei jedem Hersteller etwas anders. Such im Internet nach „Virtualisierung einschalten“ und dem Namen deines Laptops,
oder frag jemanden, der sich auskennt.

### A2. Den Stimm-Rechner bauen (einmalig, ca. 10–20 Minuten, ca. 1 GB Download)
1. Ein normales **Terminal** öffnen (kein Administrator nötig).
2. Diesen Befehl eingeben. `DEINNAME` ersetzt du durch deinen Windows-Benutzernamen (steht in `C:\Users\…`):
   ```
   wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/Users/DEINNAME/AppData/Local/Programs/Watson/eigene-stimme/einrichten.sh
   ```
3. Warten, bis **„FERTIG: eigene Stimme ist eingerichtet.“** erscheint.

Was dabei passiert: Es werden Bau-Werkzeuge installiert, das freie Programm **omnivoice.cpp** (MIT-Lizenz)
in einem fest geprüften Stand heruntergeladen, mit einer kleinen Watson-Ergänzung für mehr Tempo gebaut,
und das Stimm-Modell (ca. 0,9 GB) geladen. Alles bleibt in `/opt/omnivoice.cpp` im Linux-Bereich.

### A3. Deine Stimmprobe aufnehmen (5 Minuten)
**Tipps für eine gute Probe**
- Ein **ruhiger Raum**, ohne Musik, Fernseher oder Lüftergeräusche.
- **Natürlich** sprechen, so wie du mit einem Freund redest. Nicht vorlesen und nicht zu langsam.
- Ein ganzer Satz, **etwa 5 Sekunden** lang. Länger ist nicht besser: Dann klingt die Stimme kaum ähnlicher, rechnet aber langsamer.
- Kurze Proben (1–3 Sekunden) gehen auch. Sie sind gut verständlich, klingen aber weniger nach dir.

**So legst du sie ab**
1. Die Aufnahme als **WAV-Datei** speichern, Name: `eigene-stimme.wav`.
   (Das Handy oder der Windows-Sprachrekorder speichern oft als `.m4a`. Frag Watson im Chat, er hilft beim Umwandeln und Zuschneiden.)
2. In eine Textdatei `eigene-stimme.txt` **genau den Satz schreiben, den du gesagt hast**, Wort für Wort.
   ⚠️ Das ist wichtig: Fehlt ein Wort oder steht ein falsches drin, spricht Watson manchmal ein seltsames Wort vorweg.
3. Beide Dateien in diesen Ordner legen: `%LOCALAPPDATA%\Watson\stimmen\`
   (diesen Pfad in die Adresszeile des Explorers einfügen und Enter drücken).

### A4. Echttest (1 Minute)
Watson → links im Menü **Stimme** → Knopf **„Echttest“**.
Watson rechnet jetzt **einen echten Satz** mit deiner Stimme und misst die Zeit. Es wird dabei nichts abgespielt.
Jetzt weißt du sicher, ob Weg A oder Weg B für dich gilt.

### A5. Stimme einschalten
Watson → links im Menü **Stimme** → Auswahl **„Meine eigene Stimme (schnell)“** → **„Probe hören“**.
Beim allerersten Satz startet Watson den Stimm-Rechner. Das dauert einen Moment.
Wenn etwas nicht klappt, spricht Watson automatisch mit der Ersatzstimme Thorsten. Er bleibt also nie stumm.

### A6. Vorrat an kurzen Sätzen (einmalig, ca. 30–40 Minuten)
Ganz kurze Sätze wie „Gern geschehen.“ sind beim Stimm-Klonen **unzuverlässig**: Ungefähr jeder zweite klingt undeutlich.
Darum erzeugt Watson etwa 50 häufige Kurzsätze **einmal vorher**, hört jeden selbst nach und wiederholt
ihn, bis er stimmt. Danach kommen diese Sätze **sofort** und **fehlerfrei**.

Watson → links im Menü **Stimme** → Knopf **„Vorrat erzeugen“**. Den Computer dabei einfach laufen lassen.
Die Sätze stehen in `%LOCALAPPDATA%\Watson\stimmen\kurzsaetze.txt`. Du kannst eigene Sätze dazuschreiben
und den Knopf noch einmal drücken. Dann werden nur die neuen Sätze erzeugt.

**Fertig! 🎉**

---

## Weg B – 🟡 Mittel

Es geht, aber dein Computer rechnet langsamer. Mach **alle Schritte von Weg A**, mit diesen Unterschieden:

- **A3:** Nimm eine **kurze Probe** von 3 bis höchstens 5 Sekunden. Jede Sekunde weniger spart Rechenzeit.
- **A6, der Vorrat, ist bei dir besonders wichtig.** Die häufigsten Antworten kommen dann sofort, und du wartest nur bei längeren Antworten.
- **Beim Rechnen nichts Schweres nebenher laufen lassen**, zum Beispiel Spiele oder Videobearbeitung.
- Ist dir das Warten im Alltag doch zu lang: Einfach wieder **„Thorsten“** auswählen. Das geht jederzeit, und nichts geht verloren.

*Ehrlich:* Bei „mittel“ dauert eine Antwort mit 2 Sätzen etwa eine Minute oder länger. Für kurze Fragen ist das in Ordnung.
Für lange Gespräche ist es eher mühsam.

---

## Weg C – ❌ Geht nicht

Dein Computer ist leider zu schwach für den Stimm-Klon, oder es fehlt etwas Wichtiges (Speicher, Platz, Virtualisierung).
Der Gerätetest zeigt mit ✘, woran es liegt. Manches kann man ändern:

| Problem (✘) | Kann man das ändern? |
|---|---|
| Zu wenig freier Platz | **Ja.** Platz schaffen (alte Downloads, Papierkorb) und neu prüfen. |
| Virtualisierung aus | **Meistens ja**, im BIOS/UEFI (siehe A1). |
| Windows zu alt | **Ja**, Windows-Update ausführen. |
| Weniger als 8 GB Arbeitsspeicher | Nur mit neuem Speicher, und das geht nur bei manchen Computern. |
| Zu langsam | Nein, das hängt am Prozessor. |

**Was Watson dir trotzdem bietet:**
- **Thorsten** (männlich, ruhig) oder **Kerstin** (weiblich). Die beiden sind schnell, laufen auf jedem Computer und brauchen kein Internet.
  Ehrlich gesagt klingen sie nicht so natürlich wie ein Stimm-Klon.
- **Windows-Stimme**: die eingebaute Stimme von Windows.

Auswahl: Watson → links im Menü **Stimme**. Watson funktioniert auch ohne eigene Stimme vollständig. Nur die Stimme ist eine andere.

---

## Hilfe bei Problemen

| Was passiert? | Was hilft? |
|---|---|
| Watson spricht mit Thorsten statt mit meiner Stimme | Der Stimm-Rechner läuft nicht. **Echttest** drücken, dann zeigt Watson den Grund. |
| Vor dem Satz kommt ein komisches Wort | Der Text in `eigene-stimme.txt` passt nicht genau zur Aufnahme. Bitte prüfen. |
| Ein kurzer Satz klingt undeutlich | Den Satz in `kurzsaetze.txt` aufnehmen und **„Vorrat erzeugen“** drücken. |
| Klingt nicht nach mir | Eine neue Probe aufnehmen: ruhiger Raum, natürlicher sprechen, etwa 5 Sekunden. |

*Diese Anleitung beruht auf echten Tests vom November 2026. Was noch nicht ausprobiert ist, steht als „ehrlicher Hinweis“ dabei.*
