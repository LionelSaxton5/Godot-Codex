#!/usr/bin/env python3
"""Bounded project-local IPC client for the Godot Codex EditorPlugin.

No network listener, shell invocation, eval, authentication token or implicit project
selection. The enabled editor addon is the authority for all editor operations.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_STATUS_BYTES = 128 * 1024
MAX_SCRIPT_BYTES = 1024 * 1024
DEFAULT_TIMEOUT = 10.0
DEFAULT_STALE_SECONDS = 10.0
HEX_ID = re.compile(r"[0-9a-f]{32}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IPC = ".godot/ai_bridge"


class BridgeError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    def as_dict(self) -> dict:
        result = {"code": self.code, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result


def _object(properties=None, required=()):
    return {"type": "object", "properties": properties or {},
            "required": list(required), "additionalProperties": False}


def _string(description="", **constraints):
    return {"type": "string", "maxLength": 4096, **({"description": description} if description else {}), **constraints}


RESOURCE_PATH = _string("Project-local res:// path; no traversal, symlinks, generated files or absolute paths.", minLength=7)
NODE_PATH = _string("Root-relative node path, '.' for the scene root. No absolute paths or '..'.", minLength=1)
PROPERTY_NODE_PATH = _string("NodePath property relative to its target node. Empty clears it; parent segments are allowed only when addon resolution stays within the edited scene.")
NODE_ID = _string("Exact node_id from a fresh hierarchy or node_inspect result.", pattern="^[0-9]+$", maxLength=32, minLength=1)
NAME = _string(minLength=1, maxLength=128)
NUMBER = {"type": "number"}
INTEGER_COMPONENT = {"type": "integer", "minimum": -2147483648, "maximum": 2147483647}
TYPED_VALUE = {"anyOf": [
    {"type": "null"}, {"type": "boolean"}, NUMBER, _string(),
    _object({"type": {"const": "Vector2"}, "x": NUMBER, "y": NUMBER}, ("type", "x", "y")),
    _object({"type": {"const": "Vector3"}, "x": NUMBER, "y": NUMBER, "z": NUMBER}, ("type", "x", "y", "z")),
    _object({"type": {"const": "Vector2i"}, "x": INTEGER_COMPONENT, "y": INTEGER_COMPONENT}, ("type", "x", "y")),
    _object({"type": {"const": "Vector3i"}, "x": INTEGER_COMPONENT, "y": INTEGER_COMPONENT, "z": INTEGER_COMPONENT}, ("type", "x", "y", "z")),
    _object({"type": {"const": "Color"}, "r": NUMBER, "g": NUMBER, "b": NUMBER, "a": NUMBER}, ("type", "r", "g", "b", "a")),
    _object({"type": {"const": "NodePath"}, "value": PROPERTY_NODE_PATH}, ("type", "value")),
]}
SCENE_GUARD = {"expected_scene_path": _string("Exact scene.path from a fresh status; empty for no/unsaved scene."),
               "expected_revision": _string("Opaque scene.revision from a fresh status. Never synthesize this value.", minLength=1)}
NODE_GUARD = {"node_path": NODE_PATH, "expected_node_id": NODE_ID}


def _spec(description, properties=None, required=(), *, scene=False, node=False, read=False, destructive=False, open_world=False):
    props = {**(SCENE_GUARD if scene else {}), **(NODE_GUARD if node else {}), **(properties or {})}
    req = [*(SCENE_GUARD if scene else {}), *(NODE_GUARD if node else {}), *required]
    return {"description": description, "inputSchema": _object(props, req),
            "annotations": {"readOnlyHint": read, "destructiveHint": destructive,
                            "idempotentHint": read, "openWorldHint": open_world}}


OPERATIONS = {
    "status": _spec("Get the running editor session, fresh scene guard, engine version and supported operations.", read=True),
    "hierarchy": _spec("Inspect the edited scene tree with exact node identities. Read-only; never runs project code.",
                       {"node_path": NODE_PATH, "max_depth": {"type": "integer", "minimum": 0, "maximum": 32}}, read=True),
    "node_inspect": _spec("Inspect one node's native properties, identity and persistent signal connections.",
                          {"node_path": NODE_PATH}, ("node_path",), read=True),
    "scene_create": _spec("Create and open a new .tscn with a native root. Fails if the destination exists.",
                          {"path": RESOURCE_PATH, "root_type": NAME, "root_name": NAME}, ("path", "root_type", "root_name"), scene=True),
    "scene_open": _spec("Open an existing trusted project scene; current scene guards prevent acting on the wrong tab.",
                        {"path": RESOURCE_PATH}, ("path",), scene=True),
    "scene_save": _spec("Save the edited scene after checking scene identity, revision and exact expected disk SHA-256.",
                        {"expected_disk_sha256": _string("scene.disk_sha256 from a fresh status, or empty only for an absent destination.", pattern="^([0-9a-f]{64})?$", maxLength=64)},
                        ("expected_disk_sha256",), scene=True, destructive=True),
    "node_create": _spec("Create a native node under an identified parent, owned by the edited scene and undoable.",
                         {"parent_path": NODE_PATH, "expected_parent_id": NODE_ID, "type": NAME, "name": NAME},
                         ("parent_path", "expected_parent_id", "type", "name"), scene=True),
    "node_delete": _spec("Delete an identified non-root node through editor Undo/Redo.", scene=True, node=True, destructive=True),
    "node_duplicate": _spec("Duplicate an identified node with a new sibling name through editor Undo/Redo.",
                            {"name": NAME}, ("name",), scene=True, node=True),
    "node_reparent": _spec("Move an identified node under an identified new parent through editor Undo/Redo.",
                           {"new_parent_path": NODE_PATH, "expected_new_parent_id": NODE_ID, "keep_global_transform": {"type": "boolean"}},
                           ("new_parent_path", "expected_new_parent_id"), scene=True, node=True, destructive=True),
    "node_rename": _spec("Rename an identified node through editor Undo/Redo.", {"name": NAME}, ("name",), scene=True, node=True, destructive=True),
    "property_set": _spec("Set an allowlisted native editor property to a scalar or typed vector/color/NodePath. No custom setters.",
                          {"property": NAME, "value": TYPED_VALUE}, ("property", "value"), scene=True, node=True, destructive=True),
    "signal_connect": _spec("Add a persistent direct signal connection between identified nodes; target method must exist.",
                            {"signal": NAME, "target_path": NODE_PATH, "expected_target_id": NODE_ID, "method": NAME},
                            ("signal", "target_path", "expected_target_id", "method"), scene=True, node=True),
    "signal_disconnect": _spec("Remove an existing persistent direct signal connection through editor Undo/Redo.",
                               {"signal": NAME, "target_path": NODE_PATH, "expected_target_id": NODE_ID, "method": NAME},
                               ("signal", "target_path", "expected_target_id", "method"), scene=True, node=True, destructive=True),
    "script_attach": _spec("Attach an existing GDScript/C# script to an identified node. Tool scripts are rejected; C# needs a prior successful build.",
                           {"script_path": RESOURCE_PATH}, ("script_path",), scene=True, node=True, destructive=True),
    "script_read": _spec("Read bounded project-local .gd or .cs source as text without executing it; returns a SHA-256 for safe edits.",
                         {"path": RESOURCE_PATH}, ("path",), read=True),
    "script_write": _spec("Create/edit bounded .gd or .cs source. Existing files require overwrite=true and an exact expected_sha256. No @tool code, build or attachment.",
                          {"path": RESOURCE_PATH, "source": _string(maxLength=MAX_SCRIPT_BYTES), "overwrite": {"type": "boolean"},
                           "expected_sha256": _string(pattern="^[0-9a-f]{64}$", maxLength=64)}, ("path", "source"), destructive=True),
    "resource_create": _spec("Create a new allowlisted native .tres resource with typed properties. Never overwrites or loads custom resource scripts.",
                             {"path": RESOURCE_PATH, "type": NAME, "properties": {"type": "object", "additionalProperties": TYPED_VALUE, "maxProperties": 64}},
                             ("path", "type")),
    "resource_assign": _spec("Assign an existing safe native project resource to an identified node's native resource property.",
                             {"property": NAME, "resource_path": RESOURCE_PATH}, ("property", "resource_path"), scene=True, node=True, destructive=True),
    "editor_undo": _spec("Undo the latest edited-scene change after exact scene/revision validation.", scene=True, destructive=True),
    "editor_redo": _spec("Redo the latest edited-scene change after exact scene/revision validation.", scene=True, destructive=True),
    "play_current": _spec("Run the edited scene using the editor. Executes trusted project code; obtain user approval first.", scene=True, destructive=True, open_world=True),
    "play_main": _spec("Run the project's configured main scene. Executes trusted project code; obtain user approval first.", scene=True, destructive=True, open_world=True),
    "play_custom": _spec("Run an explicit project scene. Executes trusted project code; obtain user approval first.",
                         {"path": RESOURCE_PATH}, ("path",), scene=True, destructive=True, open_world=True),
    "stop": _spec("Stop the editor's running game; no external processes are killed."),
    "diagnostics": _spec("Get bounded addon operation/error diagnostics and editor state. This is not a complete debugger or C# build log.",
                         {"limit": {"type": "integer", "minimum": 1, "maximum": 200}}, read=True),
}
READ_ONLY = frozenset(name for name, spec in OPERATIONS.items() if spec["annotations"]["readOnlyHint"])


def validate_schema(value, schema: dict, where="arguments", depth=0):
    """Validate exactly the JSON Schema subset emitted above, without dependencies."""
    if depth > 32:
        raise BridgeError("invalid_arguments", f"{where}: nesting is too deep")
    if "anyOf" in schema:
        for variant in schema["anyOf"]:
            try:
                validate_schema(value, variant, where, depth + 1)
                return
            except BridgeError:
                pass
        raise BridgeError("invalid_arguments", f"{where}: unsupported typed value")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise BridgeError("invalid_arguments", f"{where}: expected {schema['const']!r}")
    expected = schema.get("type")
    valid = {"object": isinstance(value, dict), "string": isinstance(value, str), "integer": type(value) is int,
             "number": type(value) is int or (type(value) is float and math.isfinite(value)), "boolean": type(value) is bool,
             "null": value is None}
    if expected and not valid.get(expected, False):
        raise BridgeError("invalid_arguments", f"{where}: expected {expected}")
    if isinstance(value, dict):
        if len(value) > schema.get("maxProperties", 256):
            raise BridgeError("invalid_arguments", f"{where}: too many properties")
        props = schema.get("properties", {})
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise BridgeError("invalid_arguments", f"{where}: missing {', '.join(sorted(missing))}")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise BridgeError("invalid_arguments", f"{where}: invalid property name")
            if key in props:
                validate_schema(child, props[key], f"{where}.{key}", depth + 1)
            elif schema.get("additionalProperties") is False:
                raise BridgeError("invalid_arguments", f"{where}: unknown argument {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate_schema(child, schema["additionalProperties"], f"{where}.{key}", depth + 1)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 2**31):
            raise BridgeError("invalid_arguments", f"{where}: invalid string length")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise BridgeError("invalid_arguments", f"{where}: invalid string format")
        if "\x00" in value:
            raise BridgeError("invalid_arguments", f"{where}: NUL is not allowed")
    if type(value) in (int, float):
        if (type(value) is float and not math.isfinite(value)) or value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise BridgeError("invalid_arguments", f"{where}: number out of range")


def _json_load(data: bytes):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    result = json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))
    def check_strings(value):
        if type(value) is float and not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        if isinstance(value, str):
            value.encode("utf-8")
        elif isinstance(value, dict):
            for key, child in value.items():
                check_strings(key)
                check_strings(child)
        elif isinstance(value, list):
            for child in value:
                check_strings(child)
    check_strings(result)
    return result


def _reject_link(path: Path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise BridgeError("unsafe_path", f"Symlinks and junctions are not allowed: {path}")


def _normal_final_path(path: Path):
    """Normalize Win32 extended prefixes returned during atomic file replacement."""
    value = str(path)
    if os.name == "nt":
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\") and re.match(r"^[A-Za-z]:[\\/]", value[4:]):
            value = value[4:]
    return Path(value)


class ProjectFiles:
    """Confined file access. POSIX uses directory descriptors and O_NOFOLLOW."""
    def __init__(self, project: str | Path | None):
        if not project or not str(project).strip():
            raise BridgeError("project_required", "Set --project or GODOT_PROJECT_PATH to an explicit Godot project directory")
        path = Path(project).expanduser().absolute()
        # Canonicalize platform ancestors (e.g. macOS /var), but never the project itself.
        _reject_link(path)
        path = _normal_final_path(path.parent.resolve()) / path.name
        if not path.is_dir():
            raise BridgeError("invalid_project", f"Project directory does not exist: {path}")
        self.root = path
        self.secure_dir_fd = os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")
        try:
            self.read("project.godot", MAX_STATUS_BYTES)
        except FileNotFoundError as exc:
            raise BridgeError("invalid_project", "Project directory must contain a regular project.godot") from exc

    @staticmethod
    def parts(relative: str):
        parts = relative.split("/")
        if not relative or any(p in ("", ".", "..") for p in parts) or any(c in relative for c in "\\:\x00"):
            raise BridgeError("unsafe_path", "Expected a confined relative path")
        if any(ord(c) < 32 for c in relative):
            raise BridgeError("unsafe_path", "Control characters are not allowed in paths")
        # Windows aliases (ADS, reserved devices, trailing-dot/space normalization).
        for part in parts:
            if part.endswith((".", " ")) or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part):
                raise BridgeError("unsafe_path", "Platform-ambiguous path component")
        return parts

    def checked_path(self, relative: str, *, allow_missing=True):
        parts = self.parts(relative)
        _reject_link(self.root)
        current = self.root
        for part in parts:
            current /= part
            _reject_link(current)
            if current.exists() and current != self.root / relative and not current.is_dir():
                raise BridgeError("unsafe_path", "A path parent is not a directory")
        if not allow_missing and not current.exists():
            raise FileNotFoundError(current)
        resolved = _normal_final_path(current.resolve())
        # NTFS may resolve a just-replaced open status handle into $Deleted.
        # Never read that internal path; retry the named status within read's bound.
        if (os.name == "nt" and relative == f"{IPC}/status.json" and len(resolved.parts) >= 4
                and tuple(part.lower() for part in resolved.parts[1:3]) == ("$extend", "$deleted")):
            raise FileNotFoundError("Editor status was replaced during path resolution")
        if not resolved.is_relative_to(self.root):
            raise BridgeError("unsafe_path", "Path escapes the configured project", {"path": str(current), "resolved": str(resolved), "root": str(self.root)})
        return current

    @contextmanager
    def parent(self, relative: str):
        parts = self.parts(relative)
        if not self.secure_dir_fd:
            target = self.checked_path(relative)
            yield None, target
            return
        opened = []
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            fd = os.open(self.root, flags)
            opened.append(fd)
            for part in parts[:-1]:
                fd = os.open(part, flags, dir_fd=fd)
                opened.append(fd)
            yield fd, parts[-1]
        except OSError as exc:
            if exc.errno in (20, 40):
                raise BridgeError("unsafe_path", "Symlink or invalid IPC directory rejected") from exc
            raise
        finally:
            for fd in reversed(opened):
                os.close(fd)

    def read(self, relative: str, limit: int):
        # Windows atomic replacement briefly makes a status file inaccessible.
        # Retry only safe reads, never publish or repeat an editor mutation.
        deadline = time.monotonic() + 0.25
        while True:
            try:
                return self._read_once(relative, limit)
            except OSError as exc:
                transient = (getattr(exc, "winerror", None) in (5, 32, 33) or exc.errno == 13
                             or (isinstance(exc, FileNotFoundError) and relative == f"{IPC}/status.json"))
                if os.name != "nt" or not transient or time.monotonic() >= deadline:
                    raise
                time.sleep(0.005)

    def _read_once(self, relative: str, limit: int):
        with self.parent(relative) as (directory, name):
            self.checked_path(relative, allow_missing=False)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            try:
                fd = os.open(name, flags, **({"dir_fd": directory} if directory is not None else {}))
            except OSError as exc:
                if exc.errno in (40,):
                    raise BridgeError("unsafe_path", "Symlink file rejected") from exc
                raise
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise BridgeError("unsafe_path", "Only regular files may be read")
                if os.fstat(stream.fileno()).st_size > limit:
                    raise BridgeError("payload_too_large", f"File exceeds {limit} byte limit")
                data = stream.read(limit + 1)
                if len(data) > limit:
                    raise BridgeError("payload_too_large", f"File exceeds {limit} byte limit")
                return data

    def atomic_request(self, relative: str, data: bytes):
        if len(data) > MAX_REQUEST_BYTES:
            raise BridgeError("payload_too_large", "IPC request exceeds the byte limit")
        temp = relative + "." + uuid.uuid4().hex + ".tmp"
        with self.parent(relative) as (directory, name):
            temp_name = Path(temp).name if directory is not None else self.checked_path(temp)
            kwargs = {"dir_fd": directory} if directory is not None else {}
            self.checked_path(relative)
            if self.checked_path(relative).exists():
                raise BridgeError("id_collision", "Request ID already exists; request was not sent")
            try:
                fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, **kwargs)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.checked_path(relative)
                if directory is not None:
                    os.link(temp_name, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                else:
                    os.rename(temp_name, name)
            finally:
                try:
                    os.unlink(temp_name, **kwargs)
                except FileNotFoundError:
                    pass

    def remove_own(self, relative: str):
        """Unlink only this call's exact IPC filename; never recurse or purge queues."""
        try:
            with self.parent(relative) as (directory, name):
                # unlink does not follow a symlink, but refuse it rather than alter another actor's entry.
                self.checked_path(relative)
                os.unlink(name, **({"dir_fd": directory} if directory is not None else {}))
        except (FileNotFoundError, BridgeError, OSError):
            pass

    def resource(self, value: str, *, allow_missing=True):
        if not isinstance(value, str) or not value.startswith("res://"):
            raise BridgeError("unsafe_path", "Resource paths must start with res://")
        relative = value[6:]
        parts = self.parts(relative)
        if parts[0].lower() in {".godot", ".git", ".mono", ".codex", ".agents", "project.godot"} or (len(parts) > 1 and parts[0].lower() == "addons" and parts[1].lower() in {"godot_ai_bridge", "ai_editor_bridge"}):
            raise BridgeError("unsafe_path", "Generated/internal bridge files are not resource targets")
        return self.checked_path(relative, allow_missing=allow_missing)


def validate_node_path(value: str):
    if value == ".":
        return
    if value.startswith("/") or ":" in value or "\\" in value or any(p in ("", ".", "..") for p in value.split("/")) or any(ord(c) < 32 for c in value):
        raise BridgeError("unsafe_node_path", "Node paths must be relative to the current edited scene and cannot traverse parents")


def validate_property_node_path(value: str):
    """Only syntax here; the addon resolves relative to the target inside its scene."""
    if value == "":
        return
    if value.startswith("/") or ":" in value or "\\" in value or any(p == "" for p in value.split("/")) or any(ord(c) < 32 for c in value):
        raise BridgeError("unsafe_node_path", "NodePath properties must be relative to their target node, without absolute paths, subnames or control characters")


class EditorBridgeClient:
    def __init__(self, project=None, *, timeout=DEFAULT_TIMEOUT, stale_seconds=DEFAULT_STALE_SECONDS,
                 max_response_bytes=MAX_RESPONSE_BYTES):
        self.files = ProjectFiles(project if project is not None else os.environ.get("GODOT_PROJECT_PATH"))
        if not math.isfinite(timeout) or not 0 < timeout <= 120 or not math.isfinite(stale_seconds) or not 0 < stale_seconds <= 120:
            raise BridgeError("invalid_configuration", "Timeout/staleness bounds must be greater than zero and at most 120 seconds")
        self.timeout, self.stale_seconds, self.max_response_bytes = timeout, stale_seconds, max_response_bytes

    @property
    def project_root(self):
        return str(self.files.root)

    def status(self):
        try:
            value = _json_load(self.files.read(f"{IPC}/status.json", MAX_STATUS_BYTES))
        except FileNotFoundError as exc:
            raise BridgeError("editor_unavailable", "Enable the Godot Codex EditorPlugin in this project and keep its editor open") from exc
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise BridgeError("invalid_status", "Editor status is not valid bounded JSON") from exc
        if not isinstance(value, dict) or type(value.get("protocol_version")) is not int or value["protocol_version"] != PROTOCOL_VERSION:
            raise BridgeError("protocol_mismatch", "Editor bridge protocol_version must be 1")
        if not isinstance(value.get("session_id"), str) or not HEX_ID.fullmatch(value["session_id"]):
            raise BridgeError("invalid_status", "Editor status has an invalid session_id")
        root = value.get("project_root")
        if not isinstance(root, str) or os.path.normcase(os.path.normpath(root)) != os.path.normcase(os.path.normpath(self.project_root)):
            raise BridgeError("project_mismatch", "Editor status belongs to a different project")
        heartbeat = value.get("heartbeat_unix")
        if type(heartbeat) not in (int, float) or not math.isfinite(heartbeat):
            raise BridgeError("invalid_status", "Editor status has no valid heartbeat_unix")
        age = time.time() - heartbeat
        if age > self.stale_seconds or age < -5:
            raise BridgeError("editor_stale", "Editor heartbeat is stale; wait for the editor or reopen it", {"age_seconds": round(age, 3)})
        scene = value.get("scene")
        if not isinstance(scene, dict) or not isinstance(scene.get("path"), str) or not isinstance(scene.get("revision"), str) or not scene["revision"]:
            raise BridgeError("invalid_status", "Editor status lacks an opaque scene revision/path")
        if not isinstance(value.get("capabilities"), list) or not all(isinstance(c, str) for c in value["capabilities"]):
            raise BridgeError("invalid_status", "Editor status capabilities must be a list of operation names")
        return value

    def validate_arguments(self, operation, arguments):
        if operation not in OPERATIONS:
            raise BridgeError("unknown_operation", f"Unsupported editor operation: {operation}")
        validate_schema(arguments, OPERATIONS[operation]["inputSchema"])
        for key, value in arguments.items():
            if key in {"node_path", "parent_path", "new_parent_path", "target_path"}:
                validate_node_path(value)
            elif key in {"path", "script_path", "resource_path", "expected_scene_path"} and value:
                self.files.resource(value)
        def typed_paths(value):
            if isinstance(value, dict):
                if value.get("type") == "NodePath":
                    validate_property_node_path(value["value"])
                for child in value.values():
                    typed_paths(child)
        typed_paths(arguments)
        path = arguments.get("path", arguments.get("script_path", ""))
        suffix = Path(path).suffix.lower()
        if operation in {"script_read", "script_write", "script_attach"} and suffix not in {".gd", ".cs"}:
            raise BridgeError("invalid_arguments", "Script paths must end in .gd or .cs")
        if operation == "scene_create" and suffix != ".tscn":
            raise BridgeError("invalid_arguments", "New scene paths must end in .tscn")
        if operation in {"scene_open", "play_custom"} and suffix != ".tscn":
            raise BridgeError("invalid_arguments", "Only text .tscn scenes are supported")
        if operation == "resource_create" and suffix != ".tres":
            raise BridgeError("invalid_arguments", "New resource paths must end in .tres")
        if operation == "resource_assign" and Path(arguments["resource_path"]).suffix.lower() not in {".tres", ".png", ".jpg", ".jpeg", ".webp"}:
            raise BridgeError("invalid_arguments", "Resource assignment supports native .tres and .png/.jpg/.jpeg/.webp textures only")
        if operation == "script_write":
            if len(arguments["source"].encode("utf-8")) > MAX_SCRIPT_BYTES:
                raise BridgeError("payload_too_large", "Script source exceeds 1 MiB UTF-8")
            if arguments.get("overwrite", False) != ("expected_sha256" in arguments):
                raise BridgeError("invalid_arguments", "overwrite=true requires expected_sha256; expected_sha256 requires overwrite=true")

    def call(self, operation: str, arguments: dict | None = None):
        arguments = {} if arguments is None else arguments
        self.validate_arguments(operation, arguments)
        status = self.status()
        if operation not in status["capabilities"]:
            raise BridgeError("unsupported_operation", f"The running addon does not support {operation}")
        request_id = uuid.uuid4().hex
        if not HEX_ID.fullmatch(request_id):
            raise BridgeError("invalid_id", "Generated IPC request ID is invalid")
        request = {"id": request_id, "session_id": status["session_id"], "project_root": status["project_root"],
                   "operation": operation, "arguments": arguments}
        request_path, response_path = f"{IPC}/requests/{request_id}.json", f"{IPC}/responses/{request_id}.json"
        data = json.dumps(request, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        published = False
        owns_files = False
        try:
            if self.files.checked_path(response_path).exists():
                raise BridgeError("id_collision", "Response ID already exists; request was not sent")
            self.files.atomic_request(request_path, data)
            published = True
            owns_files = True
            deadline, next_status = time.monotonic() + self.timeout, 0.0
            while True:
                now = time.monotonic()
                if now >= next_status:
                    if self.status()["session_id"] != status["session_id"]:
                        raise BridgeError("stale_session", "Editor session changed during this request")
                    next_status = now + min(0.25, self.stale_seconds / 2)
                try:
                    response = _json_load(self.files.read(response_path, self.max_response_bytes))
                except FileNotFoundError:
                    response = None
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise BridgeError("invalid_response", "Editor returned invalid JSON") from exc
                if response is not None:
                    if self.status()["session_id"] != status["session_id"]:
                        raise BridgeError("stale_session", "Editor session changed before its response was accepted")
                    if not isinstance(response, dict) or response.get("id") != request_id or response.get("session_id") != status["session_id"] or type(response.get("ok")) is not bool:
                        raise BridgeError("invalid_response", "Editor response ID/session/envelope does not match the request")
                    if not response["ok"]:
                        error = response.get("error")
                        if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
                            raise BridgeError("invalid_response", "Editor error response lacks code/message")
                        # A valid editor error definitively reports the operation outcome.
                        published = False
                        raise BridgeError(error["code"], error["message"], error.get("details") if isinstance(error.get("details"), dict) else {})
                    if "result" not in response:
                        raise BridgeError("invalid_response", "Editor success response lacks result")
                    return response["result"]
                if now >= deadline:
                    raise BridgeError("timeout", "Editor did not reply before the bounded timeout")
                time.sleep(min(0.025, max(0, deadline - now)))
        except (OSError, BridgeError) as exc:
            error = exc if isinstance(exc, BridgeError) else BridgeError("ipc_error", str(exc))
            if published and operation not in READ_ONLY:
                raise BridgeError("outcome_unknown", "The request was published but no trustworthy response arrived. It may have applied. Inspect fresh editor state before deciding what to do; never retry the mutation automatically.",
                                  {"request_id": request_id, "operation": operation, "cause": error.as_dict()}) from exc
            raise error
        finally:
            if owns_files:
                self.files.remove_own(request_path)
                self.files.remove_own(response_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Explicit project directory; or set GODOT_PROJECT_PATH")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--arguments", default="{}", help="JSON operation arguments, including explicit guards for mutations")
    args = parser.parse_args(argv)
    try:
        arguments = _json_load(args.arguments.encode("utf-8"))
        result = EditorBridgeClient(args.project, timeout=args.timeout).call(args.operation, arguments)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, UnicodeError, BridgeError, OSError) as exc:
        error = exc if isinstance(exc, BridgeError) else BridgeError("invalid_input", str(exc))
        print(json.dumps({"ok": False, "error": error.as_dict()}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
