# 📱 Watson auf dem Handy – Anleitung

Mit dieser Anleitung kannst du von deinem Handy aus mit Watson reden – zu Hause, unterwegs, im Bett, überall. Watson selbst bleibt dabei auf deinem Computer. Das Handy ist nur ein **sicheres Fenster** zu ihm.

Du brauchst etwa **15 Minuten** und musst das nur **einmal** machen.

---

## Was du brauchst

| Was | Wozu |
|---|---|
| Deinen Computer mit Watson | Hier „wohnt“ Watson. Er muss eingeschaltet sein, wenn du ihn vom Handy aus erreichen willst. |
| Ein Handy (Android oder iPhone) | Damit redest du mit Watson. |
| Die kostenlose App **Tailscale** | Baut den privaten, verschlüsselten Tunnel zwischen Handy und Computer. |
| Ein Konto zum Anmelden bei Tailscale | Zum Beispiel dein Google-, Microsoft- oder Apple-Konto. Ein neues Passwort brauchst du nicht. |

**Kosten:** keine. Tailscale ist für private Nutzung kostenlos.

---

## Wie das Ganze funktioniert (einfach erklärt)

Stell dir einen **privaten Tunnel** vor, zu dem nur deine eigenen Geräte einen Schlüssel haben.

- **Tailscale** baut diesen Tunnel. Alles darin ist verschlüsselt (mit der Technik „WireGuard“). Niemand dazwischen kann mitlesen – auch nicht dein Internet-Anbieter oder ein offenes WLAN.
- Watsons Handy-Seite ist **nicht im offenen Internet**. Nur Geräte, die mit **deinem** Tailscale-Konto angemeldet sind, finden sie überhaupt.
- Zusätzlich schützt eine **PIN** – und wenn du willst, dein **Fingerabdruck** (oder Gesicht).

Also **drei Schlösser**: dein Tailscale-Konto, deine PIN bzw. dein Finger, und der verschlüsselte Tunnel.

---

## Schritt 1 – Tailscale auf dem Computer

1. Lade Tailscale von der offiziellen Seite herunter: **tailscale.com/download** (für Windows).
2. Öffne die heruntergeladene Datei und bestätige die Frage von Windows mit **„Ja“**.
3. Tailscale öffnet sich. Melde dich an, zum Beispiel mit deinem **Google-** oder **Microsoft-Konto**.
4. Fertig, wenn Tailscale **„Connected“** (verbunden) zeigt.

> Tipp: Merk dir, mit welchem Konto du dich angemeldet hast. Auf dem Handy brauchst du **genau dasselbe**.

---

## Schritt 2 – Tailscale auf dem Handy

1. Installiere die App **Tailscale**:
   - **Android:** aus dem Google Play Store
   - **iPhone:** aus dem App Store
2. Öffne die App und melde dich mit **demselben Konto** an wie auf dem Computer.
3. Erlaube die **VPN-Verbindung**, wenn das Handy danach fragt. (Das ist der Tunnel – keine Sorge, Tailscale leitet nicht dein ganzes Internet um.)
4. In der App sollten jetzt **beide Geräte** stehen: dein Computer und dein Handy.

---

## Schritt 3 – Tunnel in Watson einschalten

1. Öffne Watson auf dem Computer: **Einstellungen → Watson auf dem Handy**.
2. Drücke **„Tunnel einschalten“** und bestätige.
3. **Nur beim allerersten Mal:** Watson zeigt dir einen Link **„Serve jetzt freigeben“**. Das ist eine einmalige Freigabe in deinem eigenen Tailscale-Konto:
   - Link öffnen (geht auch auf dem Handy),
   - bei Tailscale anmelden,
   - auf **„Enable“** klicken.
   - Watson merkt das von selbst und schaltet den Tunnel ein.
4. Jetzt zeigt Watson die **Adresse für dein Handy**. Sie sieht ungefähr so aus:
   `https://computername.tailXXXX.ts.net`

> Warum „Serve“ und nicht „Funnel“? Tailscale kennt beides. **Serve** gibt Watson nur für **deine eigenen Geräte** frei. „Funnel“ würde ihn öffentlich ins Internet stellen – das macht Watson **nie**.

---

## Schritt 4 – Auf dem Handy öffnen und PIN festlegen

1. Achte darauf, dass Tailscale auf dem Handy **verbunden** ist.
2. Öffne die Adresse aus Schritt 3 im Browser (Chrome auf Android, Safari auf dem iPhone).
3. **Beim allerersten Mal** fragt Watson nach einer **neuen PIN**:
   - 6 bis 12 Ziffern, zweimal eingeben,
   - bitte **nicht** deine Bank- oder Handy-PIN nehmen.
   - Dein Handy bietet an, sie im Passwort-Speicher zu sichern – das ist in Ordnung.
4. Das geht **nur ein einziges Mal** und **nur über den privaten Tunnel**. Danach kann die PIN nur noch am Computer geändert werden.

Du kannst die PIN auch vorher am Computer festlegen (**Einstellungen → Watson auf dem Handy → PIN festlegen**). Dann meldest du dich auf dem Handy einfach damit an.

---

## Schritt 5 – Fingerabdruck einrichten (empfohlen)

Nach der ersten Anmeldung fragt Watson: **„Fingerabdruck einrichten?“**

1. Tippe auf **„Einrichten“**.
2. Lege deinen Finger auf (oder schau in die Kamera, je nach Handy).
3. Fertig – ab jetzt meldest du dich mit **„👆 Mit Fingerabdruck anmelden“** an.

**Wichtig zu wissen:** Dein Fingerabdruck **verlässt nie dein Handy**. Das Handy bestätigt nur „ja, das ist der richtige Mensch“ – mit einer geheimen digitalen Unterschrift. Watson bekommt deinen Finger nie zu sehen. Die PIN bleibt immer als Ersatz.

---

## Schritt 6 – Watson wie eine App auf den Startbildschirm

**Android (Chrome):**
1. Adresse öffnen.
2. Oben rechts auf die **drei Punkte ⋮** tippen.
3. **„Zum Startbildschirm hinzufügen“** (oder „App installieren“) wählen.

**iPhone (Safari):**
1. Adresse öffnen.
2. Unten auf das **Teilen-Symbol** (Viereck mit Pfeil) tippen.
3. **„Zum Home-Bildschirm“** wählen.

Jetzt hast du ein **Watson-Symbol** und öffnest ihn mit einem Tipp.

---

## Im Alltag

- **Öffnen:** Tailscale an → Watson-Symbol antippen → mit Finger anmelden. Eine Anmeldung gilt **30 Tage**.
- **Reden:** Unten schreiben, auf ➤ tippen.
- **Vorlesen lassen:** unter einer Antwort auf **🔊 Anhören** tippen.
- **Bewerten:** 👍 oder 👎 – damit lernt Watson, welches „Gehirn“ dir am besten antwortet.
- **ℹ️:** zeigt dir, wie Watson die Antwort gemacht hat (welches Gehirn, welche Werkzeuge).
- **Erlaubnis-Fragen:** Wenn Watson am Computer etwas tun möchte und dich fragen muss, kommt die Frage **auf dein Handy**.
- **Stopp:** Während Watson arbeitet, kannst du mit **■ Stopp** jederzeit abbrechen.

### Wo du bist, da redet Watson

- **Bist du am Handy,** bleibt der Computer **still**: kein Ton, keine Fenster, keine Fragen auf dem Bildschirm. (Das gilt, solange du das Handy in den letzten 15 Minuten benutzt hast.)
- **Bist du am Computer,** bleibt das Handy **still**. Es spricht nur, wenn du selbst auf 🔊 tippst.
- Sobald du am Computer klickst oder tippst, gilt wieder der Computer.

**Ehrliche Ausnahme:** Bittest du Watson vom Handy aus ausdrücklich, am Computer etwas zu tun (zum Beispiel „öffne den Editor“), dann gehen dafür natürlich Fenster am Computer auf – das ist dann ja die Aufgabe.

---

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| „Seite nicht erreichbar“ | Ist Tailscale auf dem Handy **verbunden**? Ist der Computer **an** und nicht im Ruhezustand? Läuft Watson auf dem Computer? |
| Watson antwortet nachts nicht | Der Computer ist wahrscheinlich in den **Ruhezustand** gegangen. Das kannst du in Windows unter **Einstellungen → System → Energie** selbst einstellen (Watson ändert keine Windows-Einstellungen für dich). |
| „Tunnel einschalten“ zeigt einen Link | Das ist die einmalige Freigabe von „Serve“ – siehe Schritt 3. |
| „Zu viele falsche Versuche“ | Nach 5 falschen Versuchen ist die Anmeldung **15 Minuten gesperrt**. Einfach warten. |
| PIN vergessen | Am Computer: **Einstellungen → Watson auf dem Handy → PIN festlegen**. Alle alten Anmeldungen werden dabei ungültig. |
| Fingerabdruck geht nicht | Mit der PIN anmelden. Den Fingerabdruck kannst du am Computer entfernen und auf dem Handy neu einrichten. |
| Neues Handy | Tailscale auf dem neuen Handy installieren, gleiches Konto, Adresse öffnen, mit PIN anmelden, Fingerabdruck neu einrichten. |

---

## Handy verloren? So sperrst du es aus

1. Am Computer: **Einstellungen → Watson auf dem Handy** → beim Fingerabdruck des alten Handys auf **✕** klicken.
2. Eine **neue PIN** festlegen – damit werden alle Anmeldungen ungültig.
3. Im Tailscale-Konto (login.tailscale.com) das alte Handy **entfernen**.

Danach kommt mit dem alten Handy niemand mehr zu Watson.

---

## Was Watson dabei nie tut

- Watson stellt sich **nie öffentlich ins Internet** – nur in deinen privaten Tunnel.
- Watson **speichert deine PIN nie im Klartext**, nur verschlüsselt (als sogenannter „Hash“ im Windows-Tresor).
- Watson **sieht deinen Fingerabdruck nie**.
- Watson **meldet sich nie für dich** bei Tailscale oder anderen Diensten an und klickt nie für dich auf „Enable“ – das bleibt deine Entscheidung.
- Watson **ändert keine Windows-Einstellungen** für dich.
