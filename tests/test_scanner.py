import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from netspector.cli import main
from netspector.scanner import scan


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_python_routes_aliases_dynamic_and_secrets(self):
        self.write("app.py", '''import httpx as h
import os
from fastapi import FastAPI
app = FastAPI()
@app.get("/health")
def health():
    h.get("https://user:password@example.com:8443/path?token=secret#private")
    h.post(os.getenv("API_URL"))
# h.get("https://comment.example")
unused = "https://unused.example"
''')
        report = scan(self.root)
        self.assertEqual(len(report["findings"]), 3)
        targets = [f["target"] for f in report["findings"]]
        self.assertIn("https://example.com:8443/path", targets)
        self.assertIn("<dynamic>", targets)
        self.assertNotIn("password", json.dumps(report))
        self.assertEqual(report["findings"][-1]["reference"], "env:API_URL")

    def test_config_candidates_and_kubernetes(self):
        self.write("k.yaml", '''kind: Service
metadata: {name: api}
spec:
  ports: [{port: 80, targetPort: 8000}]
---
endpoint: https://example.com?q=secret
''')
        result = scan(self.root)["findings"]
        self.assertEqual(len(result), 2)
        service = next(f for f in result if f["kind"] == "service")
        self.assertEqual(service["status"], "declared")
        self.assertEqual(service["port"], 80)
        self.assertEqual(next(f for f in result if f["kind"] == "configuration")["direction"], "unknown")

    def test_partial_failure_excludes_and_repeatability(self):
        self.write("bad.py", "def broken(")
        self.write("good.json", '{"url":"https://example.com"}')
        self.write(".venv/ignored.py", 'import httpx; httpx.get("https://ignored.com")')
        first = scan(self.root)
        self.assertEqual(first, scan(self.root))
        self.assertEqual(len(first["findings"]), 1)
        self.assertEqual(len(first["diagnostics"]), 1)
        self.assertEqual(scan(self.root, ["bad.py"])["diagnostics"], [])

    def test_cli_formats_and_exit_codes(self):
        self.write("app.py", 'import requests; requests.get("https://example.com")')
        for format in ("json", "csv", "table"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["scan", str(self.root), "--format", format]), 0)
            self.assertIn("example.com", output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["scan", str(self.root / "missing")]), 2)
        self.write("bad.json", "{")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["scan", str(self.root)]), 1)

    def test_local_variable_is_not_resolved_from_module_constant(self):
        self.write("app.py", '''import requests
URL = "https://wrong.example"
def f(URL):
    requests.get(URL)
''')
        self.assertEqual(scan(self.root)["findings"][0]["status"], "unresolved")

    def test_malformed_manifest_does_not_abort_scan(self):
        self.write("bad.yaml", "kind: Service\nspec: [unexpected]\n")
        self.write("good.json", '{"url":"https://example.com"}')
        report = scan(self.root)
        self.assertEqual(len(report["diagnostics"]), 1)
        self.assertEqual(len(report["findings"]), 1)

    def test_output_is_not_scanned(self):
        out = self.root / "report.json"
        out.write_text('{"url":"https://stale.example"}')
        self.assertEqual(main(["scan", str(self.root), "--format", "json", "--output", str(out)]), 0)
        self.assertEqual(json.loads(out.read_text())["findings"], [])


if __name__ == "__main__":
    unittest.main()
