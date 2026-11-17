"""Command-line interface and stable report formats."""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

from . import __version__
from .scanner import scan
from .html_report import render_html
from .topology import path_label


def main(argv=None):
    parser = argparse.ArgumentParser(prog="netspector", description="Discover network connections from source and configuration.")
    parser.add_argument("--version", action="version", version=f"netspector {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("scan", help="Statically scan a project directory")
    command.add_argument("path", type=Path)
    command.add_argument("--format", choices=["table", "json", "csv", "html"], default="table")
    command.add_argument("--direction", choices=["inbound", "outbound", "unknown"])
    command.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    command.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    # Reports are UTF-8 even when redirected from a Windows legacy-codepage shell.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        excludes = list(args.exclude)
        if args.output:
            try:
                excludes.append(args.output.resolve().relative_to(args.path.resolve()).as_posix())
            except ValueError:
                pass
        report = scan(args.path, excludes)
        if args.direction:
            report["findings"] = [f for f in report["findings"] if f["direction"] == args.direction]
            report["connections"] = [c for c in report["connections"] if c["direction"] == args.direction]
        if args.format == "json":
            output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            output = render_html(report, project_name=args.path.resolve().name)
        elif args.format == "csv":
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=["direction", "kind", "target", "protocol", "port", "status", "file", "line", "reference", "evidence", "candidates", "record_type", "connection"])
            writer.writeheader()
            records = [dict(f, record_type="finding") for f in report["findings"]]
            records += [dict(record_type="connection", direction=c["direction"], kind="network-path", target=path_label(c), status=c["status"],
                             file=c["nodes"][0]["file"], reference=c["nodes"][0]["reference"], evidence=c["evidence"], connection=c)
                        for c in report["connections"]]
            for finding in records:
                finding = {k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (list, dict)) else v for k, v in finding.items()}
                # Keep untrusted source values from becoming spreadsheet formulas.
                writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for k, v in finding.items()})
            output = stream.getvalue()
        else:
            rows = [["DIRECTION", "KIND", "TARGET", "PORT", "STATUS", "SOURCE"]]
            rows += [[f["direction"], f["kind"], f["target"], str(f["port"] or "-"), f["status"], f"{f['file']}:{f['line'] or '-'}"] for f in report["findings"]]
            widths = [max(len(row[i]) for row in rows) for i in range(6)]
            output = "\n".join("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows) + "\n"
            for finding in report["findings"]:
                for candidate in finding["candidates"]:
                    output += f"  candidate for {finding['file']}:{finding['line']}: {candidate['target']} <- {candidate['file']} ({candidate['reference']})\n"
            if report["connections"]:
                output += "\nKubernetes network paths\n"
                for connection in report["connections"]:
                    reasons = ", ".join(connection["reasons"])
                    output += f"  [{connection['status']}] {connection['namespace']}: {path_label(connection)}"
                    output += f" ({reasons})\n" if reasons else "\n"
            output += f"\n{len(report['findings'])} finding(s), {len(report['connections'])} network path(s), {len(report['diagnostics'])} diagnostic(s)\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        for diagnostic in report["diagnostics"]:
            print(f"warning: {diagnostic['file']}: {diagnostic['message']}", file=sys.stderr)
        return 1 if report["diagnostics"] else 0
    except (ValueError, OSError) as exc:
        print(f"netspector: {exc}", file=sys.stderr)
        return 2
