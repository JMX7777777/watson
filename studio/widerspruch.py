"""
Widerspruchs-Prüfung: Watson hält sein Wissen sauber (Idee aus dem „Second Brain“-Video, 21.11.2026).

Nachts (Abendrunde) sucht Watson Paare von Einträgen, die vom Thema her nah beieinander liegen:
Wissensbuch, Merkzettel über den Nutzer und Meinungsbuch. Ein Gehirn prüft jedes Paar:
  passt       – alles gut
  doppelt     – sagt dasselbe zweimal
  widerspruch – die beiden widersprechen sich
  veraltet    – eins ist durch das andere überholt

Wichtig:
- Es wird NICHTS überschrieben oder gelöscht. Funde werden nur markiert (widersprueche.json).
- Wissen und Merkzettel: der Nutzer entscheidet (Vorschlag im Tagebuch). Erst die Quelle klären, dann ist der Fund
  erledigt – solange beide Texte gleich bleiben, wird das Paar nicht noch einmal gemeldet.
- Meinungen: Watson denkt SELBST neu nach (freies Lernen, Bibel als Maßstab – wie bei den roten und gelben Rosen).
  Das macht meinungsbuch.nachdenken() mit den gefundenen Meinungen.
- Bei jeder Antwort sieht das Gehirn neben einem betroffenen Eintrag einen Hinweis (hinweis()).
"""
import hashlib
import json
import threading
import time

import pfade

DATEI = pfade.DATEN / "widersprueche.json"
_lock = threading.Lock()
ARTEN = ("doppelt", "widerspruch", "veraltet")
NAMEN = {"wissen": "Wissensbuch", "merkzettel": "Merkzettel", "meinung": "Meinungsbuch"}


def _laden():
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"naechste": 1, "geprueft": {}, "funde": []}


def _speichern(d):
    d["funde"] = d["funde"][-300:]
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def _schluessel(a, b):
    """Gleiches Paar mit gleichen Texten = gleicher Schlüssel. Ändert sich ein Text, wird neu geprüft."""
    a, b = sorted((a, b), key=lambda x: (x["quelle"], x["id"]))
    roh = "|".join(f"{x['quelle']}:{x['id']}:{x['text']}" for x in (a, b))
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]


def eintraege(mem=None):
    """Alles, was geprüft wird: [{quelle, id, text}]."""
    import lernbuch, meinungsbuch
    out = [{"quelle": "wissen", "id": e["id"],
            "text": (e.get("frage", "")[:200] + ": " + (e.get("kurz") or e.get("antwort") or "")[:700]).strip()}
           for e in lernbuch.wissen_liste()]
    out += [{"quelle": "meinung", "id": m["id"], "text": f"{m['thema']}: {m['meinung']}"[:700]}
            for m in meinungsbuch.alle()]
    if mem is not None:
        try:
            out += [{"quelle": "merkzettel", "id": f["id"], "text": f["text"][:700]} for f in mem.all_facts()]
        except Exception:
            pass
    return [x for x in out if len(x["text"]) > 10]


def _woerter(t):
    import lernbuch
    return lernbuch._woerter(t)


def kandidaten(liste, schon, max_paare=8):
    """Die thematisch nächsten Paare, die noch nicht (mit diesen Texten) geprüft wurden."""
    n = len(liste)
    if n < 2:
        return []
    paare = []
    try:
        import numpy as np
        import bedeutung
        v = bedeutung.einbetten([x["text"] for x in liste])
        v = v - v.mean(0)                                   # gemeinsamen Anteil abziehen, damit Nähe deutlicher wird
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
        s = v @ v.T
        for i in range(n):
            for j in range(i + 1, n):
                paare.append((float(s[i, j]), i, j))
        paare = [p for p in paare if p[0] >= 0.35]
    except Exception:                                       # ohne Bedeutungs-Modell: einfacher Wortvergleich
        w = [_woerter(x["text"]) for x in liste]
        for i in range(n):
            for j in range(i + 1, n):
                if w[i] and w[j]:
                    g = len(w[i] & w[j]) / min(len(w[i]), len(w[j]))
                    if g >= 0.4:
                        paare.append((g, i, j))
    paare.sort(reverse=True)
    out = []
    for _, i, j in paare:
        if _schluessel(liste[i], liste[j]) not in schon:
            out.append((liste[i], liste[j]))
            if len(out) >= max_paare:
                break
    return out


def pruefen(frage_fn, gehirne, json_aus, massstab="", mem=None, max_paare=8):
    """Abendrunde: nahe Paare suchen, von einem Gehirn prüfen lassen, Funde markieren. -> Bericht fürs Tagebuch."""
    d = _laden()
    paare = kandidaten(eintraege(mem), d["geprueft"], max_paare)
    if not paare:
        return {"ruhig": True, "geprueft": 0, "funde": []}
    text, _ = frage_fn([
        {"role": "system", "content": "Du bist Watson und hältst dein Wissen sauber. Prüfe jedes Paar ehrlich und "
         "genau: Sagen die beiden Einträge dasselbe (doppelt), widersprechen sie sich (widerspruch), ist einer durch "
         "den anderen überholt (veraltet) – oder passen sie zusammen (passt)? Nur ähnliches Thema ist KEIN "
         "Widerspruch; ein Widerspruch heißt: beide können nicht zugleich wahr sein. Im Zweifel: passt. "
         + (f"Dein Maßstab: {massstab[:1500]} " if massstab else "") +
         "Entscheide NICHT, welcher Eintrag recht hat, und ändere nichts – beschreibe nur kurz, was du siehst, und "
         "schlage vor, was man klären müsste. Antworte NUR als JSON: {\"ergebnisse\": [{\"nr\": 1, \"art\": "
         "\"passt|doppelt|widerspruch|veraltet\", \"erklaerung\": \"…\", \"vorschlag\": \"…\"}]}"},
        {"role": "user", "content": "\n\n".join(
            f"Paar {k}:\nA ({NAMEN[a['quelle']]} Nr. {a['id']}): {a['text']}\nB ({NAMEN[b['quelle']]} Nr. {b['id']}): {b['text']}"
            for k, (a, b) in enumerate(paare, 1))}], gehirne)
    j = json_aus(text) or {}
    ergebnisse = {}
    for x in j.get("ergebnisse") or []:
        try:
            ergebnisse[int(x.get("nr"))] = x
        except (TypeError, ValueError, AttributeError):
            pass
    if not ergebnisse:
        return {"fehler": "Das Gehirn hat keine brauchbare Antwort gegeben.", "geprueft": 0, "funde": []}
    heute = time.strftime("%d.%m.%Y %H:%M")
    bericht = {"geprueft": 0, "funde": []}
    with _lock:
        d = _laden()
        for k, (a, b) in enumerate(paare, 1):
            x = ergebnisse.get(k)
            if not x:
                continue                                    # ohne Urteil: nächste Nacht noch einmal
            d["geprueft"][_schluessel(a, b)] = heute
            bericht["geprueft"] += 1
            art = str(x.get("art", "passt")).strip().lower()
            if art not in ARTEN:
                continue
            fid = d["naechste"]
            d["naechste"] += 1
            fund = {"id": fid, "datum": heute, "art": art, "a": a, "b": b,
                    "erklaerung": str(x.get("erklaerung", ""))[:600], "vorschlag": str(x.get("vorschlag", ""))[:400],
                    "status": "offen"}
            d["funde"].append(fund)
            bericht["funde"].append(fund)
        _speichern(d)
    return bericht


def offene(quelle=None):
    return [f for f in _laden()["funde"] if f["status"] == "offen"
            and (quelle is None or quelle in (f["a"]["quelle"], f["b"]["quelle"]))]


def erledigt(fid, status):
    """status: geklaert | kein_widerspruch | watson_bedacht"""
    with _lock:
        d = _laden()
        for f in d["funde"]:
            if f["id"] == fid:
                f["status"], f["erledigt"] = status, time.strftime("%d.%m.%Y %H:%M")
                _speichern(d)
                return f
    return None


def hinweis(quelle, eid):
    """Kurzer Warnhinweis für die Antwort, wenn ein Eintrag einen offenen Fund hat (sonst "")."""
    try:
        for f in offene(quelle):
            for x, y in ((f["a"], f["b"]), (f["b"], f["a"])):
                if x["quelle"] == quelle and str(x["id"]) == str(eid):
                    wort = {"doppelt": "doppelt mit", "widerspruch": "⚠ widerspricht vielleicht",
                            "veraltet": "⚠ evtl. veraltet gegenüber"}[f["art"]]
                    return f" ({wort} {NAMEN[y['quelle']]} Nr. {y['id']}: {f['erklaerung'][:150]} – ungeklärt, sag das ehrlich)"
    except Exception:
        pass
    return ""


def als_vorschlaege(funde):
    """Funde ohne Meinung -> Vorschläge fürs Tagebuch (der Nutzer klärt sie)."""
    out = []
    for f in funde:
        if "meinung" in (f["a"]["quelle"], f["b"]["quelle"]):
            continue
        wort = {"doppelt": "Doppelt", "widerspruch": "Widerspruch", "veraltet": "Veraltet?"}[f["art"]]
        out.append({"art": "widerspruch", "fund": f["id"], "status": "offen",
                    "text": (f"{wort}: {NAMEN[f['a']['quelle']]} Nr. {f['a']['id']} und {NAMEN[f['b']['quelle']]} "
                             f"Nr. {f['b']['id']}. {f['erklaerung']}"
                             + (f" Zu klären: {f['vorschlag']}" if f['vorschlag'] else ""))[:600]})
    return out
