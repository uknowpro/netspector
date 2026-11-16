"""Package a native build with documentation, examples, and license notices."""
import argparse
import importlib.metadata
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from netspector import __version__

parser = argparse.ArgumentParser()
parser.add_argument('target', choices=['linux-x86_64', 'macos-x86_64', 'macos-arm64', 'windows-x86_64'])
args = parser.parse_args()
expected = {'linux': 'Linux', 'macos': 'Darwin', 'windows': 'Windows'}[args.target.split('-')[0]]
assert platform.system() == expected, 'Build on the target operating system'
assert platform.machine().lower() in ({'arm64', 'aarch64'} if args.target.endswith('arm64') else {'amd64', 'x86_64'})
name = f'netspector-{__version__}-{args.target}'
staging = Path('build') / name
staging.mkdir(parents=True, exist_ok=True)
exe = 'netspector.exe' if expected == 'Windows' else 'netspector'
shutil.copy2(Path('dist') / exe, staging / exe)
for file in ('LICENSE', 'README.md', 'README.ko.md'):
    shutil.copy2(file, staging / file)
shutil.copytree('examples', staging / 'examples', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
licenses = staging / 'licenses'
licenses.mkdir(exist_ok=True)
for package in ('PyYAML', 'pyinstaller'):
    distribution = importlib.metadata.distribution(package)
    for file in distribution.files or []:
        if any(word in file.name.lower() for word in ('license', 'copying')) and distribution.locate_file(file).is_file():
            destination = licenses / package / str(file).replace('/', '_').replace('\\', '_')
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(distribution.locate_file(file), destination)
version = platform.python_version()
url = f'https://raw.githubusercontent.com/python/cpython/v{version}/LICENSE'
with urllib.request.urlopen(url, timeout=60) as response:
    (licenses / 'Python-LICENSE.txt').write_bytes(response.read())
(staging / 'BUILD-INFO.txt').write_text(
    f'netspector {__version__}\nTarget: {args.target}\nPython: {version}\n'
    f'PyInstaller: {importlib.metadata.version("pyinstaller")}\n'
    f'PyYAML: {importlib.metadata.version("PyYAML")}\n'
    'License notices: licenses/\n', encoding='utf-8')
output = Path('release-assets')
output.mkdir(exist_ok=True)
if expected == 'Windows':
    archive = output / f'{name}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(staging.rglob('*')):
            if path.is_file():
                bundle.write(path, Path(name) / path.relative_to(staging))
else:
    archive = output / f'{name}.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        bundle.add(staging, arcname=name)
print(archive)
