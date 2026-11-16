"""Conservative static analysis. Target code is never imported or executed."""
from __future__ import annotations

import ast
import fnmatch
import json
import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

import yaml

URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def safe_target(value: str) -> str:
    """Remove URL credentials, query values and fragments from report evidence."""
    if not URL.match(value):
        return "<dynamic>" if value != "<dynamic>" and not value.startswith("/") else value
    try:
        parts = urlsplit(value)
        host = parts.hostname or "<unresolved>"
        if ":" in host:
            host = f"[{host}]"
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{host}{port}{parts.path}"
    except ValueError:
        return "<invalid-url>"


def scan(root: Path, excludes: list[str] | None = None) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    findings, diagnostics = [], []

    def emit(file, line, direction, kind, target, status="confirmed", protocol=None, port=None, reference=None):
        target = safe_target(str(target)) if URL.match(str(target)) else str(target)
        if URL.match(target):
            parsed = urlsplit(target)
            protocol = parsed.scheme
            port = parsed.port or {"http": 80, "https": 443}.get(protocol)
        findings.append(dict(direction=direction, kind=kind, target=target, protocol=protocol,
                             port=port, status=status, file=file, line=line, reference=reference))

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if any(p in SKIP for p in path.relative_to(root).parts) or path.is_symlink():
            continue
        if any(fnmatch.fnmatch(rel, p) or Path(rel).match(p) for p in excludes or []):
            continue
        if not path.is_file() or path.suffix not in {".py", ".json", ".yaml", ".yml", ".toml"} and not path.name.startswith(".env"):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                diagnostics.append(dict(file=rel, message="Skipped file larger than 2 MB"))
                continue
            source = path.read_text(encoding="utf-8")
            if path.suffix == ".py":
                python_scan(source, rel, emit)
            elif path.suffix in {".yaml", ".yml"}:
                for doc in yaml.safe_load_all(source):
                    config_scan(doc, rel, emit)
                    if isinstance(doc, dict):
                        kubernetes_scan(doc, rel, emit)
            elif path.suffix == ".json":
                config_scan(json.loads(source), rel, emit)
            elif path.suffix == ".toml":
                config_scan(tomllib.loads(source), rel, emit)
            else:
                for lineno, line in enumerate(source.splitlines(), 1):
                    match = re.match(r"\s*(?:export\s+)?([\w]+)\s*=\s*(.*?)\s*$", line)
                    if match:
                        key, value = match.groups()
                        value = value.strip("\"'")
                        if URL.match(value):
                            emit(rel, lineno, "unknown", "configuration", value, "candidate", reference=key)
        except (OSError, UnicodeError, SyntaxError, ValueError, TypeError, AttributeError, yaml.YAMLError, RecursionError) as exc:
            # Parser messages can contain source secrets: only expose the error type.
            diagnostics.append(dict(file=rel, message=type(exc).__name__))
    unique = {json.dumps(f, sort_keys=True): f for f in findings}
    return dict(schema_version="1", findings=sorted(unique.values(), key=lambda f: (f["file"], f["line"] or 0, f["kind"], f["target"])), diagnostics=diagnostics)


def config_scan(value, file, emit, key=""):
    if isinstance(value, dict):
        for k, v in value.items():
            config_scan(v, file, emit, f"{key}.{k}".strip("."))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            config_scan(v, file, emit, f"{key}[{i}]")
    elif isinstance(value, str) and URL.match(value):
        emit(file, None, "unknown", "configuration", value, "candidate", reference=key)


def kubernetes_scan(doc, file, emit):
    kind, spec = doc.get("kind"), doc.get("spec") or {}
    name = (doc.get("metadata") or {}).get("name", "<unnamed>")
    if kind == "List":
        for item in doc.get("items", []):
            if isinstance(item, dict):
                kubernetes_scan(item, file, emit)
    elif kind == "Service":
        for p in spec.get("ports", []):
            emit(file, None, "inbound", "service", name, "declared", p.get("protocol", "TCP").lower(), p.get("port"), f"targetPort={p.get('targetPort', p.get('port'))}")
    elif kind in {"Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
        if kind == "CronJob":
            spec = spec.get("jobTemplate", {}).get("spec", {})
        pod = spec if kind == "Pod" else spec.get("template", {}).get("spec", {})
        for container in pod.get("containers", []):
            for p in container.get("ports", []):
                emit(file, None, "inbound", "container-port", f"{name}/{container.get('name', '<unnamed>')}", "declared", p.get("protocol", "TCP").lower(), p.get("containerPort"))
    elif kind == "Ingress":
        for rule in spec.get("rules", []):
            for entry in rule.get("http", {}).get("paths", []):
                emit(file, None, "inbound", "ingress", f"{rule.get('host', '*')}{entry.get('path', '/')}", "declared", "http")


def python_scan(source, file, emit):
    tree = ast.parse(source)
    imports, constants, apps, clients = {}, {}, set(), set()
    # Module-level bindings only; no unsafe propagation across functions/scopes.
    def dotted(node):
        if isinstance(node, ast.Name):
            return imports.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{dotted(node.value)}.{node.attr}"
        return ""

    def value(node, allow_constants=True):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, None
        if allow_constants and isinstance(node, ast.Name) and node.id in constants:
            return constants[node.id], node.id
        if isinstance(node, ast.Call) and dotted(node.func) in {"os.getenv", "os.environ.get"} and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return "<dynamic>", f"env:{arg.value}"
        if isinstance(node, ast.Subscript) and dotted(node.value) == "os.environ" and isinstance(node.slice, ast.Constant):
            return "<dynamic>", f"env:{node.slice.value}"
        return "<dynamic>", None

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    literal, _ = value(node.value)
                    if literal != "<dynamic>":
                        constants[target.id] = literal
                    if isinstance(node.value, ast.Call):
                        constructor = dotted(node.value.func)
                        if constructor in {"fastapi.FastAPI", "fastapi.APIRouter"}:
                            apps.add(target.id)
                        if constructor in {"requests.Session", "httpx.Client", "httpx.AsyncClient"}:
                            clients.add(target.id)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func)
        owner, _, method = name.rpartition(".")
        arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg in {"url", "path"}), None)
        if method in METHODS and owner in {"requests", "httpx"} | clients:
            target, ref = value(arg, False)
            emit(file, node.lineno, "outbound", "http-client", safe_target(target), "unresolved" if target == "<dynamic>" else "confirmed", reference=ref)
        elif method in METHODS | {"websocket", "api_route"} and owner in apps:
            target, ref = value(arg, False)
            emit(file, node.lineno, "inbound", "route", target, "unresolved" if target == "<dynamic>" else "declared", "websocket" if method == "websocket" else "http", reference=ref)
