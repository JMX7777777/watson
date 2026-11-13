"""
Watsons MCP-Steckdose.

MCP (Model Context Protocol) ist ein Standard, mit dem KI-Programme fertige Werkzeuge
"einstecken" können: Webseiten lesen, Dateien, Mail, Kalender, Browser, n8n …
Die Werkzeuge stehen in mcp.json - im selben Format wie bei Claude Desktop,
damit man Beispiele aus GitHub-Anleitungen direkt übernehmen kann.
"""
import asyncio
import json
import os
import re
import threading
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)[:30]


class McpHub:
    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.servers = {}      # name -> {"session", "tools", "error", "trusted", "stack"}
        self.lock = threading.Lock()

    # ---------- Konfiguration ----------
    def read_config(self):
        if not self.config_file.exists():
            return {}
        data = json.loads(self.config_file.read_text(encoding="utf-8"))
        return data.get("mcpServers", {})

    def _run(self, coro, timeout=60):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    # ---------- Verbinden ----------
    async def _connect_one(self, name, spec):
        stack = AsyncExitStack()
        entry = {"session": None, "tools": [], "error": "", "trusted": bool(spec.get("trusted")),
                 "safe_tools": set(spec.get("safe_tools", [])),
                 "stack": stack, "disabled": bool(spec.get("disabled"))}
        if entry["disabled"]:
            entry["error"] = "ausgeschaltet"
            return entry
        try:
            # Node.js/npm immer im Suchpfad, auch wenn Windows den neuen PATH noch nicht kennt
            env = dict(os.environ)
            extra = [r"C:\Program Files\nodejs", os.path.expandvars(r"%APPDATA%\npm")]
            env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
            # Platzhalter wie ${WATSON:n8n_api_key} aus Watsons Einstellungen füllen (Schlüssel stehen nicht in mcp.json)
            try:
                settings = json.loads((self.config_file.parent / "einstellungen.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                settings = {}
            def _wert(name):
                try:                      # Schlüssel kommen aus dem verschlüsselten Tresor
                    import tresor
                    v = tresor.lesen(name)
                    if v:
                        return v
                except Exception:
                    pass
                return str(settings.get(name, ""))
            fuellen = lambda v: re.sub(r"\$\{WATSON:(\w+)\}", lambda m: _wert(m.group(1)), str(v))
            if spec.get("url"):
                # Online-Dienst (läuft beim Anbieter) – nur über verschlüsseltes https
                url = str(spec["url"])
                if not url.startswith("https://"):
                    raise ValueError("Online-Werkzeuge nur über https")
                from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
                kopf = {k: fuellen(v) for k, v in (spec.get("headers") or {}).items()}
                client = await stack.enter_async_context(create_mcp_http_client(headers=kopf or None))
                streams = await stack.enter_async_context(streamable_http_client(url, http_client=client))
                read, write = streams[0], streams[1]
            else:
                for k, v in (spec.get("env") or {}).items():
                    env[k] = fuellen(v)
                params = StdioServerParameters(command=spec["command"], args=spec.get("args", []),
                                               env=env, cwd=spec.get("cwd"))
                read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), 30)
            tools = (await asyncio.wait_for(session.list_tools(), 30)).tools
            entry.update(session=session, tools=tools)
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"[:300]
            if spec.get("url") and "https" not in entry["error"]:
                entry["error"] = ("Der Online-Dienst hat abgelehnt – meist verlangt er eine Anmeldung oder einen Schlüssel "
                                  "beim Anbieter. (" + entry["error"][:160] + ")")
            try:
                await stack.aclose()
            except Exception:
                pass
        return entry

    async def _connect_all(self):
        for e in self.servers.values():
            try:
                await e["stack"].aclose()
            except Exception:
                pass
        self.servers = {}
        for name, spec in self.read_config().items():
            self.servers[name] = await self._connect_one(name, spec)

    def reload(self):
        with self.lock:
            try:
                self._run(self._connect_all(), timeout=180)
            except json.JSONDecodeError as e:
                self.servers = {}
                return {"error": f"mcp.json hat einen Schreibfehler: {e}"}
        return {"ok": True}

    # ---------- Auskunft ----------
    def status(self):
        return [{"name": n, "ok": e["session"] is not None, "error": e["error"], "trusted": e["trusted"],
                 "safe_count": len(e["safe_tools"]),
                 "tools": [{"name": t.name, "description": (t.description or "")[:200],
                            "asks": not (e["trusted"] or t.name in e["safe_tools"])} for t in e["tools"]]}
                for n, e in self.servers.items()]

    def openai_tools(self):
        """Werkzeuge im Format, das die Gehirne (über OpenRouter) verstehen."""
        out = []
        for n, e in self.servers.items():
            for t in e["tools"]:
                out.append({"type": "function", "function": {
                    "name": f"{_safe(n)}__{_safe(t.name)}"[:64],
                    "description": (t.description or t.name)[:1000],
                    "parameters": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
                                  or {"type": "object", "properties": {}},
                }})
        return out

    def find(self, fullname):
        for n, e in self.servers.items():
            for t in e["tools"]:
                if f"{_safe(n)}__{_safe(t.name)}"[:64] == fullname:
                    return n, t.name, e
        return None, None, None

    # ---------- Benutzen ----------
    def call(self, fullname, arguments):
        server, tool, entry = self.find(fullname)
        if not entry or not entry["session"]:
            return f"Werkzeug {fullname} ist nicht verfügbar."
        result = self._run(entry["session"].call_tool(tool, arguments or {}), timeout=120)
        texts = []
        for c in result.content:
            if getattr(c, "type", "") == "text":
                texts.append(c.text)
            else:
                texts.append(f"[{getattr(c, 'type', 'Inhalt')}]")
        text = "\n".join(texts) or "(keine Ausgabe)"
        if getattr(result, "is_error", False) or getattr(result, "isError", False):
            text = "FEHLER: " + text
        return text[:12000]
