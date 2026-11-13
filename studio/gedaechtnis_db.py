"""
Watsons Super-Gedächtnis.

Drei Ebenen, wie beim Menschen:
  1. Kurzzeit:  die letzten Nachrichten des aktuellen Gesprächs
  2. Langzeit:  "Merkzettel" - kurze, dauerhafte Fakten über den Nutzer (werden automatisch erkannt)
  3. Archiv:    jedes Gespräch, das je geführt wurde - durchsuchbar

Alles liegt in EINER Datei (watson.db, SQLite). Die Volltextsuche (FTS5) findet
in Millisekunden passende Fakten und alte Gespräche - auch bei tausenden Einträgen.
Ins Gehirn kommt nur, was zur aktuellen Frage passt. Das spart Zeit und Geld.
"""
import re
import sqlite3
import threading
import time
from pathlib import Path

STOPWORDS = set("""
aber alle allem allen aller alles als also am an ander andere anderem anderen anderer anderes auch auf aus bei bin bis
bist da damit dann das dass dein deine dem den denn der des dich die dir doch dort du durch ein eine einem einen einer
eines er es etwas euch euer für hab habe haben hat hatte hier hin ich ihm ihn ihr im in ist ja jede jedem jeden jeder
jedes jetzt kann kannst kein keine können mache machen mal man mein meine mich mir mit muss nach nicht nichts noch nun
nur ob oder ohne sehr sein seine sich sie sind so soll sollte sondern über um und uns unser unter viel vom von vor war
waren was weil welche wenn wer werde werden wie wieder will wir wird wirst wo wollen würde zu zum zur zwischen bitte
watson hallo danke gut okay ok gibt geht schon mehr ganz immer einfach
""".split())


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
        """)
        self.db.commit()

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
        return mid

    def messages(self, chat_id, limit=None):
        sql = "SELECT role, name, content, model FROM messages WHERE chat_id=? ORDER BY id"
        rows = [dict(r) for r in self._x(sql, (chat_id,)).fetchall()]
        return rows[-limit:] if limit else rows

    # ---------- Merkzettel (Fakten) ----------
    def add_fact(self, text, chat_id=None):
        now = time.time()
        with self.lock:
            fid = self.db.execute("INSERT INTO facts(text, created, updated, chat_id) VALUES(?,?,?,?)",
                                  (text, now, now, chat_id)).lastrowid
            self.db.execute("INSERT INTO facts_fts(rowid, text) VALUES(?,?)", (fid, text))
            self.db.commit()
        return fid

    def update_fact(self, fid, text):
        with self.lock:
            self.db.execute("UPDATE facts SET text=?, updated=? WHERE id=?", (text, time.time(), fid))
            self.db.execute("DELETE FROM facts_fts WHERE rowid=?", (fid,))
            self.db.execute("INSERT INTO facts_fts(rowid, text) VALUES(?,?)", (fid, text))
            self.db.commit()

    def delete_fact(self, fid):
        with self.lock:
            self.db.execute("DELETE FROM facts WHERE id=?", (fid,))
            self.db.execute("DELETE FROM facts_fts WHERE rowid=?", (fid,))
            self.db.commit()

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
        # die neuesten Fakten immer mitnehmen (z. B. "Der Nutzer heißt Anna")
        have = {f["id"] for f in found}
        for r in self._x("SELECT id, text FROM facts ORDER BY updated DESC LIMIT 5").fetchall():
            if r["id"] not in have and len(found) < k + 5:
                found.append(dict(r))
        return found

    def relevant_past(self, text, exclude_chat=None, k=5):
        q = self.query_from(text)
        if not q:
            return []
        rows = self._x(
            "SELECT m.chat_id, m.role, m.ts, c.title, snippet(messages_fts, 0, '', '', ' … ', 40) AS snip "
            "FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid JOIN chats c ON c.id = m.chat_id "
            "WHERE messages_fts MATCH ? AND m.chat_id != ? ORDER BY bm25(messages_fts) LIMIT ?",
            (q, exclude_chat or -1, k)).fetchall()
        return [dict(r) for r in rows]

    def search(self, text, k=30):
        """Für die Suche im Gedächtnis-Tab: Fakten + Gesprächsstellen."""
        q = self.query_from(text, 20)
        if not q:
            return {"facts": [], "messages": []}
        facts = [dict(r) for r in self._x(
            "SELECT f.id, f.text FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts) LIMIT ?", (q, k)).fetchall()]
        msgs = [dict(r) for r in self._x(
            "SELECT m.chat_id, m.role, m.ts, c.title, snippet(messages_fts, 0, '[', ']', ' … ', 24) AS snip "
            "FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid JOIN chats c ON c.id = m.chat_id "
            "WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts) LIMIT ?", (q, k)).fetchall()]
        return {"facts": facts, "messages": msgs}

    def export_markdown(self, path: Path):
        """Merkzettel auch als Datei in den Gedächtnis-Ordner legen, damit Watson in Claude ihn ebenfalls kennt."""
        facts = self.all_facts()
        lines = ["# Erinnerungen aus Watson Studio", "",
                 "_Automatisch erstellt von Watson Studio. Änderungen bitte im Programm (Tab Gedächtnis) machen._", ""]
        lines += [f"- {f['text']} ({time.strftime('%d.%m.%Y', time.localtime(f['updated']))})" for f in facts]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
