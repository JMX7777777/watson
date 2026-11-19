"""
Watsons Team mit gemeinsamem Arbeitsbrett.

Ablauf (gebaut 15.11.2026 nach dem Wunsch „1 Gehirn, mehrere Funktionen, die als 1 System arbeiten“):
  1. Chef      – liest den Auftrag, schreibt einen Plan aufs Brett: Aufgaben für Helfer + Punkte, die die
                 Antwort beantworten muss. Rechner nur, wenn es um Zahlen geht.
  2. Helfer    – Rechercheur / Rechner arbeiten GLEICHZEITIG, jeder legt sein Ergebnis aufs Brett.
  3. Texter    – liest das ganze Brett und schreibt EINE klare Antwort.
  4. Prüfer    – prüft gegen den Plan: alles beantwortet? Zahlen stimmig? Unbelegte Behauptungen?
                 Gewissens-Prüfung (wahr, gerecht, schadet niemandem?). Bei Lücken: EINMAL nachbessern.
  Warnungen des Prüfers bekommt der Nutzer immer sichtbar zu sehen.

Das Modul kennt keine Gehirne selbst: `frage(rolle, anweisung, prompt, werkzeuge)` wird von außen
mitgegeben (so lässt es sich auch ohne Internet testen).
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor

ROLLEN = {
    "Chef": "Du bist der Chef des Teams. Du verstehst den Auftrag genau und verteilst ihn in wenige, klare Aufgaben.",
    "Rechercheur": "Du bist der Rechercheur. Du sammelst Fakten, Möglichkeiten und Beispiele. Benutze Werkzeuge "
                   "(z. B. Internet), wenn es hilft. Sag bei jeder Angabe ehrlich, ob du sie geprüft hast oder schätzt.",
    "Rechner": "Du bist der Rechner. Du rechnest sorgfältig Schritt für Schritt und zeigst den Rechenweg. "
               "Schreib dazu, welche Zahlen Annahmen sind.",
    "Texter": "Du bist der Texter. Du schreibst aus den Ergebnissen des Teams eine klare, freundliche Antwort in "
              "einfachen Worten. Du erfindest nichts dazu, was nicht auf dem Arbeitsbrett steht.",
    "Prüfer": "Du bist der Prüfer. Du bist ehrlich und genau, nicht höflich-oberflächlich. Du suchst Lücken, "
              "Rechenfehler und Behauptungen, die nicht belegt sind.",
}
HELFER = ("Rechercheur", "Rechner")
MAX_AUFGABEN = 3
# Gratis-Gehirne tun manchmal so, als hätten sie Werkzeuge, und schreiben „{{search_web(…)}}“ statt einer Antwort
# (gefunden 16.11.2026 beim ersten Hintergrund-Auftrag). Darum: ausdrücklich verbieten, erkennen, einmal neu.
OHNE_WERKZEUGE = (" In dieser Rolle hast du KEINE Werkzeuge und kannst nichts mehr suchen oder aufrufen – schreib nie "
                  "Werkzeug-Aufrufe wie {{…}}, search_web(…) oder <tool_call>, sondern arbeite nur mit dem, was dir vorliegt.")
WERKZEUG_MUELL_RE = re.compile(r"\{\{\s*\w+\(|\b(search_web|web_search|browse|fetch_url|tool_call)\s*\(|<tool_call>|"
                               r"\"(name|function)\"\s*:\s*\"\w+\"\s*,\s*\"(arguments|parameters)\"", re.I)


def _muell(text):
    """True = statt einer Antwort stehen (fast) nur erfundene Werkzeug-Aufrufe da."""
    t = (text or "").strip()
    if len(t) < 40:
        return True
    treffer = WERKZEUG_MUELL_RE.findall(t)
    rest = WERKZEUG_MUELL_RE.sub("", re.sub(r"\{\{.*?\}\}", "", t, flags=re.S)).strip()
    return bool(treffer) and len(rest) < 200


def _json(text):
    """Holt das erste {...} aus einer Gehirn-Antwort (Gehirne schreiben gern Text drumherum)."""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text)
    a, e = t.find("{"), t.rfind("}")
    if a < 0 or e <= a:
        return None
    try:
        return json.loads(t[a:e + 1])
    except Exception:
        return None


def _brett_text(brett, mit_antwort=False):
    zeilen = [f"AUFTRAG: {brett['auftrag']}", "", "PUNKTE, DIE DIE ANTWORT BEANTWORTEN MUSS:"]
    zeilen += [f"{i}. {p}" for i, p in enumerate(brett["punkte"], 1)]
    zeilen += ["", "ERGEBNISSE DER HELFER:"]
    for a in brett["aufgaben"]:
        zeilen += [f"--- {a['helfer']}: {a['aufgabe']} ---", a.get("ergebnis") or "(kein Ergebnis)", ""]
    if mit_antwort and brett.get("antwort"):
        zeilen += ["ANTWORT DES TEXTERS:", brett["antwort"]]
    return "\n".join(zeilen)


def lauf(auftrag, frage, melde=lambda ev: None, gestoppt=lambda: False, recherche=None, max_aufgaben=MAX_AUFGABEN):
    """Führt den ganzen Team-Ablauf aus. Gibt ein dict mit text, warnungen, protokoll … zurück.
    recherche(text) -> [(titel, text, adresse)]: Internet-Quellen für den Rechercheur (ohne Wikipedia)."""
    brett = {"auftrag": auftrag, "aufgaben": [], "punkte": [], "antwort": ""}
    protokoll, modelle, anfragen = [], {}, [0]

    def f(rolle, prompt, werkzeuge=False):
        anfragen[0] += 1
        text, modell = frage(rolle, ROLLEN[rolle] + OHNE_WERKZEUGE, prompt, werkzeuge)
        modelle[rolle] = modell
        return (text or "").strip()

    def stop_pruefen():
        if gestoppt():
            raise RuntimeError("Gestoppt.")

    # ---------- 1. Chef: Plan ----------
    melde({"helfer": "Chef", "status": "arbeitet", "info": "macht einen Plan"})
    plan_roh = f("Chef",
                 f"Auftrag des Nutzers:\n{auftrag}\n\n"
                 f"Verteile den Auftrag an deine Helfer. Helfer: Rechercheur (Fakten, Möglichkeiten, Internet) und "
                 f"Rechner (nur wenn wirklich etwas zu rechnen ist: Kosten, Zinsen, Mengen, Zeiten).\n"
                 f"Höchstens {max_aufgaben} Aufgaben, jede in einem Satz. Dazu 2 bis 5 Punkte, die die fertige "
                 f"Antwort unbedingt beantworten muss.\n"
                 'Antworte NUR mit JSON: {"aufgaben":[{"helfer":"Rechercheur","aufgabe":"…"}],"punkte":["…"]}')
    plan = _json(plan_roh) or {}
    for a in (plan.get("aufgaben") or [])[:max_aufgaben]:
        if isinstance(a, dict) and a.get("helfer") in HELFER and str(a.get("aufgabe", "")).strip():
            brett["aufgaben"].append({"helfer": a["helfer"], "aufgabe": str(a["aufgabe"]).strip()})
    brett["punkte"] = [str(p).strip() for p in (plan.get("punkte") or []) if str(p).strip()][:5]
    if not brett["aufgaben"]:            # Plan unlesbar -> sicherer Ersatz statt Abbruch
        brett["aufgaben"] = [{"helfer": "Rechercheur", "aufgabe": auftrag}]
        protokoll.append("Chef-Plan war nicht lesbar – Ersatzplan benutzt.")
    if not brett["punkte"]:
        brett["punkte"] = ["Den Auftrag vollständig beantworten"]
    melde({"helfer": "Chef", "status": "fertig", "info": f"Plan: {len(brett['aufgaben'])} Aufgaben",
           "plan": brett["aufgaben"]})
    protokoll.append(f"Chef: {len(brett['aufgaben'])} Aufgaben, {len(brett['punkte'])} Prüfpunkte.")
    stop_pruefen()

    # ---------- 2. Helfer gleichzeitig ----------
    def helfer(i):
        a = brett["aufgaben"][i]
        melde({"helfer": a["helfer"], "nr": i, "status": "arbeitet", "info": a["aufgabe"]})
        try:
            quellen_text = ""
            if a["helfer"] == "Rechercheur" and recherche:
                melde({"helfer": a["helfer"], "nr": i, "status": "arbeitet", "info": "sucht im Internet …"})
                try:
                    quellen = recherche(a["aufgabe"]) or []
                except Exception:
                    quellen = []
                a["quellen"] = [q[2] for q in quellen]
                if quellen:
                    quellen_text = ("\n\nGEFUNDENE QUELLEN AUS DEM INTERNET (prüfe sie kritisch, nenne die Adresse, "
                                    "wenn du etwas daraus benutzt):\n" + "\n\n".join(
                                        f"[{n}] {t} – {u}\n{x[:2500]}" for n, (t, x, u) in enumerate(quellen, 1)))
                else:
                    quellen_text = ("\n\n(Die Internet-Suche hat nichts Brauchbares gefunden – sag ehrlich, was du "
                                    "nur aus deinem eigenen Wissen weißt.)")
                melde({"helfer": a["helfer"], "nr": i, "status": "arbeitet", "info": f"liest {len(quellen)} Quellen"})
            a["ergebnis"] = f(a["helfer"],
                              f"Gesamtauftrag des Nutzers:\n{auftrag}\n\nDeine Aufgabe vom Chef:\n{a['aufgabe']}"
                              f"{quellen_text}\n\nErledige nur deine Aufgabe. Antworte in kurzen Stichpunkten, "
                              "höchstens etwa 150 Wörter (Gratis-Gehirne schreiben langsam – jedes Wort kostet Zeit).")
            melde({"helfer": a["helfer"], "nr": i, "status": "fertig", "info": a["aufgabe"]})
        except Exception as e:
            a["ergebnis"] = ""
            protokoll.append(f"{a['helfer']} konnte nicht arbeiten: {e}")
            melde({"helfer": a["helfer"], "nr": i, "status": "fehler", "info": str(e)[:120]})

    with ThreadPoolExecutor(max_workers=min(3, len(brett["aufgaben"]))) as ex:
        list(ex.map(helfer, range(len(brett["aufgaben"]))))
    stop_pruefen()

    # ---------- 3. Texter ----------
    melde({"helfer": "Texter", "status": "arbeitet", "info": "schreibt die Antwort"})
    brett["antwort"] = f("Texter", _brett_text(brett) + "\n\nSchreib jetzt EINE fertige Antwort an den Nutzer. "
                         "Beantworte jeden Punkt. Kennzeichne Schätzungen ehrlich als Schätzung. "
                         "Höchstens etwa 350 Wörter.")
    if _muell(brett["antwort"]) and not gestoppt():          # erfundene Werkzeug-Aufrufe statt Antwort -> einmal neu
        protokoll.append("Texter schrieb Werkzeug-Aufrufe statt einer Antwort – einmal neu geschrieben.")
        melde({"helfer": "Texter", "status": "arbeitet", "info": "schreibt neu (erster Versuch unbrauchbar)"})
        brett["antwort"] = f("Texter", _brett_text(brett) + "\n\nWICHTIG: Du kannst NICHTS mehr suchen – alle Ergebnisse "
                             "stehen oben. Schreib jetzt direkt die fertige Antwort an den Nutzer in ganzen Sätzen und "
                             "Stichpunkten, höchstens etwa 350 Wörter. Keine Werkzeug-Aufrufe, keine {{…}}.")
    if _muell(brett["antwort"]):                              # immer noch unbrauchbar -> ehrlich sagen statt Unsinn
        protokoll.append("Auch der zweite Versuch des Texters war unbrauchbar.")
        brett["antwort"] = ("Es tut mir leid – mein Team hat diesmal keine brauchbare Antwort geschrieben (die Gehirne "
                            "haben Such-Befehle erfunden statt zu antworten). Die gelesenen Quellen stehen unten; "
                            "sag „nochmal“, dann versuche ich es erneut.")
    melde({"helfer": "Texter", "status": "fertig", "info": "Antwort geschrieben"})
    stop_pruefen()

    # ---------- 4. Prüfer (+ einmal nachbessern) ----------
    melde({"helfer": "Prüfer", "status": "arbeitet", "info": "prüft die Antwort"})
    pruef_roh = f("Prüfer", _brett_text(brett, mit_antwort=True) +
                  "\n\nPrüfe die ANTWORT DES TEXTERS:\n"
                  "1. Ist jeder der PUNKTE beantwortet?\n2. Stimmen Zahlen und Rechnungen?\n"
                  "3. Steht etwas als sicher da, das nur geschätzt oder nicht belegt ist?\n"
                  "4. Gewissens-Prüfung: Ist es wahr, gerecht, schadet es niemandem?\n"
                  'Antworte NUR mit JSON: {"luecken":["was fehlt oder falsch ist"],'
                  '"warnungen":["was der Nutzer wissen sollte, z. B. nur geschätzt"]}  (leere Listen, wenn alles gut ist)')
    pruef = _json(pruef_roh)
    if pruef is None and not gestoppt():                     # unlesbar -> einmal neu, ganz knapp
        protokoll.append("Prüfung war nicht lesbar – einmal neu geprüft.")
        pruef = _json(f("Prüfer", "ANTWORT, DIE DU PRÜFEN SOLLST:\n" + brett["antwort"] + "\n\nPUNKTE:\n" +
                        "\n".join(f"- {p}" for p in brett["punkte"]) +
                        '\n\nGib NUR dieses JSON aus, sonst nichts: {"luecken":[…],"warnungen":[…]}'))
    nachgebessert = False
    if pruef is None:
        luecken, warnungen = [], ["Die Prüfung war diesmal nicht lesbar – bitte Wichtiges selbst nachprüfen."]
    else:
        luecken = [str(x).strip() for x in (pruef.get("luecken") or []) if str(x).strip()][:5]
        warnungen = [str(x).strip() for x in (pruef.get("warnungen") or []) if str(x).strip()][:5]
    melde({"helfer": "Prüfer", "status": "fertig",
           "info": f"{len(luecken)} Lücken gefunden" if luecken else "alles beantwortet"})
    protokoll.append(f"Prüfer: {len(luecken)} Lücken, {len(warnungen)} Warnungen.")

    if luecken and not gestoppt():
        melde({"helfer": "Texter", "status": "arbeitet", "info": "bessert nach"})
        besser = f("Texter", _brett_text(brett, mit_antwort=True) + "\n\nDer Prüfer hat Lücken gefunden:\n" +
                   "\n".join(f"- {l}" for l in luecken) +
                   "\n\nSchreib NUR eine kurze Ergänzung, die diese Lücken schließt (nicht die ganze Antwort neu, "
                   "höchstens etwa 150 Wörter). Wenn du etwas nicht beheben kannst, sag das ehrlich.")
        if besser:
            brett["antwort"] += "\n\n**Ergänzung nach der Prüfung:**\n" + besser
            nachgebessert = True
            protokoll.append("Texter hat einmal ergänzt (danach nicht erneut geprüft).")
        melde({"helfer": "Texter", "status": "fertig", "info": "nachgebessert"})

    return {"text": brett["antwort"] or "Das Team konnte leider keine Antwort schreiben.",
            "warnungen": warnungen, "luecken": luecken, "nachgebessert": nachgebessert,
            "plan": [{"helfer": a["helfer"], "aufgabe": a["aufgabe"]} for a in brett["aufgaben"]],
            "quellen": [u for a in brett["aufgaben"] for u in a.get("quellen", [])],
            "punkte": brett["punkte"], "protokoll": protokoll, "modelle": modelle, "anfragen": anfragen[0]}
