"""A presentation graph: aggregate hosts and edges, retain every source record."""
from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import PurePosixPath
from urllib.parse import urlsplit

MARKERS = {'pyproject.toml', 'setup.py', 'setup.cfg', 'package.json', 'pom.xml',
           'build.gradle', 'build.gradle.kts', 'go.mod', 'Cargo.toml', 'composer.json'}


def project_metadata(root, files):
    boundaries = {'.'}
    for file in files:
        path = PurePosixPath(file)
        if path.name in MARKERS or path.suffix == '.csproj':
            boundaries.add(str(path.parent))
    return dict(roots=sorted(boundaries))


def host_identity(target):
    """No DNS lookups or alias guessing; ports and paths are edge attributes."""
    if not isinstance(target, str) or target.startswith(('/', '<', '*')):
        return None
    try:
        parsed = urlsplit(target if '://' in target else '//' + target)
        host = parsed.hostname
        if not host or any(c in host for c in '<>{}$* '):
            return None
        # Validate ports even though identity deliberately excludes them.
        parsed.port
        try:
            host = ipaddress.ip_address(host).compressed
        except ValueError:
            host = host.rstrip('.').encode('idna').decode('ascii').lower()
        return host or None
    except (ValueError, UnicodeError):
        return None


def build_graph(report):
    metadata = report.get('project', {})
    roots = metadata.get('roots', ['.'])
    title = metadata.get('name', 'Project')
    nodes, edges = {}, {}

    def project(file):
        parent = PurePosixPath(file or '').parent
        matches = [r for r in roots if r == '.' or PurePosixPath(r) == parent or PurePosixPath(r) in parent.parents]
        return max(matches, key=lambda r: len(PurePosixPath(r).parts)) if matches else '.'

    def unique(items):
        return list({json.dumps(item, sort_keys=True, ensure_ascii=False): item for item in items}.values())

    def node(key, label, kind, group, record=None):
        ident = 'n-' + hashlib.sha256(key.encode()).hexdigest()[:16]
        value = nodes.setdefault(ident, dict(id=ident, label=label, kind=kind, projects=[], records=[]))
        if group not in value['projects']:
            value['projects'].append(group)
        if record is not None:
            value['records'].append(record)
        return ident

    def app(group, record=None):
        return node('app:' + group, title if group == '.' else group, 'Application', group, record)

    def host(target, group, record):
        name = host_identity(target)
        return node('host:' + name, name, 'Host', group, record) if name else None

    def connect(source, target, group, record, relation='directed', candidate=False):
        if not source or not target:
            return
        key = (source, target, relation)
        value = edges.setdefault(key, dict(id='e-' + hashlib.sha256('|'.join(key).encode()).hexdigest()[:16],
                                           source=source, target=target, relation=relation, projects=[], records=[], uncertain=True))
        value['records'].append(record)
        value['uncertain'] = value['uncertain'] and candidate
        scopes = {group}
        for ident in (source, target):
            if nodes[ident]['kind'] != 'Host':
                scopes.update(nodes[ident]['projects'])
        value['projects'] = sorted(set(value['projects']) | scopes)

    for finding in report['findings']:
        group = project(finding['file'])
        kind, direction = finding['kind'], finding['direction']
        # Infrastructure gets its own declared topology below. Never invent an app association.
        if kind in {'service', 'container-port', 'ingress'}:
            continue
        application = app(group, finding)
        if direction == 'inbound':
            # A route path is not a remote caller. Keep local routes on the app node.
            if '://' in finding['target']:
                connect(host(finding['target'], group, finding), application, group, finding)
            continue
        targets = [(finding['target'], finding, finding['status'] in {'candidate', 'unresolved'})]
        targets.extend((candidate['target'], dict(finding=finding, candidate=candidate), True)
                       for candidate in finding.get('candidates', []) if candidate.get('target'))
        for target, record, candidate in targets:
            endpoint = host(target, group, record)
            if endpoint:
                connect(application, endpoint, group, record, 'association' if direction == 'unknown' else 'directed', candidate or direction == 'unknown')
            elif direction == 'outbound' and not finding.get('candidates'):
                dynamic = node('unresolved:' + group, 'Unresolved targets', 'Unresolved', group, finding)
                connect(application, dynamic, group, finding, candidate=True)

    covered = set()
    for connection in report.get('connections', []):
        chain = connection.get('nodes', [])
        previous, workload = None, None
        for item in chain:
            group = project(item.get('file', ''))
            namespace = item.get('namespace', connection.get('namespace', 'default'))
            kind, name = item['kind'], item['name']
            # Containers with the same name in different workloads are distinct.
            if kind not in {'Ingress', 'Service', 'Container', 'ExternalName'}:
                workload = f'{kind}/{name}'
            if kind == 'ExternalName':
                current = host(name, group, connection)
            else:
                key = f'k8s:{group}:{namespace}:{kind}:{workload if kind == "Container" else ""}:{name}'
                current = node(key, name, kind, group, connection)
                nodes[current]['namespace'] = namespace
            covered.add((item.get('file'), kind, name))
            if kind == 'Container' and workload:
                covered.add((item.get('file'), 'container-port', workload.split('/', 1)[1] + '/' + name))
            if kind == 'Ingress' and item.get('host'):
                connect(host(item['host'], group, connection), current, group, connection,
                        candidate=connection['status'] in {'candidate', 'unresolved', 'partial'})
            if previous:
                connect(previous, current, group, connection, candidate=connection['status'] in {'candidate', 'unresolved', 'partial'})
            previous = current

    # Preserve declarations that have no topology path, without claiming ownership.
    for finding in report['findings']:
        if finding['kind'] not in {'service', 'container-port', 'ingress'}:
            continue
        group = project(finding['file'])
        if finding['kind'] == 'ingress':
            host(finding['target'].split('/')[0], group, finding)
        elif not any(file == finding['file'] and name == finding['target'] for file, _, name in covered):
            node('declaration:' + group + ':' + finding['kind'] + ':' + finding['target'],
                 finding['target'], 'Port declaration', group, finding)

    # URL declarations supporting a known direction do not draw a second parallel line.
    for key, edge in list(edges.items()):
        directed = edges.get((edge['source'], edge['target'], 'directed'))
        if edge['relation'] == 'association' and directed is not None:
            directed['records'].extend(edge['records'])
            directed['projects'] = sorted(set(directed['projects'] + edge['projects']))
            del edges[key]
    for value in [*nodes.values(), *edges.values()]:
        value['records'] = unique(value['records'])
        value['projects'].sort()
    return dict(title=title, projects=sorted({p for n in nodes.values() for p in n['projects']}),
                nodes=sorted(nodes.values(), key=lambda n: (n['kind'] != 'Application', n['kind'] == 'Host', n['label'], n['id'])),
                edges=sorted(edges.values(), key=lambda e: e['id']))
