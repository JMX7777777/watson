"""
Watsons Super-Gedächtnis.

Drei Ebenen, wie beim Menschen:
  1. Kurzzeit:  die letzten Nachrichten des aktuellen Gesprächs
  2. Langzeit:  "Merkzettel" - kurze, dauerhafte Fakten über den Nutzer (werden automatisch erkannt)
  3. Archiv:    jedes Gespräch, das je geführt wurde - durchsuchbar

Alles liegt in EINER Datei (watson.db, SQLite). Die Volltextsuche (FTS5) findet
in Millisekunden passende Fakten und alte Gespräche - auch bei tausenden Einträgen.
Ins Gehirn kommt nur, was zur aktuellen Frage passt. Das spart Zeit und Geld.
Dazu kommt die Bedeutungs-Suche (bedeutung.py): findet auch Passendes mit anderen Wörtern
(„Bin ich verheiratet?“ -> „Der Nutzer hat eine Frau“). Fehlt das Modell, gilt nur die Stichwort-Suche.
"""
import queue
import re
import sqlite3
import threading
import time
from pathlib import Path

import numpy as np

import bedeutung

STOPWORDS = set("""
aber alle allem allen aller alles als also am an ander andere anderem anderen anderer anderes auch auf aus bei bin bis
bist da damit dann das dass dein deine dem den denn der des dich die dir doch dort du durch ein eine einem einen einer
eines er es etwas euch euer für hab habe haben hat hatte hier hin ich ihm ihn ihr im in ist ja jede jedem jeden jeder
jedes jetzt kann kannst kein keine können mache machen mal man mein meine mich mir mit muss nach nicht nichts noch nun
nur ob oder ohne sehr sein seine sich sie sind so soll sollte sondern über um und uns unser unter viel vom von vor war
waren was weil welche wenn wer werde werden wie wieder will wir wird wirst wo wollen würde zu zum zur zwischen bitte
watson hallo danke gut okay ok gibt geht schon mehr ganz immer einfach heute steht
""".split())


# Bedeutungs-Treffer zählen nur, wenn sie deutlich herausragen (gemessen 15.11.2026: 11/12 richtig, wenige Fehltreffer).
# e5-Werte liegen alle eng um 0,8 – darum wird die „Grundähnlichkeit“ (Mittelwert aller Einträge) abgezogen.
ARCHIV_VERSION = 2   # 21.11.2026: lange Stichpunkte werden an Satzenden zerlegt
SEM_Z = 2.0     # mindestens 2 Standardabweichungen über dem Durchschnitt
SEM_MIN = 0.15   # und eine kleine Mindest-Ähnlichkeit nach dem Abziehen


class Memory:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, title TEXT, created REAL, updated REAL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, chat_id INTEGER, role TEXT, name TEXT,
            content TEXT, model TEXT, ts REAL);
        CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id, id);
        CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, text TEXT, created REAL, updated REAL, chat_id INTEGER);
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, tokenize='unicode61 remove_diacritics 2');
        CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE IF NOT EXISTS vektoren(art TEXT, ref INTEGER, vec BLOB, PRIMARY KEY(art, ref));
        CREATE TABLE IF NOT EXISTS archiv(id INTEGER PRIMARY KEY, datei TEXT, titel TEXT, text TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS archiv_fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE IF NOT EXISTS archiv_stand(datei TEXT PRIMARY KEY, mtime REAL);
        """)
        self.db.commit()
        self._vcache = {}                 # art -> (ids, Matrix) für schnelle Bedeutungs-Suche
        self._vq = queue.Queue()          # neue Texte, die einen Fingerabdruck brauchen
        self._vthread = None

    # ---------- Archiv: große Notiz-Dateien in Abschnitten (Gedächtnis in Stufen, Idee wie Letta/MemGPT) ----------
    # Kern (klein, immer dabei) liefert watson_studio.read_memory(nur_kern=True).
    # Archiv (groß: Verlauf, Projekte, Überblick …) wird in Abschnitte zerlegt; pro Frage kommen nur die passenden mit.
    @staticmethod
    def _abschnitte(text, max_zeichen=1200):
        """Zerlegt Markdown nach Überschriften und dann in Stichpunkt-Gruppen -> [(titel, text)]."""
        aus, pfad, block = [], [], []

        def fertig():
            inhalt = "\n".join(block).strip()
            block.clear()
            if not inhalt:
                return
            titel = " › ".join(pfad) or "Anfang"
            stueck, teile = [], []
            for zeile in inhalt.split("\n"):     # neuer Teil nur an einem neuen Stichpunkt / Absatz
                neu_punkt = zeile.startswith(("- ", "* ", "|")) or not zeile.strip()
                if stueck and neu_punkt and sum(len(z) + 1 for z in stueck) + len(zeile) > max_zeichen:
                    teile.append("\n".join(stueck).strip())
                    stueck = []
                stueck.append(zeile)
            teile.append("\n".join(stueck).strip())
            # Ein einzelner Riesen-Stichpunkt (gemessen 21.11.2026: ~10.000 Zeichen) ging sonst ganz mit.
            # -> an Satzenden weiter zerlegen, damit jeder Ausschnitt klein bleibt (spart Tokens).
            kleine = []
            for t in teile:
                while len(t) > max_zeichen * 1.5:
                    schnitt = max(t.rfind(". ", 0, max_zeichen), t.rfind("; ", 0, max_zeichen), t.rfind("\n", 0, max_zeichen))
                    schnitt = schnitt + 1 if schnitt > max_zeichen // 3 else max_zeichen
                    kleine.append(t[:schnitt].strip())
                    t = t[schnitt:].strip()
                kleine.append(t)
            aus.extend((titel, t) for t in kleine if t)

        for zeile in text.splitlines():
            m = re.match(r"^(#{1,4})\s+(.*)", zeile)
            if m:
                fertig()
                tiefe = len(m.group(1))
                pfad[:] = pfad[:tiefe - 1] + [m.group(2).strip()]
            else:
                block.append(zeile)
        fertig()
        return aus

    def archiv_sync(self, dateien):
        """Bringt das Archiv auf den Stand der Dateien (nur geänderte werden neu zerlegt). Schnell, wenn nichts neu ist."""
        dateien = [Path(d) for d in dateien if Path(d).exists()]
        stand = {r["datei"]: r["mtime"] for r in self._x("SELECT datei, mtime FROM archiv_stand").fetchall()}
        namen = {d.name for d in dateien}
        for alt in [n for n in stand if n not in namen]:              # Datei gibt es nicht mehr
            self._archiv_leeren(alt)
        for d in dateien:
            mt = f"{d.stat().st_mtime}|{ARCHIV_VERSION}"   # neue Zerlege-Art -> alles einmal neu zerlegen
            if stand.get(d.name) == mt:
                continue
            self._archiv_leeren(d.name)
            stuecke = self._abschnitte(d.read_text(encoding="utf-8"))
            neu = []
            with self.lock:
                for titel, text in stuecke:
                    aid = self.db.execute("INSERT INTO archiv(datei, titel, text) VALUES(?,?,?)",
                                          (d.name, titel, text)).lastrowid
                    self.db.execute("INSERT INTO archiv_fts(rowid, text) VALUES(?,?)", (aid, f"{titel}\n{text}"))
                    neu.append(("archiv", aid, f"{titel}\n{text}"))
                self.db.execute("INSERT OR REPLACE INTO archiv_stand(datei, mtime) VALUES(?,?)", (d.name, mt))
                self.db.commit()
            for e in neu:
                self._v_neu(*e)

    def _archiv_leeren(self, datei):
        ids = [r["id"] for r in self._x("SELECT id FROM archiv WHERE datei=?", (datei,)).fetchall()]
        with self.lock:
            self.db.executemany("DELETE FROM archiv_fts WHERE rowid=?", [(i,) for i in ids])
            self.db.execute("DELETE FROM archiv WHERE datei=?", (datei,))
            self.db.execute("DELETE FROM archiv_stand WHERE datei=?", (datei,))
            self.db.commit()
        if ids:
            self._v_loeschen("archiv", ids)

    def relevant_archiv(self, text, k=4):
        """Die passendsten Archiv-Abschnitte: Bedeutung zuerst, dann Stichwort, ohne Doppelte."""
        ids = [ref for ref, _ in self._v_suche("archiv", text, k)]
        q = self.query_from(text)
        if q:
            ids += [r["rowid"] for r in self._x(
                "SELECT rowid FROM archiv_fts WHERE archiv_fts MATCH ? ORDER BY bm25(archiv_fts) LIMIT ?",
                (q, k)).fetchall()]
        aus = []
        for i in dict.fromkeys(ids):
            r = self._x("SELECT datei, titel, text FROM archiv WHERE id=?", (i,)).fetchone()
            if r:
                aus.append(dict(r))
            if len(aus) >= k:
                break
        return aus

    # ---------- Bedeutungs-Suche ----------
    def bedeutung_starten(self):
        """Modell laden und alles, was noch keinen Fingerabdruck hat, nachholen (im Hintergrund)."""
        if self._vthread and self._vthread.is_alive():
            return
        self._vthread = threading.Thread(target=self._v_arbeiter, daemon=True)
        self._vthread.start()

    def _v_arbeiter(self):
        if not bedeutung.laden():
            return
        fehlend = [("fact", r["id"], r["text"]) for r in self._x(
            "SELECT id, text FROM facts WHERE id NOT IN (SELECT ref FROM vektoren WHERE art='fact')").fetchall()]
        fehlend += [("msg", r["id"], r["content"]) for r in self._x(
            "SELECT id, content FROM messages WHERE role IN ('user','assistant') "
            "AND id NOT IN (SELECT ref FROM vektoren WHERE art='msg')").fetchall()]
        fehlend += [("archiv", r["id"], f"{r['titel']}\n{r['text']}") for r in self._x(
            "SELECT id, titel, text FROM archiv WHERE id NOT IN (SELECT ref FROM vektoren WHERE art='archiv')").fetchall()]
        for i in range(0, len(fehlend), 16):
            self._v_speichern(fehlend[i:i + 16])
        while True:
            stapel = [self._vq.get()]
            while not self._vq.empty() and len(stapel) < 16:
                stapel.append(self._vq.get_nowait())
            self._v_speichern(stapel)

    def _v_speichern(self, eintraege):
        eintraege = [e for e in eintraege if e[2] and e[2].strip()]
        if not eintraege:
            return
        try:
            vecs = bedeutung.einbetten([e[2][:2000] for e in eintraege])
        except Exception:
            return
        with self.lock:
            self.db.executemany("INSERT OR REPLACE INTO vektoren(art, ref, vec) VALUES(?,?,?)",
                                [(a, r, v.tobytes()) for (a, r, _), v in zip(eintraege, vecs)])
            self.db.commit()
        for a in {e[0] for e in eintraege}:
            self._vcache.pop(a, None)

    def _v_neu(self, art, ref, text):
        if self._vthread:
            self._vq.put((art, ref, text))

    def _v_loeschen(self, art, refs):
        with self.lock:
            self.db.executemany("DELETE FROM vektoren WHERE art=? AND ref=?", [(art, r) for r in refs])
            self.db.commit()
        self._vcache.pop(art, None)

    def _v_suche(self, art, text, k):
        """[(ref, ähnlichkeit)] – die k bedeutungsnächsten Einträge. Leer, wenn das Modell fehlt."""
        if not bedeutung.bereit() or not (text or "").strip():
            return []
        if art not in self._vcache:
            rows = self._x("SELECT ref, vec FROM vektoren WHERE art=?", (art,)).fetchall()
            ids = [r["ref"] for r in rows]
            if not rows:
                return []
            mat = np.frombuffer(b"".join(r["vec"] for r in rows), np.float32).reshape(-1, bedeutung.DIM)
            mu = mat.mean(0)
            mat = mat - mu
            mat /= np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)
            self._vcache[art] = (ids, mat, mu)
        ids, mat, mu = self._vcache[art]
        try:
            q = bedeutung.einbetten([text[:2000]], "query")[0] - mu
        except Exception:
            return []
        q /= max(float(np.linalg.norm(q)), 1e-9)
        s = mat @ q
        z = (s - s.mean()) / s.std() if len(s) >= 5 and s.std() > 0 else np.full_like(s, SEM_Z)
        oben = np.argsort(-s)[:k]
        return [(ids[i], float(s[i])) for i in oben if z[i] >= SEM_Z and s[i] >= SEM_MIN]

    # ---------- Hilfen ----------
    @staticmethod
    def query_from(text, max_terms=12):
        words = re.findall(r"[\wäöüÄÖÜß]{3,}", text.lower())
        seen, terms = set(), []
        for w in words:
            if w in STOPWORDS or w in seen:
                continue
            seen.add(w)
            terms.append(f'"{w}"*')
            if len(terms) >= max_terms:
                break
        return " OR ".join(terms)

    def _x(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    # ---------- Gespräche ----------
    def new_chat(self, title="Neues Gespräch"):
        now = time.time()
        return self._x("INSERT INTO chats(title, created, updated) VALUES(?,?,?)", (title, now, now)).lastrowid

    def list_chats(self, limit=60):
        rows = self._x("SELECT id, title, updated FROM chats ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def delete_chat(self, chat_id):
        ids = [r["id"] for r in self._x("SELECT id FROM messages WHERE chat_id=?", (chat_id,)).fetchall()]
        with self.lock:
            self.db.executemany("DELETE FROM messages_fts WHERE rowid=?", [(i,) for i in ids])
            self.db.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
            self.db.execute("DELETE FROM chats WHERE id=?", (chat_id,))
            self.db.commit()
        self._v_loeschen("msg", ids)

    def add_message(self, chat_id, role, content, name="", model=""):
        now = time.time()
        with self.lock:
            mid = self.db.execute("INSERT INTO messages(chat_id, role, name, content, model, ts) VALUES(?,?,?,?,?,?)",
                                  (chat_id, role, name, content, model, now)).lastrowid
            self.db.execute("INSERT INTO messages_fts(rowid, content) VALUES(?,?)", (mid, content))
            self.db.execute("UPDATE chats SET updated=? WHERE id=?", (now, chat_id))
            if role == "user":
                row = self.db.execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone()
                if row and row["title"] == "Neues Gespräch":
                    title = content.strip().replace("\n", " ")
                    self.db.execute("UPDATE chats SET title=? WHERE id=?",
                                    (title[:48] + ("…" if len(title) > 48 else ""), chat_id))
            self.db.commit()
        if role in ("user", "assistant"):
            self._v_neu("msg", mid, content)
        return mid

    def messages(self, chat_id, limit=None):
        sql = "SELECT id, role, name, content, model FROM messages WHERE chat_id=? ORDER BY id"
        rows = [dict(r) for r in self._x(sql, (chat_id,)).fetchall()]
        return rows[-limit:] if limit else rows

    def kuerzen_ab(self, chat_id, msg_id):
        """Löscht die Nachricht msg_id und alle späteren im Gespräch (für „Nachricht bearbeiten“). Gibt die Anzahl zurück."""
        ids = [r["id"] for r in self._x("SELECT id FROM messages WHERE chat_id=? AND id>=?", (chat_id, msg_id)).fetchall()]
        if not ids:
            return 0
        with self.lock:
            self.db.executemany("DELETE FROM messages_fts WHERE rowid=?", [(i,) for i in ids])
            self.db.execute("DELETE FROM messages WHERE chat_id=? AND id>=?", (chat_id, msg_id))
            self.db.execute("UPDATE chats SET updated=? WHERE id=?", (time.time(), chat_id))
            self.db.commit()
        self._v_loeschen("msg", ids)
        return len(ids)

    # ---------- Merkzettel (Fakten) ----------
    def add_fact(self, text, chat_id=None):
        now = time.time()
        with self.lock:
            fid = self.db.execute("INSERT INTO facts(text, created, updated, chat_id) VALUES(?,?,?,?)",
                                  (text, now, now, chat_id)).lastrowid
            self.db.execute("INSERT INTO facts_fts(rowid, text) VALUES(?,?)", (fid, text))
            self.db.commit()
        self._v_neu("fact", fid, text)
        return fid

    def update_fact(self, fid, text):
        with self.lock:
            self.db.execute("UPDATE facts SET text=?, updated=? WHERE id=?", (text, time.time(), fid))
            self.db.execute("DELETE FROM facts_fts WHERE rowid=?", (fid,))
            self.db.execute("INSERT INTO facts_fts(rowid, text) VALUES(?,?)", (fid, text))
            self.db.commit()
        self._v_neu("fact", fid, text)

    def delete_fact(self, fid):
        with self.lock:
            self.db.execute("DELETE FROM facts WHERE id=?", (fid,))
            self.db.execute("DELETE FROM facts_fts WHERE rowid=?", (fid,))
            self.db.commit()
        self._v_loeschen("fact", [fid])

    def all_facts(self):
        return [dict(r) for r in self._x("SELECT id, text, updated FROM facts ORDER BY updated DESC").fetchall()]

    def count(self):
        q = lambda t: self._x(f"SELECT count(*) FROM {t}").fetchone()[0]
        return {"chats": q("chats"), "messages": q("messages"), "facts": q("facts")}

    # ---------- Suchen ----------
    def relevant_facts(self, text, k=10):
        q = self.query_from(text)
        found = []
        if q:
            rows = self._x("SELECT f.id, f.text FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                           "WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts) LIMIT ?", (q, k)).fetchall()
            found = [dict(r) for r in rows]
        found = self._mit_bedeutung(text, found, 3)
        # die neuesten Fakten immer mitnehmen (z. B. "Der Nutzer heißt Anna")
        have = {f["id"] for f in found}
        for r in self._x("SELECT id, text FROM facts ORDER BY updated DESC LIMIT 5").fetchall():
            if r["id"] not in have and len(found) < k + 5:
                found.append(dict(r))
        return found

    def _mit_bedeutung(self, text, found, n):
        """Bis zu n Fakten aus der Bedeutungs-Suche VOR die Stichwort-Treffer stellen (ohne Doppelte)."""
        treffer = self._v_suche("fact", text, n)
        if not treffer:
            return found
        have = {f["id"] for f in found}
        neu = []
        for ref, _ in treffer:
            if ref in have:
                continue
            r = self._x("SELECT id, text FROM facts WHERE id=?", (ref,)).fetchone()
            if r:
                neu.append(dict(r))
        return neu + found

    def _msg_bedeutung(self, text, exclude_chat, n, schnipsel=240):
        """Gesprächsstellen aus der Bedeutungs-Suche, im selben Format wie die Stichwort-Treffer."""
        aus = []
        for ref, _ in self._v_suche("msg", text, n * 3):
            r = self._x("SELECT m.id, m.chat_id, m.role, m.ts, m.content, c.title FROM messages m "
                        "JOIN chats c ON c.id = m.chat_id WHERE m.id=? AND m.chat_id != ?",
                        (ref, exclude_chat or -1)).fetchone()
            if r:
                t = " ".join(r["content"].split())
                aus.append({"id": r["id"], "chat_id": r["chat_id"], "role": r["role"], "ts": r["ts"], "title": r["title"],
                            "snip": t[:schnipsel] + (" …" if len(t) > schnipsel else "")})
            if len(aus) >= n:
                break
        return aus

    @staticmethod
    def _zusammen(zuerst, danach, k):
        seen, aus = set(), []
        for r in zuerst + danach:
            key = r.get("id") or (r.get("chat_id"), r.get("ts"))
            if key in seen:
                continue
            seen.add(key)
            aus.append(r)
        return aus[:k]

    def relevant_past(self, text, exclude_chat=None, k=5):
        q = self.query_from(text)
        rows = []
        if q:
            rows = [dict(r) for r in self._x(
                "SELECT m.id, m.chat_id, m.role, m.ts, c.title, snippet(messages_fts, 0, '', '', ' … ', 40) AS snip "
                "FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid JOIN chats c ON c.id = m.chat_id "
                "WHERE messages_fts MATCH ? AND m.chat_id != ? ORDER BY bm25(messages_fts) LIMIT ?",
                (q, exclude_chat or -1, k)).fetchall()]
        return self._zusammen(self._msg_bedeutung(text, exclude_chat, 2), rows, k)

    def search(self, text, k=30):
        """Für die Suche im Gedächtnis-Tab: Fakten + Gesprächsstellen."""
        q = self.query_from(text, 20)
        facts, msgs = [], []
        if q:
            facts = [dict(r) for r in self._x(
                "SELECT f.id, f.text FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                "WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts) LIMIT ?", (q, k)).fetchall()]
            msgs = [dict(r) for r in self._x(
                "SELECT m.id, m.chat_id, m.role, m.ts, c.title, snippet(messages_fts, 0, '[', ']', ' … ', 24) AS snip "
                "FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid JOIN chats c ON c.id = m.chat_id "
                "WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts) LIMIT ?", (q, k)).fetchall()]
        facts = self._mit_bedeutung(text, facts, 5)[:k]
        msgs = self._zusammen(self._msg_bedeutung(text, None, 5, 160), msgs, k)
        return {"facts": facts, "messages": msgs}

    def export_markdown(self, path: Path):
        """Merkzettel auch als Datei in den Gedächtnis-Ordner legen, damit Watson in Claude ihn ebenfalls kennt."""
        facts = self.all_facts()
        lines = ["# Erinnerungen aus Watson Studio", "",
                 "_Automatisch erstellt von Watson Studio. Änderungen bitte im Programm (Tab Gedächtnis) machen._", ""]
        lines += [f"- {f['text']} ({time.strftime('%d.%m.%Y', time.localtime(f['updated']))})" for f in facts]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
