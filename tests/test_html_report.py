import base64
import contextlib
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
import tempfile
import unittest
from pathlib import Path

from netspector.cli import main
from netspector.html_report import render_html, SCRIPT
from netspector.scanner import scan


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class HtmlReportTests(unittest.TestCase):
    def test_untrusted_source_data_is_text_and_script_is_hash_restricted(self):
        payload = '</script><img src="https://bad.example" onerror="alert(1)">'
        report = {'findings': [dict(direction='outbound', kind='http-client', target=payload, port=None, status='candidate',
                                   file=payload, line=1, reference=payload, evidence=[], candidates=[{'target': payload}])],
                  'connections': [dict(namespace=payload, status='unresolved', reasons=[payload], evidence=[{'file': payload}],
                                       nodes=[dict(kind='Ingress', name=payload, host=payload, path=payload)])],
                  'diagnostics': [dict(file=payload, message=payload)]}
        output = render_html(report)
        self.assertNotIn(payload, output)
        parser = Elements()
        parser.feed(output)
        self.assertEqual(sum(tag == 'script' for tag, _ in parser.elements), 1)
        self.assertFalse(any(tag in {'img', 'iframe', 'link'} for tag, _ in parser.elements))
        self.assertFalse(any(any(key.startswith('on') for key in attrs) for _, attrs in parser.elements))
        digest = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
        self.assertIn('sha256-' + digest, output)
        self.assertIn('&lt;img', output)

    def test_empty_report_and_diagnostics(self):
        report = {'findings': [], 'connections': [], 'diagnostics': [{'file': 'bad.yaml', 'message': 'ParserError'}]}
        output = render_html(report)
        self.assertIn('No matching network paths.', output)
        self.assertIn('No matching findings.', output)
        self.assertIn('bad.yaml', output)
        self.assertIn('ParserError', output)
        self.assertEqual(output, render_html(report))

    def test_all_output_formats_include_topology_and_filter_direction(self):
        root = Path(__file__).resolve().parents[1] / 'examples' / 'demo'
        for format in ('table', 'json', 'csv', 'html'):
            with self.subTest(format=format):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['scan', str(root), '--format', format]), 0)
                self.assertIn('weather', output.getvalue())
                if format == 'csv':
                    rows = list(csv.DictReader(io.StringIO(output.getvalue())))
                    connection = next(r for r in rows if r['record_type'] == 'connection')
                    self.assertEqual(json.loads(connection['connection'])['direction'], 'inbound')
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['scan', str(root), '--format', format, '--direction', 'outbound']), 0)
                if format == 'json':
                    self.assertEqual(json.loads(output.getvalue())['connections'], [])
                if format == 'csv':
                    self.assertTrue(all(r['record_type'] == 'finding' for r in csv.DictReader(io.StringIO(output.getvalue()))))

    def test_html_file_handles_unicode_and_partial_scan_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'app.py').write_text('import httpx\nhttpx.get("https://user:password@example.com/path?token=secret")\n', encoding='utf-8')
            (root / 'bad.json').write_text('{')
            target = root / '보고서.html'
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['scan', str(root), '--format', 'html', '--output', str(target)]), 1)
            html = target.read_text(encoding='utf-8')
            self.assertIn('https://example.com/path', html)
            self.assertNotIn('password', html)
            self.assertNotIn('token=secret', html)
            self.assertIn('bad.json', html)

    def test_redirected_html_is_utf8_even_under_legacy_encoding(self):
        import os
        import subprocess
        import sys
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-m', 'netspector', 'scan', str(repo / 'examples' / 'demo'), '--format', 'html'],
                                cwd=repo, env=dict(os.environ, PYTHONIOENCODING='ascii'), capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Ingress → Service', result.stdout.decode('utf-8'))
