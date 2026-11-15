"""
Watsons Entscheider: schnelle Ja/Nein- und Auswahl-Entscheidungen ohne Gehirn-Anfrage.

Idee wie bei Entscheidungs-Modellen (Jev, Laya): Text lesen und zwischen festen Antworten wählen – in Millisekunden.
Umsetzung mit Watsons eigenem „Versteher“ (bedeutung.py, multilingual-e5-small, läuft auf dem Laptop, gratis):
Für jede Antwort gibt es Beispielsätze; ein neuer Satz bekommt die Antwort, deren Beispiele ihm am ähnlichsten sind
(die k nächsten Beispiele stimmen ab). Mit Sicherheit: knappe Entscheidungen werden als unsicher gemeldet.

Fehlt das Modell, gibt jede Entscheidung None zurück – dann gilt die alte Regel (Wortliste / Gehirn).
"""
import threading

import numpy as np

import bedeutung

BEISPIELE = {
    # Gibt es in der Nachricht des Nutzers etwas Neues, Dauerhaftes über ihn? (sonst keine Merkzettel-Anfrage)
    "merken": {
        "ja": [
            "Ich heiße Peter und wohne in Utrecht.", "Meine Tochter hat am 3. Mai Geburtstag.",
            "Ich arbeite als Schreiner in einer kleinen Werkstatt.", "Ich trinke keinen Alkohol.",
            "Wir bekommen im Frühling ein Baby.", "Mein Lieblingsessen ist Lasagne.",
            "Ich habe Diabetes und muss auf Zucker achten.", "Nenn mich bitte Chef.",
            "Ich möchte nächstes Jahr ein Haus kaufen.", "Mein Bruder heißt Thomas und lebt in Spanien.",
            "Erklär mir Dinge bitte immer ganz kurz.", "Ich gehe jeden Sonntag in die Gemeinde.",
            "Ich habe mir ein neues Auto gekauft, einen Toyota.", "Ab Montag fange ich einen neuen Job an.",
            "Ich mag keine langen Antworten.", "Meine Frau ist Lehrerin.",
            "Ich lerne gerade Englisch für die Arbeit.", "Wir haben einen Hund, er heißt Max.",
            "Ich bin allergisch gegen Nüsse.", "Ich will mit dem Rauchen aufhören.",
        ],
        "nein": [
            "Wie wird das Wetter morgen?", "Erzähl mir einen Witz.", "Was ist die Hauptstadt von Kanada?",
            "Danke, das hat geholfen.", "Gib mir den Bibelvers des Tages.", "Rechne 45 mal 12.",
            "Öffne bitte den Browser.", "Hallo Watson!", "Was bedeutet das Wort Gnade?",
            "Schreib mir ein Gedicht über den Herbst.", "Wie funktioniert ein Elektroauto?",
            "Übersetze das bitte ins Englische.", "Mach weiter.", "Kannst du das kürzer sagen?",
            "Wie spät ist es?", "Was ist auf meinem Bildschirm?", "Erklär mir den Unterschied zwischen RAM und SSD.",
            "Okay, gute Nacht.", "Such mir ein Rezept für Pfannkuchen.", "Wer hat das Telefon erfunden?",
        ],
    },
    # Recherche-Aufgabe, bei der das Team (Quellen + Prüfer) hilft?
    "team": {
        "ja": [
            "Ich will einen gebrauchten E-Bike kaufen, worauf muss ich achten und was kostet das?",
            "Welche Krankenversicherung ist in den Niederlanden für Selbstständige am besten?",
            "Wie gründe ich eine kleine Firma und welche Pflichten habe ich?",
            "Lohnt sich eine Wärmepumpe für mein altes Haus?",
            "Vergleiche die günstigsten Stromanbieter für einen Zwei-Personen-Haushalt.",
            "Was muss ich beachten, wenn ich ein Zimmer an Studenten vermiete?",
            "Welcher Drucker ist für wenig Geld zuverlässig?",
            "Darf mein Vermieter die Miete einfach erhöhen?",
            "Ich möchte mit Videos auf YouTube Geld verdienen, wie fange ich an und was brauche ich?",
            "Welche Förderung gibt es für Solaranlagen?",
            "Was sind die Vor- und Nachteile von einem Tablet gegenüber einem Laptop für Senioren?",
            "Erstelle mir einen Businessplan für einen Food-Truck.",
        ],
        "nein": [
            "Schreib einen Geburtstagsgruß für meine Mutter.", "Wie spät ist es in New York?",
            "Hilf mir, meinen Tag zu planen.", "Erklär mir, was Gnade bedeutet.", "Rechne 15 Prozent von 240 aus.",
            "Gib mir einen ermutigenden Bibelvers.", "Übersetze diesen Satz ins Niederländische.",
            "Erzähl mir eine Gutenachtgeschichte.", "Was ist ein Algorithmus?", "Öffne das Video-Studio.",
            "Bereite eine Predigt über Liebe vor.", "Formuliere diese E-Mail freundlicher.",
        ],
    },
}

_lock = threading.Lock()
_cache = {}


def _vektoren(aufgabe):
    with _lock:
        if aufgabe not in _cache:
            labels, texte = [], []
            for lab, sätze in BEISPIELE[aufgabe].items():
                labels += [lab] * len(sätze)
                texte += sätze
            _cache[aufgabe] = (labels, bedeutung.einbetten(texte, "query"))
        return _cache[aufgabe]


def entscheide(aufgabe, text, k=5):
    """-> (antwort, sicherheit 0..1) oder (None, 0) wenn das Modell fehlt.
    Die k ähnlichsten Beispiele stimmen ab, gewichtet nach Ähnlichkeit."""
    if not bedeutung.bereit() and not bedeutung.laden():
        return None, 0.0
    try:
        labels, mat = _vektoren(aufgabe)
        v = bedeutung.einbetten([text[:1500]], "query")[0]
    except Exception:
        return None, 0.0
    s = mat @ v
    oben = np.argsort(-s)[:k]
    stimmen = {}
    for i in oben:
        stimmen[labels[i]] = stimmen.get(labels[i], 0.0) + float(np.exp((s[i] - s[oben[0]]) * 30))
    gesamt = sum(stimmen.values())
    antwort = max(stimmen, key=stimmen.get)
    return antwort, stimmen[antwort] / gesamt
