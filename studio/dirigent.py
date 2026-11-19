"""
Der Dirigent: erkennt, was für eine Aufgabe eine Frage ist, und wählt das passende Gehirn –
kostenlos zuerst, mit Erfahrung aus dem Lernbuch. Bezahlte Gehirne nur, wenn der Nutzer den Bezahlt-Modus erlaubt.

Aufgaben-Arten:
  einfach   – Gruß, Dank, kurze Frage          -> schnelles Gratis-Gehirn
  normal    – gewöhnliche Fragen               -> starkes Gratis-Gehirn
  schwer    – Planen, Schreiben, Analysieren   -> das beste erlaubte starke Gehirn (mit Internet-Suche; Hermes entfernt 19.11.2026)
  computer  – Programme bedienen, Bildschirm   -> Gehirn mit Händen (Vertrauens-Stufen gelten)
"""
import re

import lernbuch

ID = "watson/dirigent"
NAMEN = {"einfach": "kurze Frage", "normal": "normale Frage", "schwer": "anspruchsvolle Aufgabe",
         "computer": "Arbeit am Computer"}

SCHNELL = ["nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-31b-it:free", "openrouter/free"]
STARK = ["nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free", "nvidia/nemotron-3.5-super-vl:free"]

EINFACH_RE = re.compile(r"^\s*(hallo|hi|hey|moin|guten (morgen|tag|abend)|gute nacht|danke|vielen dank|super|"
                        r"ok|okay|alles klar|wie geht'?s|wie geht es dir|tschüss|bis (später|morgen))\b", re.I)
SCHWER_RE = re.compile(r"\b(plan\w*|strategie|konzept|analysier\w*|vergleich\w*|ausführlich|schritt für schritt|"
                       r"geschäftsidee|businessplan|programmier\w*|code|skript|brief|bewerbung|aufsatz|predigt|"
                       r"andacht|zusammenfass\w*|recherchier\w*|begründ\w*|vor- und nachteile|entwirf|entwurf|"
                       r"berechne|rechne .{0,40}(prozent|zins))\b", re.I)


def kategorie(text, braucht_haende):
    t = (text or "").strip()
    if braucht_haende(t):
        return "computer"
    woerter = len(t.split())
    if len(t) > 350 or SCHWER_RE.search(t):
        return "schwer"
    if EINFACH_RE.search(t) and woerter <= 8 or woerter <= 4:
        return "einfach"
    return "normal"


# Team automatisch nur bei RECHERCHE-Aufgaben (Vergleich 15.11.2026: Team besser bei Plan/Kauf/Recht – echte Quellen,
# ehrliche Warnungen; gleich beim Rechnen; schlechter bei Andacht/Schreiben; dafür 2–3× langsamer).
RECHERCHE_RE = re.compile(r"\b(plan\w*|vergleich\w*|kauf\w*|kost\w*|preis\w*|anbieter|recht\w*|gesetz\w*|recherchier\w*|"
                          r"worauf .{0,30}achten|was brauche ich|welche[srnm]? .{0,40}(besser|empfiehlst|empfehlen|nehmen)|"
                          r"versicherung\w*|steuer\w*|förder\w*|beantrag\w*|gründ\w*|anmeld\w*|pflicht\w*|vor- und nachteile|"
                          r"geschäftsidee|businessplan|selbstständig\w*|günstig\w*|teurer|empfiehlst|empfehl\w*|"
                          r"\w*vertr[aä]g\w*|tarif\w*)\b", re.I)
SCHREIBEN_RE = re.compile(r"\b(brief\w*|andacht\w*|predigt\w*|gedicht\w*|aufsatz|bewerbung\w*|geschichte|rede|lied\w*|"
                          r"e-?mail|nachricht|übersetz\w*|formulier\w*|schreib\w*|gebet\w*|segen|glückwunsch\w*)\b", re.I)


# Alltags-Planung (Tag, Woche, Termine) braucht keine Recherche – ein schnelles Gehirn reicht
ALLTAG_RE = re.compile(r"\b(tag|woche|wochenende|morgen|abend|heute|termin\w*|urlaub|einkauf\w*)\b.{0,40}\bplan\w*|"
                       r"\bplan\w*\b.{0,40}\b(tag|tages|woche|wochenende|morgen|abend|heute|termin\w*)\b", re.I)


def team_passend(text):
    """True = Recherche-Aufgabe, bei der das Team (Chef, Rechercheur, Rechner, Texter, Prüfer) hilft."""
    t = (text or "").strip()
    if len(t.split()) < 6 or SCHREIBEN_RE.search(t) or ALLTAG_RE.search(t):
        return False
    return bool(RECHERCHE_RE.search(t))


def waehle(kat, cfg, rank_id, hermes_id, hermes_ok, bezahlte_gehirne):
    """Gibt (Gehirn, Begründung) zurück. Die Reihenfolge der Kandidaten kommt aus dem Lernbuch."""
    if kat == "computer":
        return rank_id, "Arbeit am Computer → Gehirn mit Händen"
    if kat == "einfach":
        kand = SCHNELL[:]
    elif kat == "schwer":
        kand = ([hermes_id] if hermes_ok else []) + STARK[:]
        if not cfg.get("nur_gratis", True):
            kand = bezahlte_gehirne[:1] + kand          # Bezahlt-Modus erlaubt: der „Professor“ zuerst
    else:
        kand = STARK[:] + [m for m in SCHNELL if m not in STARK]
    kand += [m for m in neu_entdeckte() if m not in kand]      # von der Abendrunde geprüfte neue Gratis-Gehirne
    reihe = lernbuch.ordnen(kat, kand)
    erfahrung = lernbuch.werte(kat).get(reihe[0])
    grund = f"{NAMEN[kat]} → {kurz(reihe[0])}" + (f" (Erfahrung: {erfahrung[0]}×)" if erfahrung else " (noch keine Erfahrung)")
    return reihe[0], grund


def neu_entdeckte():
    import json
    try:
        return json.loads((lernbuch.pfade.DATEN / "dirigent_extra.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def kandidaten(kat):
    """Für die Prüfung: Gratis-Gehirne einer Aufgaben-Art in der Reihenfolge der Erfahrung."""
    kand = (SCHNELL if kat == "einfach" else STARK + [m for m in SCHNELL if m not in STARK]) + neu_entdeckte()
    return lernbuch.ordnen(kat, list(dict.fromkeys(kand)))


def kurz(modell):
    return {"watson/hermes": "Hermes", "openrouter/free": "Gratis-Verteiler"}.get(
        modell, modell.split("/")[-1].replace(":free", ""))
