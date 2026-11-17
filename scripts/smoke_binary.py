"""Exercise the shipped archive away from the checkout and installed package."""
import csv
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from release_support import validate_windows_executable

archive = Path(sys.argv[1]).resolve()
expected_version = sys.argv[2]
target = sys.argv[3]
with tempfile.TemporaryDirectory(prefix='netspector-release-') as temporary:
    root = Path(temporary)
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(root)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(root, filter='data')
    package, = root.iterdir()
    binary = package / ('netspector.exe' if os.name == 'nt' else 'netspector')
    if target.startswith('windows-'):
        print(validate_windows_executable(binary, target))
    environment = {k: v for k, v in os.environ.items() if k not in {'PYTHONPATH', 'PYTHONHOME'}}
    environment['PYTHONIOENCODING'] = 'utf-8'

    def run(*args, code=0):
        result = subprocess.run([str(binary), *map(str, args)], cwd=root, env=environment, capture_output=True, encoding='utf-8', timeout=60)
        assert result.returncode == code, (result.returncode, result.stderr)
        return result.stdout

    assert run('--version').strip() == f'netspector {expected_version}'
    report = json.loads(run('scan', package / 'examples' / 'demo', '--format', 'json'))
    assert len(report['findings']) == 8 and not report['diagnostics'], report
    assert any([n['kind'] for n in c['nodes']] == ['Ingress', 'Service', 'Deployment', 'Container'] for c in report['connections'])
    assert '<!doctype html>' in run('scan', package / 'examples' / 'demo', '--format', 'html')
    candidate = next(f for f in report['findings'] if f['reference'] == 'env:NOTIFY_URL')
    assert candidate['candidates'][0]['target'] == 'https://notify.example.com/events'
    java = json.loads(run('scan', package / 'examples' / 'java', '--format', 'json'))
    assert not java['diagnostics']
    assert {f['target'] for f in java['findings'] if f['direction'] == 'inbound'} == {'/api/health', '/api/notify'}
    assert any(f['kind'] == 'http-request' and f['target'] == 'https://audit.example.com/events' for f in java['findings'])
    assert any(f['reference'] == 'property:notify.url' and f['candidates'] for f in java['findings'])
    assert 'WeatherController.java' in run('scan', package / 'examples' / 'java', '--format', 'html')
    config = json.loads(run('scan', package / 'examples' / 'config', '--format', 'json'))
    assert not config['diagnostics'], config
    config_targets = {f['target'] for f in config['findings']}
    assert {'https://api.example.com:443/v1', 'db.example.com:5432',
            'https://audit.example.com:8443/events', '/api/*'} <= config_targets
    assert 'services.ini' in run('scan', package / 'examples' / 'config', '--format', 'html')
    project = root / '한글 project'
    project.mkdir()
    (project / 'app.py').write_text('import httpx\nhttpx.get("https://example.com")\n', encoding='utf-8')
    output = root / '결과.json'
    run('scan', project, '--format', 'json', '--output', output)
    assert json.loads(output.read_text(encoding='utf-8'))['findings'][0]['target'] == 'https://example.com'
    rows = list(csv.DictReader(io.StringIO(run('scan', project, '--format', 'csv'))))
    assert rows[0]['target'] == 'https://example.com'
    assert 'confirmed' in run('scan', project)
    (project / 'broken.json').write_text('{', encoding='utf-8')
    assert json.loads(run('scan', project, '--format', 'json', code=1))['diagnostics']
    run('scan', root / 'missing', code=2)
print('Standalone archive smoke tests passed')
