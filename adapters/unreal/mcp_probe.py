"""Minimal MCP client for UE 5.8's Unreal MCP server (stdlib only).

CRITICAL: the server ties the session to a single persistent HTTP/1.1
connection (one-shot urllib per request gets empty streams). This client keeps
one http.client.HTTPConnection for init -> notify -> call.

Usage:
  python adapters/unreal/mcp_probe.py [tools/list|call <tool_name> '<json_args>']
  # call form: python mcp_probe.py call list_toolsets '{}'
  # toolset tools go through the dispatcher:
  #   python mcp_probe.py call call_tool '{"tool_name":"list_toolsets"}'
  #   python mcp_probe.py call call_tool '{"toolset_name":"EditorToolset","tool_name":"...","arguments":{...}}'
Env: MCP_URL (default http://127.0.0.1:8000/mcp)
"""
from __future__ import annotations

import http.client
import json
import os
import sys
import urllib.parse

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")


class Session:
    def __init__(self, url: str):
        u = urllib.parse.urlparse(url)
        self.conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=300)
        self.path = u.path or "/mcp"
        self.sid: str | None = None
        self._id = 0
        self._hello()

    def _hello(self):
        res = self._rpc("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "hermes-probe", "version": "0.1"}})
        server = res.get("serverInfo", {}) if isinstance(res, dict) else {}
        print("SERVER", json.dumps(server, ensure_ascii=False))
        self._notify("notifications/initialized")

    def _raw(self, payload: dict) -> tuple[int, bytes]:
        self._id += 1
        body = json.dumps(payload).encode()
        heads = {"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"}
        if self.sid:
            heads["Mcp-Session-Id"] = self.sid
        self.conn.request("POST", self.path, body=body, headers=heads)
        res = self.conn.getresponse()
        sid = res.getheader("Mcp-Session-Id")
        if sid:
            self.sid = sid
        data = res.read()
        return res.status, data

    def _payload_text(self, data: bytes) -> str:
        text = data.decode("utf-8", "replace")
        if "data:" in text:
            cands = [ln[5:].strip() for ln in text.splitlines()
                     if ln.startswith("data:")]
            for cand in reversed(cands):
                try:
                    json.loads(cand)
                    return cand
                except Exception:  # noqa: BLE001 - try an earlier chunk
                    continue
        return text

    def _rpc(self, method: str, params: dict):
        st, data = self._raw({"jsonrpc": "2.0", "id": self._id + 1,
                              "method": method, "params": params})
        if st >= 400:
            raise SystemExit(f"HTTP {st}: {data[:300]!r}")
        out = json.loads(self._payload_text(data))
        if isinstance(out, dict) and "error" in out:
            raise SystemExit(f"RPC error: {json.dumps(out['error'])[:600]}")
        return out.get("result")

    def _notify(self, method: str):
        self.conn.request("POST", self.path,
                          body=json.dumps({"jsonrpc": "2.0", "method": method}).encode(),
                          headers={"Content-Type": "application/json",
                                   "Accept": "application/json, text/event-stream",
                                   **({"Mcp-Session-Id": self.sid} if self.sid else {})})
        self.conn.getresponse().read()

    def call(self, name: str, args: dict):
        return self._rpc("tools/call", {"name": name, "arguments": args})


def main() -> None:
    s = Session(URL)
    mode = sys.argv[1] if len(sys.argv) > 1 else "tools/list"
    if mode == "tools/list":
        res = s._rpc("tools/list", {})
        for t in res.get("tools", []):
            print(f"  - {t['name']}: {(t.get('description') or '')[:110]}")
    elif mode == "call":
        name, args = sys.argv[2], json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")
        res = s.call(name, args)
        print(json.dumps(res, ensure_ascii=False, indent=1)[:6000])
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
