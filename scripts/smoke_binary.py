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

archive = Path(sys.argv[1]).resolve()
expected_version = sys.argv[2]
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
    environment = {k: v for k, v in os.environ.items() if k not in {'PYTHONPATH', 'PYTHONHOME'}}
    environment['PYTHONIOENCODING'] = 'utf-8'

    def run(*args, code=0):
        result = subprocess.run([str(binary), *map(str, args)], cwd=root, env=environment, capture_output=True, encoding='utf-8', timeout=60)
        assert result.returncode == code, (result.returncode, result.stderr)
        return result.stdout

    assert run('--version').strip() == f'netspector {expected_version}'
    report = json.loads(run('scan', package / 'examples' / 'demo', '--format', 'json'))
    assert len(report['findings']) == 7 and not report['diagnostics'], report
    candidate = next(f for f in report['findings'] if f['reference'] == 'env:NOTIFY_URL')
    assert candidate['candidates'][0]['target'] == 'https://notify.example.com/events'
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
