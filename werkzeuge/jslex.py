"""Kleiner JavaScript-Leser: findet alle Text-Literale ('…', "…", `…${x}…`), überspringt Kommentare und Regex."""


def strings(js):
    out, i, n = [], 0, len(js)
    prev = ""          # letztes bedeutsames Zeichen (für Regex-Erkennung)
    while i < n:
        c = js[i]
        if c == "/" and js.startswith("//", i):
            j = js.find("\n", i); i = n if j < 0 else j; continue
        if c == "/" and js.startswith("/*", i):
            j = js.find("*/", i + 2); i = n if j < 0 else j + 2; continue
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^"):
            # Regex-Literal
            i += 1; klasse = False
            while i < n:
                if js[i] == "\\": i += 2; continue
                if js[i] == "[": klasse = True
                elif js[i] == "]": klasse = False
                elif js[i] == "/" and not klasse: break
                elif js[i] == "\n": break
                i += 1
            i += 1
            while i < n and js[i].isalpha(): i += 1
            prev = "r"; continue
        if c in "'\"":
            j, buf = i + 1, []
            while j < n and js[j] != c:
                if js[j] == "\\" and j + 1 < n: buf.append(js[j:j + 2]); j += 2; continue
                if js[j] == "\n": break
                buf.append(js[j]); j += 1
            out.append(("".join(buf), False)); i = j + 1; prev = "s"; continue
        if c == "`":
            j, buf, teile = i + 1, [], 0
            while j < n and js[j] != "`":
                if js[j] == "\\": buf.append(js[j:j + 2]); j += 2; continue
                if js.startswith("${", j):
                    tiefe, k = 1, j + 2
                    while k < n and tiefe:
                        if js[k] == "{": tiefe += 1
                        elif js[k] == "}": tiefe -= 1
                        elif js[k] == "`":   # verschachtelte Vorlage: Inhalt mit auswerten
                            sub_ende = js.find("`", k + 1)
                            k = sub_ende if sub_ende > 0 else k
                        k += 1
                    innen = js[j + 2:k - 1]
                    out.extend(strings(innen))       # Texte in ${…} auch einsammeln
                    buf.append("{%d}" % teile); teile += 1; j = k; continue
                buf.append(js[j]); j += 1
            out.append(("".join(buf), True)); i = j + 1; prev = "s"; continue
        if not c.isspace():
            prev = c if not (c.isalnum() or c in "_$") else "a"
            # nach Schlüsselwörtern wie return/typeof kommt ein Ausdruck -> Regex möglich
            if c.isalpha():
                j = i
                while j < n and (js[j].isalnum() or js[j] in "_$"): j += 1
                wort = js[i:j]
                prev = "(" if wort in ("return", "typeof", "case", "in", "of", "do", "else") else "a"
                i = j; continue
        i += 1
    return out
