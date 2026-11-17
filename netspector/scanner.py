"""Conservative static analysis. Target code is never imported or executed."""
from __future__ import annotations

import fnmatch
import json
import re
import shlex
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from .python_analyzer import analyze
from .java_analyzer import analyze_java
from .java_properties import properties
from .resolution import Environment
from .topology import Topology

URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "target", ".gradle"}


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
    environment = Environment(safe_target)
    topology = Topology()

    def emit(file, line, direction, kind, target, status="confirmed", protocol=None, port=None, reference=None, evidence=None):
        target = safe_target(str(target)) if URL.match(str(target)) else str(target)
        if URL.match(target):
            parsed = urlsplit(target)
            protocol = parsed.scheme
            port = parsed.port or {"http": 80, "https": 443}.get(protocol)
        findings.append(dict(direction=direction, kind=kind, target=target, protocol=protocol,
                             port=port, status=status, file=file, line=line, reference=reference, evidence=evidence or [], candidates=[]))

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if any(p in SKIP for p in path.relative_to(root).parts) or path.is_symlink():
            continue
        if any(fnmatch.fnmatch(rel, p) or Path(rel).match(p) for p in excludes or []):
            continue
        if not path.is_file() or path.suffix not in {".py", ".java", ".properties", ".json", ".yaml", ".yml", ".toml"} and not path.name.startswith(".env"):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                diagnostics.append(dict(file=rel, message="Skipped file larger than 2 MB"))
                continue
            source = path.read_text(encoding="utf-8")
            if path.suffix == ".py":
                analyze(source, rel, emit, safe_target)
            elif path.suffix == ".java":
                analyze_java(source, rel, emit, safe_target)
            elif path.suffix == ".properties":
                for key, value, line in properties(source):
                    environment.add('property:' + key, value, rel, line, reference=key)
                    if URL.match(value):
                        emit(rel, line, "unknown", "configuration", value, "candidate", reference=key)
            elif path.suffix in {".yaml", ".yml"}:
                for document_index, doc in enumerate(yaml.safe_load_all(source)):
                    config_scan(doc, rel, emit, environment=environment if path.name.startswith(("application", "bootstrap")) else None)
                    if isinstance(doc, dict):
                        topology.document(doc, rel, f"documents[{document_index}]")
                        kubernetes_scan(doc, rel, emit)
                        environment.document(doc, rel)
            elif path.suffix == ".json":
                doc = json.loads(source)
                config_scan(doc, rel, emit, environment=environment if path.name.startswith(("application", "bootstrap")) else None)
                if isinstance(doc, dict):
                    topology.document(doc, rel, "document")
                    kubernetes_scan(doc, rel, emit)
                    environment.document(doc, rel)
            elif path.suffix == ".toml":
                config_scan(tomllib.loads(source), rel, emit)
            else:
                for lineno, line in enumerate(source.splitlines(), 1):
                    match = re.match(r"\s*(?:export\s+)?([\w]+)\s*=\s*(.*?)\s*$", line)
                    if match:
                        key, value = match.groups()
                        parts = shlex.split(value, comments=True, posix=True)
                        value = parts[0] if len(parts) == 1 else ""
                        environment.add(key, value, rel, lineno)
                        if URL.match(value):
                            emit(rel, lineno, "unknown", "configuration", value, "candidate", reference=key)
        except (OSError, UnicodeError, SyntaxError, ValueError, TypeError, AttributeError, yaml.YAMLError, RecursionError) as exc:
            # Parser messages can contain source secrets: only expose the error type.
            diagnostics.append(dict(file=rel, message=type(exc).__name__))
    diagnostics.extend(environment.build())
    environment.resolve(findings)
    connections, topology_diagnostics = topology.build()
    diagnostics.extend(topology_diagnostics)
    unique = {json.dumps(f, sort_keys=True): f for f in findings}
    return dict(schema_version="1", findings=sorted(unique.values(), key=lambda f: (f["file"], f["line"] or 0, f["kind"], f["target"])), diagnostics=diagnostics, connections=connections)


def config_scan(value, file, emit, key="", environment=None):
    if isinstance(value, dict):
        for k, v in value.items():
            config_scan(v, file, emit, f"{key}.{k}".strip("."), environment)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            config_scan(v, file, emit, f"{key}[{i}]", environment)
    elif isinstance(value, str) and URL.match(value):
        if environment is not None:
            environment.add('property:' + key, value, file, reference=key)
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
    elif kind in {"Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}:
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
