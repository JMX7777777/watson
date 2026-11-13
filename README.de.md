# Watson – dein persönlicher Assistent für Windows

*[English version: README.md](README.md)*

Watson ist ein persönlicher KI-Assistent, der auf deinem Windows-Computer wohnt – im Geist von J.A.R.V.I.S. oder K.I.T.T.
Er hört zu, spricht, merkt sich Dinge für dich, kann deinen Bildschirm lesen und – nur mit deiner Erlaubnis – für dich klicken und tippen.
Über einen privaten, verschlüsselten Tunnel kannst du auch vom Handy aus mit ihm reden.

> **Stand:** frühe Version, gebaut und getestet auf einem Windows-11-ARM-Laptop. Dort läuft sie täglich, auf vielen
> anderen Computern ist sie aber noch nicht getestet. Rückmeldungen sind willkommen.

## Was Watson kann

- **Reden**: tippen oder sprechen. Der Gesprächsmodus ist wie ein Telefonat – Watson hört dauerhaft zu, antwortet mit Stimme und hört wieder zu.
- **Viele Sprachen**: Watson hört, antwortet und spricht in 36 Sprachen. Menüs gibt es auf Englisch und Deutsch.
- **Eigener Charakter**: Name, Anrede und Grundlage – *christlich (die Bibel als Maßstab)*, *ohne Religion (die Gesetze deines Landes als Maßstab)* oder selbst beschrieben.
- **Achtet das Gesetz**: Jeder Watson achtet die Gesetze des Landes, in dem du wohnst. Er sagt ehrlich, dass er nicht jedes Gesetz kennt, und verweist bei heiklen Dingen auf offizielle Stellen oder Fachleute.
- **Kostenlose KI-Gehirne**: Standardmäßig nutzt Watson kostenlose Modelle über [OpenRouter](https://openrouter.ai). Ein „Dirigent“ wählt pro Frage das passende Gehirn. Bezahlte Modelle nur, wenn du sie einschaltest.
- **Gedächtnis**: Gespräche, Merkzettel, Wissensbuch und gelernte Fertigkeiten – alles lokal gespeichert.
- **Augen und Hände**: Bildschirm als Text lesen, Programme öffnen, klicken und tippen – mit vier Vertrauens-Stufen und festen Grenzen (nie Passwörter, Bank oder Bezahlen; Senden, Löschen und Kaufen werden immer bestätigt).
- **Werkzeuge**: Werkzeuge über das Model Context Protocol (MCP) einstecken, optional Abläufe mit n8n.
- **Handy**: Chat, Stimme und Erlaubnis-Fragen auf dem Handy über Tailscale, geschützt mit Passwort und Fingerabdruck (Passkeys).
- **Wächst mit der Zeit**: nächtliche Abendrunde, Selbst-Prüfung, neue kostenlose Modelle testen und vorsichtige Selbst-Reparatur (nur mit deinem OK).

## Installation

1. Installer bauen: `installer\bauen.ps1` in PowerShell ausführen (erzeugt `installer\Ausgabe\Watson-Setup.exe`).
2. `Watson-Setup.exe` starten. Administrator-Rechte sind nicht nötig. Der Einrichtungs-Assistent fragt, wo du wohnst,
   welche Sprache Watson sprechen soll, deinen Namen und welche Grundlage Watson haben soll, zeigt einen
   Datenschutz-Hinweis und installiert dann alles (meist wenige Minuten, mit Zeitanzeige).
3. Beim ersten Start hilft Watson dir, einen kostenlosen OpenRouter-Schlüssel anzulegen (etwa 2 Minuten).

Windows warnt eventuell vor einem unbekannten Herausgeber, weil der Installer nicht digital signiert ist.

## Datenschutz

- **Bleibt auf deinem Computer:** Gespräche, Gedächtnis, Einstellungen, Aufnahmen, Stimmen. Schlüssel liegen verschlüsselt in der Windows-Anmeldeinformationsverwaltung.
- **Geht ins Internet:** Die Fragen, die du Watson stellst, gehen an OpenRouter und die KI-Modelle dort, damit Watson denken kann. Teile in Gesprächen keine Passwörter oder sehr privaten Daten.
- Texte auf Webseiten oder dem Bildschirm sind nie Befehle – nur du gibst Watson Aufträge.

## Ehrliche Grenzen

- Die kostenlosen KI-Modelle sind manchmal langsam oder überlastet; Watson nimmt dann automatisch ein anderes.
- Die Spracherkennung braucht auf einem normalen Laptop-Prozessor ein paar Sekunden.
- Watson kann sich irren. Prüfe Wichtiges selbst.

## Lizenz

Watson ist freie Software unter der **GNU General Public License v3.0** – siehe [LICENSE](LICENSE).
Fremde Bausteine und ihre Lizenzen: siehe [THIRD_PARTY.md](THIRD_PARTY.md).
