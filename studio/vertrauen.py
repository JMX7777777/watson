"""
Vertrauens-Stufen für Watsons Hände und Augen – Vertrauen wächst wie in einer Freundschaft.

Stufe 1  Kennenlernen      – Watson fragt vor JEDER einzelnen Handlung.
Stufe 2  Mit Kontrolle     – Watson zeigt vorher seinen ganzen Plan; ein Ja, dann arbeitet er ihn am Stück ab.
Stufe 3  Freund            – Watson erledigt ganze Aufgaben selbst und fragt nur in kritischen Momenten.
Stufe 4  Volles Vertrauen  – Watson entscheidet selbstständig im Sinn des Nutzers.

Feste Grenzen auf JEDER Stufe (auch Stufe 4):
  - Senden/Veröffentlichen, endgültig Löschen, Kaufen/Bezahlen  -> Watson fragt immer.
  - Passwortfelder, Bank-, Bezahl- und Login-Fenster              -> Watson bedient sie nie.

Der Vertrauensbalken beruht auf echten Zahlen (erledigte Aufträge, Fehler, Stopps), nicht auf Watsons Gefühl.
Watson schlägt höchstens Stufe 3 von sich aus vor – Stufe 4 kann nur der Nutzer selbst wählen.
Bei einem Stopp oder einem Sicherheits-Verstoß geht Watson von selbst eine Stufe zurück und sagt, warum.
"""
import json
import threading
import time

import pfade

DATEI = pfade.DATEN / "vertrauen.json"
_lock = threading.Lock()

STUFEN = {
    1: {"name": "Kennenlernen", "icon": "🌱",
        "kurz": "Watson fragt vor jeder einzelnen Handlung.",
        "darf": "Nichts ohne dich. Jeder Klick, jede Eingabe, jedes Bildschirm-Lesen wird vorher gefragt.",
        "fragt": "Immer – bei jedem einzelnen Schritt.",
        "fuer": "Für den Anfang, wenn du Watson erst kennenlernst. Am sichersten, aber auch am langsamsten."},
    2: {"name": "Mit Kontrolle", "icon": "🤝",
        "kurz": "Watson zeigt vorher seinen Plan. Ein Ja – dann arbeitet er ihn am Stück ab.",
        "darf": "Einen Auftrag, den du vorher als Plan gesehen und erlaubt hast, ohne weitere Fragen ausführen.",
        "fragt": "Einmal am Anfang jedes Auftrags (mit dem ganzen Plan) – und bei jedem wichtigen Schritt.",
        "fuer": "Wenn Watson schon einige Aufgaben gut erledigt hat, du aber den Überblick behalten willst."},
    3: {"name": "Freund", "icon": "👬",
        "kurz": "Watson erledigt ganze Aufgaben selbst und fragt nur in kritischen Momenten.",
        "darf": "Programme öffnen, klicken, tippen, Bildschirm lesen und Abläufe starten, die du freigegeben hast.",
        "fragt": "In kritischen Momenten: wichtige Schritte, fremde Werkzeuge, unbekannte Abläufe, "
                 "Bildschirmfotos, die an ein KI-Gehirn gehen.",
        "fuer": "Wenn Watson viele Aufgaben fast fehlerfrei erledigt hat und du ihm im Alltag vertraust."},
    4: {"name": "Volles Vertrauen", "icon": "🔑",
        "kurz": "Wie ein treuer Verwalter: Watson entscheidet selbstständig in deinem Sinn.",
        "darf": "Alles im Rahmen deiner Aufträge selbst entscheiden und erledigen – ohne Rückfrage.",
        "fragt": "Nur noch an den festen Grenzen (Senden, endgültig Löschen, Kaufen/Bezahlen).",
        "fuer": "Nur, wenn Watson sich über lange Zeit als sehr zuverlässig erwiesen hat. "
                "Watson schlägt diese Stufe nie selbst vor – nur du kannst sie wählen."},
}
GRENZEN = ("Etwas senden oder veröffentlichen (E-Mails, Nachrichten, Beiträge)",
           "Etwas endgültig löschen",
           "Etwas kaufen, bestellen oder bezahlen",
           "Passwortfelder, Bank-, Bezahl- und Login-Fenster – die bedient Watson nie")

# Ab wann Watson selbst eine höhere Stufe vorschlägt (ehrlich, aus echten Zahlen)
REGEL = {2: (10, 0.90), 3: (50, 0.97)}      # Stufe: (mind. Aufträge, mind. Erfolgsquote)
FENSTER = 100                                 # die letzten 100 Aufträge zählen


def _laden():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except Exception:
        return {"auftraege": [], "hinweis": ""}


def _speichern(d):
    d["auftraege"] = d["auftraege"][-500:]
    DATEI.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def stufe(cfg):
    """Aktuelle Stufe aus den Einstellungen (alte Einstellung hands_mode wird übernommen)."""
    s = cfg.get("vertrauen_stufe")
    if s in (1, 2, 3, 4):
        return s
    alt = cfg.get("hands_mode", "auftrag")
    return {"jede": 1, "auftrag": 2}.get(alt, 4 if cfg.get("risky_ask") is False else 3)


# ---------- Aufträge zählen ----------
_aktuell = {"auftrag": None}


def auftrag_start(text, st):
    _aktuell["auftrag"] = {"zeit": time.strftime("%d.%m.%Y %H:%M"), "tag": time.strftime("%Y-%m-%d"),
                           "auftrag": (text or "")[:200], "stufe": st, "schritte": [], "fehler": 0,
                           "gestoppt": False, "abgelehnt": 0, "verstoss": False}


def schritt(beschreibung, ergebnis):
    a = _aktuell["auftrag"]
    if a is None:
        return
    erg = str(ergebnis or "")
    ok = not (erg.startswith("FEHLER") or erg.startswith("Abgelehnt"))
    a["schritte"].append({"was": beschreibung[:160], "ok": ok})
    if not ok:
        a["fehler"] += 1
    if erg.startswith("Abgelehnt") or "Aus Sicherheitsgründen" in erg:
        a["verstoss"] = True              # Watson wollte etwas Verbotenes tun (Passwort, Bank …)


def aktueller_auftrag():
    a = _aktuell["auftrag"]
    return json.loads(json.dumps(a)) if a else None


def nicht_erlaubt():
    if _aktuell["auftrag"] is not None:
        _aktuell["auftrag"]["abgelehnt"] += 1


def gestoppt():
    if _aktuell["auftrag"] is not None:
        _aktuell["auftrag"]["gestoppt"] = True


def auftrag_ende(cfg, speichere_cfg):
    """Auftrag abschließen (nur wenn Watson wirklich gehandelt hat). Gibt einen Rückstufungs-Hinweis zurück."""
    a, _aktuell["auftrag"] = _aktuell["auftrag"], None
    if not a or not a["schritte"]:          # nur Aufträge, bei denen Watson wirklich gehandelt hat
        return ""
    with _lock:
        d = _laden()
        d["auftraege"].append(a)
        hinweis = ""
        st = stufe(cfg)
        if st > 1 and (a["gestoppt"] or a["verstoss"]):
            grund = ("du mich gestoppt hast" if a["gestoppt"] else
                     "ich etwas versucht habe, das ich nicht darf (z. B. ein Passwort- oder Bankfenster)")
            neu = st - 1
            cfg["vertrauen_stufe"] = neu
            speichere_cfg(cfg)
            hinweis = (f"Ich bin von Stufe {st} auf Stufe {neu} „{STUFEN[neu]['name']}“ zurückgegangen, weil {grund}. "
                       "Vertrauen muss ich mir erst wieder verdienen. Du kannst die Stufe jederzeit selbst ändern.")
            d["hinweis"] = hinweis
        _speichern(d)
    return hinweis


def erfolgreich(a):
    return not a["gestoppt"] and not a["verstoss"] and a["fehler"] == 0 and a["abgelehnt"] == 0


def einschaetzung(cfg):
    """Watsons ehrliche Selbsteinschätzung – nur aus echten Zahlen."""
    d = _laden()
    letzte = d["auftraege"][-FENSTER:]
    n = len(letzte)
    gut = sum(1 for a in letzte if erfolgreich(a))
    quote = gut / n if n else 0.0
    stopps = sum(1 for a in letzte if a["gestoppt"])
    fehler = sum(1 for a in letzte if a["fehler"] or a["verstoss"])
    korrekturen = sum(1 for a in letzte if a["abgelehnt"])
    ernst_zuletzt = any(a["gestoppt"] or a["verstoss"] for a in letzte[-10:])

    empfohlen = 1
    for s in (2, 3):
        mind, q = REGEL[s]
        if n >= mind and quote >= q and not (s == 3 and ernst_zuletzt):
            empfohlen = s
    # Fortschritt bis zur nächsten Stufe (für den Balken)
    if empfohlen < 3:
        mind, q = REGEL[empfohlen + 1]
        teil_anzahl = min(1.0, n / mind)
        teil_quote = min(1.0, quote / q) if n else 0.0
        fortschritt = round(100 * ((empfohlen - 1) + teil_anzahl * teil_quote) / 3)
        noch = max(0, mind - n)
        naechstes = (f"Für Stufe {empfohlen + 1} brauche ich mindestens {mind} Aufträge "
                     f"mit {round(q * 100)} % Erfolg" + (f" – es fehlen noch {noch} Aufträge." if noch else
                                                          f" – meine Quote ist noch zu niedrig."))
    else:
        fortschritt = 70          # Stufe 3 erreicht; den Weg zu Stufe 4 füllt Watson nie selbst auf
        naechstes = ("Mehr als Stufe 3 schlage ich nie von mir aus vor. Volles Vertrauen (Stufe 4) "
                     "kannst nur du wählen.")
    if n == 0:
        satz = ("Ich habe für dich noch keine Aufgabe am Computer erledigt. Ehrlich gesagt kann ich mich deshalb "
                "noch nicht einschätzen – ich empfehle Stufe 1 oder 2.")
    else:
        satz = (f"Von meinen letzten {n} Aufträgen am Computer habe ich {gut} ohne Fehler, Stopp oder Korrektur "
                f"erledigt ({int(quote * 100)} %). Ich sehe mich ehrlich bei Stufe {empfohlen} "
                f"„{STUFEN[empfohlen]['name']}“.")
    return {"anzahl": n, "gut": gut, "quote": int(quote * 100), "stopps": stopps, "fehler": fehler,
            "korrekturen": korrekturen, "empfohlen": empfohlen, "fortschritt": fortschritt,
            "satz": satz, "naechstes": naechstes, "hinweis": d.get("hinweis", "")}


def hinweis_gelesen():
    with _lock:
        d = _laden(); d["hinweis"] = ""; _speichern(d)


def bericht(tag=None):
    """Rechenschaft: Was Watson an einem Tag am Computer getan hat."""
    tag = tag or time.strftime("%Y-%m-%d")
    return [{"zeit": a["zeit"][-5:], "auftrag": a["auftrag"], "stufe": a["stufe"],
             "schritte": [s["was"] for s in a["schritte"]][:30], "erfolgreich": erfolgreich(a),
             "gestoppt": a["gestoppt"]}
            for a in _laden()["auftraege"] if a.get("tag") == tag]
