#!/usr/bin/env python3
"""Dependency-free MCP stdio server for the explicitly configured live Godot editor.

Pinned MCP handshake dialect 2025-11-25, with 2025-06-18 / 2025-03-26 support.
All stdout is newline-delimited JSON-RPC. Diagnostics belong on stderr only.
"""
from __future__ import annotations

import argparse
import json
import sys

from editor_bridge_client import BridgeError, DEFAULT_TIMEOUT, EditorBridgeClient, OPERATIONS, _json_load

VERSION = "0.2.1"
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
MAX_FRAME_BYTES = 2 * 1024 * 1024


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def tool_result(result, *, is_error=False, structured=True):
    value = result if isinstance(result, dict) else {"result": result}
    output = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)}],
              "isError": is_error}
    if structured:
        output["structuredContent"] = value
    return output


class McpServer:
    def __init__(self, project=None, timeout=DEFAULT_TIMEOUT):
        self.project, self.timeout = project, timeout
        self.initialized = False
        self.ready = False
        self.protocol_version = SUPPORTED_VERSIONS[0]
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = EditorBridgeClient(self.project, timeout=self.timeout)
        return self._client

    def handle(self, message):
        request_id = None
        notification = False
        try:
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise RpcError(-32600, "Expected one JSON-RPC 2.0 object (batch messages are not supported)")
            if "id" in message:
                supplied_id = message["id"]
                if type(supplied_id) not in (str, int) or (isinstance(supplied_id, str) and len(supplied_id) > 256):
                    raise RpcError(-32600, "Request id must be an integer or bounded string, never null/bool/float/object")
                request_id = supplied_id
            method = message.get("method")
            if not isinstance(method, str) or not method:
                raise RpcError(-32600, "method must be a non-empty string")
            notification = "id" not in message
            if set(message) - {"jsonrpc", "id", "method", "params"}:
                raise RpcError(-32600, "Unknown JSON-RPC request field")
            params = message.get("params", {})
            if not isinstance(params, dict):
                raise RpcError(-32602, "params must be an object")
            if notification:
                if method == "notifications/initialized" and self.initialized and not (set(params) - {"_meta"}):
                    self.ready = True
                # Never execute tools/call sent without an id. Unknown notifications are ignored.
                return None
            if method == "initialize":
                if self.initialized:
                    raise RpcError(-32600, "This connection is already initialized")
                if (not isinstance(params.get("protocolVersion"), str) or not isinstance(params.get("capabilities"), dict)
                        or not isinstance(params.get("clientInfo"), dict)
                        or not isinstance(params["clientInfo"].get("name"), str)
                        or not isinstance(params["clientInfo"].get("version"), str)):
                    raise RpcError(-32602, "initialize requires protocolVersion, capabilities, and clientInfo.name/version")
                requested = params["protocolVersion"]
                self.protocol_version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
                self.initialized = True
                result = {"protocolVersion": self.protocol_version, "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "godot-codex", "version": VERSION},
                          "instructions": "Select an explicit trusted project using --project or GODOT_PROJECT_PATH. Enable its Godot Codex EditorPlugin. Read godot_status/hierarchy before mutations; pass the exact scene revision and node identity guards. Never retry outcome_unknown automatically. Playing a scene executes project code and requires user approval."}
            elif method == "ping":
                if set(params) - {"_meta"}:
                    raise RpcError(-32602, "ping has no arguments")
                result = {}
            else:
                if not self.ready:
                    raise RpcError(-32002, "Complete initialize and notifications/initialized before calling tools")
                if method == "tools/list":
                    if set(params) - {"_meta"}:
                        raise RpcError(-32602, "All tools fit in one page; cursor and other arguments are unsupported")
                    result = {"tools": [{"name": "godot_" + name, **spec} for name, spec in OPERATIONS.items()]}
                elif method == "tools/call":
                    if set(params) - {"name", "arguments", "_meta"} or not isinstance(params.get("name"), str) or not isinstance(params.get("arguments", {}), dict):
                        raise RpcError(-32602, "tools/call expects name:string and arguments:object")
                    name = params["name"]
                    if not name.startswith("godot_") or name[6:] not in OPERATIONS:
                        raise RpcError(-32602, "Unknown tool: " + name[:128])
                    try:
                        value = self.client.call(name[6:], params.get("arguments", {}))
                        result = tool_result(value, structured=self.protocol_version != "2025-03-26")
                    except BridgeError as exc:
                        result = tool_result({"error": exc.as_dict()}, is_error=True, structured=self.protocol_version != "2025-03-26")
                    except OSError as exc:
                        result = tool_result({"error": {"code": "ipc_error", "message": str(exc)}}, is_error=True,
                                             structured=self.protocol_version != "2025-03-26")
                else:
                    raise RpcError(-32601, "Method not found")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except RpcError as exc:
            return None if notification else rpc_error(request_id, exc.code, exc.message)


def serve(server, source, sink):
    while True:
        # Bounded readline prevents unbounded allocations on malicious unterminated frames.
        frame = source.readline(MAX_FRAME_BYTES + 1)
        if not frame:
            return 0
        if len(frame) > MAX_FRAME_BYTES:
            emit(sink, rpc_error(None, -32700, "JSON-RPC frame exceeds the 2 MiB limit; connection closed"))
            return 2
        if not frame.endswith(b"\n"):
            emit(sink, rpc_error(None, -32700, "Each JSON-RPC message must end with a newline"))
            return 2
        try:
            message = _json_load(frame)
        except (ValueError, UnicodeError, RecursionError):
            emit(sink, rpc_error(None, -32700, "Invalid UTF-8 JSON frame"))
            continue
        try:
            response = server.handle(message)
        except Exception as exc:  # Keep protocol output valid even for an unexpected implementation failure.
            print(f"godot-mcp internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
            request_id = message.get("id") if isinstance(message, dict) and type(message.get("id")) in (str, int) else None
            response = rpc_error(request_id, -32603, "Internal server error") if not isinstance(message, dict) or "id" in message else None
        if response is not None:
            emit(sink, response)


def emit(sink, message):
    sink.write(json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n")
    sink.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Explicit Godot project directory, or use GODOT_PROJECT_PATH")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Bounded editor call timeout in seconds (0 < n <= 120)")
    args = parser.parse_args(argv)
    try:
        return serve(McpServer(args.project, args.timeout), sys.stdin.buffer, sys.stdout.buffer)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
