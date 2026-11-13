"""Sammelt sichtbare deutsche Textstücke aus HTML-Seiten (statisches HTML + Texte in JavaScript).
${…} in JavaScript-Vorlagen wird zu {0}, {1} … (Platzhalter)."""
import re
from html.parser import HTMLParser

import jslex

DE = re.compile(r"[äöüÄÖÜß]|\b(der|die|das|und|ist|nicht|ein|eine|mit|für|auf|zu|du|dich|dir|dein|deine|ich|wird|noch|"
                r"keine|kein|oder|bitte|jetzt|alle|hier|was|wie|wenn|schon|nur|auch|Watson|Gespräch|Gehirn|Stimme|"
                r"Fehler|Einstellungen|Speichern|Löschen|Abbrechen|Neu|Ja|Nein|Öffnen|Bereit|Testen|Starten|Hilfe)\b", re.I)
CODEISH = re.compile(r"^[\w\-#.:\[\]=\"'()>, ]*$")


def _aus_html(h):
    out = []

    class P(HTMLParser):
        skip = 0

        def handle_starttag(s, tag, attrs):
            if tag in ("script", "style"):
                s.skip += 1
            for k, v in attrs:
                if k in ("title", "placeholder", "aria-label") and v:
                    out.append(v)

        def handle_endtag(s, tag):
            if tag in ("script", "style"):
                s.skip -= 1

        def handle_data(s, d):
            if not s.skip:
                out.append(d)
    P().feed(h)
    return out


def _gut(t):
    if len(t) < 2 or not re.search(r"[A-Za-zÄÖÜäöüß]{2}", t):
        return False
    if CODEISH.match(t) and not DE.search(t):
        return False
    if re.match(r"^(https?:|ti ti-|[\w-]+\.(py|json|md|html|txt|log|exe)$)", t):
        return False
    return bool(DE.search(t)) or bool(re.search(r"[A-ZÄÖÜ][a-zäöüß]+ [a-zäöüß]+", t))


def sammeln(dateien):
    alle = {}
    for datei in dateien:
        h = open(datei, encoding="utf-8").read()
        stuecke = _aus_html(re.sub(r"(?s)<script>.*?</script>", "", h))
        js = "\n".join(re.findall(r"(?s)<script>(.*?)</script>", h))
        for s, _ in jslex.strings(js):
            if not s:
                continue
            s2 = s.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
            stuecke += _aus_html(s2) if ("<" in s2 and ">" in s2) else [s2]
        for t in stuecke:
            t = " ".join(t.split())
            if _gut(t):
                k = [0]

                def renum(_):
                    k[0] += 1
                    return "{%d}" % (k[0] - 1)
                alle[re.sub(r"\{\d+\}", renum, t)] = True
    return sorted(alle)
