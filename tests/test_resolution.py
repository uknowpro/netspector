import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from netspector.cli import main
from netspector.scanner import scan


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def calls(self):
        return [f for f in scan(self.root)['findings'] if f['kind'] == 'http-client']

    def test_constant_chain_and_local_assignment_provenance(self):
        self.write('app.py', '''import httpx
BASE = "https://example.com/path?secret=x"
URL = BASE
def run():
    local = URL
    httpx.get(local)
''')
        call, = self.calls()
        self.assertEqual(call['target'], 'https://example.com/path')
        self.assertEqual(call['status'], 'inferred')
        self.assertEqual([e['line'] for e in call['evidence']], [2, 3, 5])
        self.assertNotIn('secret', json.dumps(call))

    def test_env_alias_and_dotenv_candidates_are_not_confirmed(self):
        self.write('app.py', '''import httpx
from os import getenv as env
URL = env("API_URL")
def run():
    httpx.get(URL)
''')
        self.write('.env.dev', 'API_URL="https://user:password@dev.example/v1?token=hidden" # comment\n')
        self.write('.env.prod', 'API_URL=https://prod.example/v1\n')
        call, = self.calls()
        self.assertEqual(call['status'], 'candidate')
        self.assertEqual(call['target'], '<dynamic>')
        self.assertEqual(call['reference'], 'env:API_URL')
        self.assertEqual([c['target'] for c in call['candidates']], ['https://dev.example/v1', 'https://prod.example/v1'])
        self.assertEqual(call['candidates'][0]['line'], 1)
        self.assertNotIn('password', json.dumps(scan(self.root)))
        self.assertNotIn('hidden', json.dumps(scan(self.root)))

    def test_scope_reassignment_control_flow_and_import_shadowing(self):
        self.write('app.py', '''import httpx
URL = "https://global.example"
def argument(URL):
    httpx.get(URL)
def reassigned():
    URL = "https://first.example"
    URL = unknown()
    httpx.get(URL)
def conditional(flag):
    if flag:
        URL = "https://conditional.example"
    httpx.get(URL)
def shadow(httpx):
    httpx.get("https://not-httpx.example")
''')
        calls = self.calls()
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(c['status'] == 'unresolved' for c in calls))

    def test_configmap_namespace_reference_and_unreferenced_maps(self):
        self.write('app.py', 'import httpx\nimport os\nhttpx.get(os.environ["API_URL"])\n')
        self.write('maps.yaml', '''kind: ConfigMap
metadata: {name: endpoints, namespace: prod}
data: {URL: 'https://prod.example'}
---
kind: ConfigMap
metadata: {name: endpoints, namespace: dev}
data: {URL: 'https://wrong.example'}
---
kind: ConfigMap
metadata: {name: unused, namespace: prod}
data: {API_URL: 'https://unused.example'}
''')
        self.write('workload.yaml', '''kind: Deployment
metadata: {name: api, namespace: prod}
spec:
  template:
    spec:
      containers:
        - name: app
          env:
            - name: API_URL
              valueFrom:
                configMapKeyRef: {name: endpoints, key: URL}
''')
        call, = self.calls()
        self.assertEqual(len(call['candidates']), 1)
        candidate = call['candidates'][0]
        self.assertEqual(candidate['target'], 'https://prod.example')
        self.assertEqual(candidate['file'], 'maps.yaml')
        self.assertEqual(candidate['via'], 'workload.yaml')
        self.assertEqual(candidate['namespace'], 'prod')

    def test_envfrom_prefix_and_explicit_override(self):
        self.write('app.py', 'import httpx\nimport os\nhttpx.get(os.getenv("APP_URL"))\n')
        self.write('k.yaml', '''kind: ConfigMap
metadata: {name: urls}
data: {URL: 'https://inherited.example'}
---
kind: Pod
metadata: {name: api}
spec:
  containers:
    - name: app
      envFrom:
        - prefix: APP_
          configMapRef: {name: urls}
      env:
        - name: APP_URL
          value: https://explicit.example
''')
        call, = self.calls()
        self.assertEqual([c['target'] for c in call['candidates']], ['https://explicit.example'])

    def test_missing_secret_and_template_stay_unresolved(self):
        self.write('app.py', 'import httpx\nimport os\nhttpx.get(os.getenv("API_URL"))\n')
        self.write('.env', 'API_URL=https://${HOST}/api\n')
        self.write('k.yaml', '''kind: Pod
spec:
  containers:
    - name: app
      env:
        - name: API_URL
          valueFrom:
            secretKeyRef: {name: secret, key: url}
''')
        call, = self.calls()
        self.assertEqual(call['status'], 'unresolved')
        self.assertEqual(call['candidates'], [])

    def test_exclusion_and_export_provenance(self):
        self.write('app.py', 'import httpx\nimport os\nhttpx.get(os.getenv("API_URL"))\n')
        self.write('.env', 'API_URL=https://example.com\n')
        report = scan(self.root, ['.env'])
        self.assertEqual(report['findings'][0]['status'], 'unresolved')
        for fmt in ('json', 'csv', 'table'):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['scan', str(self.root), '--direction', 'outbound', '--format', fmt]), 0)
            self.assertIn('https://example.com', output.getvalue())
            self.assertIn('.env', output.getvalue())
            if fmt == 'csv':
                row = next(csv.DictReader(io.StringIO(output.getvalue())))
                self.assertEqual(json.loads(row['candidates'])[0]['file'], '.env')
        self.assertEqual(scan(self.root), scan(self.root))

    def test_global_mutation_does_not_propagate(self):
        self.write('app.py', '''import httpx
URL = "https://old.example"
def mutate():
    global URL
    URL = "https://new.example"
def run():
    httpx.get(URL)
''')
        self.assertEqual(self.calls()[0]['status'], 'unresolved')

    def test_same_line_order_does_not_resolve_future_import(self):
        self.write('app.py', 'httpx.get("https://wrong.example"); import httpx\nhttpx.get("https://right.example")\n')
        self.assertEqual([f['target'] for f in self.calls()], ['https://right.example'])

    def test_invalid_configmap_does_not_block_other_candidates(self):
        self.write('app.py', 'import httpx\nimport os\nhttpx.get(os.getenv("URL"))\n')
        self.write('k.yaml', '''kind: ConfigMap
metadata: {name: broken}
data: [not-a-map]
---
kind: Pod
spec:
  containers:
    - name: good
      env:
        - {name: URL, value: 'https://good.example'}
''')
        report = scan(self.root)
        self.assertEqual(len(report['diagnostics']), 1)
        call = next(f for f in report['findings'] if f['kind'] == 'http-client')
        self.assertEqual(call['candidates'][0]['target'], 'https://good.example')

    def test_pattern_capture_does_not_use_global_constant(self):
        self.write('app.py', '''import httpx
URL = "https://wrong.example"
def run(data):
    match data:
        case {"url": URL}:
            httpx.get(URL)
''')
        self.assertEqual(self.calls()[0]['status'], 'unresolved')

    def test_envfrom_prefix_without_override(self):
        self.write('app.py', 'import httpx\nimport os\nhttpx.get(os.getenv("APP_URL"))\n')
        self.write('k.yaml', '''kind: List
items:
  - kind: ConfigMap
    metadata: {name: urls}
    data: {URL: 'https://prefixed.example'}
  - kind: Pod
    spec:
      containers:
        - name: app
          envFrom:
            - prefix: APP_
              configMapRef: {name: urls}
''')
        self.assertEqual(self.calls()[0]['candidates'][0]['target'], 'https://prefixed.example')
