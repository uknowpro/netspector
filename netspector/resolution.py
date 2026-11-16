"""Collect environment declarations without assuming deployment/app association."""
from collections import defaultdict


class Environment:
    def __init__(self, safe_target):
        self.values = defaultdict(list)
        self.docs = []
        self.safe_target = safe_target

    def add(self, name, value, file, line=None, reference=None, **context):
        if not isinstance(name, str) or not isinstance(value, str):
            return
        target = self.safe_target(value)
        # Expansion is not evaluated; do not turn templates into concrete URLs.
        if target in {'<dynamic>', '<invalid-url>'} or any(token in value for token in ('${', '$(', '{{')):
            return
        if '://' not in target:
            return
        self.values[name].append(dict(target=target, file=file, line=line, reference=reference or name, **context))

    def document(self, doc, file):
        if not isinstance(doc, dict):
            return
        if doc.get('kind') == 'List':
            for item in doc.get('items', []):
                self.document(item, file)
        else:
            self.docs.append((doc, file))

    def build(self):
        maps = defaultdict(list)
        diagnostics = []
        for doc, file in self.docs:
            try:
                meta = doc.get('metadata') or {}
                if doc.get('kind') == 'ConfigMap':
                    data = doc.get('data') or {}
                    if not isinstance(data, dict):
                        raise ValueError()
                    maps[(meta.get('namespace', 'default'), meta.get('name'))].append((data, file))
            except (TypeError, AttributeError, ValueError):
                diagnostics.append(dict(file=file, message='Invalid ConfigMap declaration'))
        for doc, file in self.docs:
            try:
                self.workload(doc, file, maps)
            except (TypeError, AttributeError, ValueError):
                diagnostics.append(dict(file=file, message='Invalid environment declaration'))
        return diagnostics

    def workload(self, doc, file, maps):
        kind = doc.get('kind')
        if kind not in {'Pod', 'Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob'}:
            return
        meta, spec = doc.get('metadata') or {}, doc.get('spec') or {}
        namespace = meta.get('namespace', 'default')
        if kind == 'CronJob':
            spec = spec.get('jobTemplate', {}).get('spec', {})
        pod = spec if kind == 'Pod' else spec.get('template', {}).get('spec', {})
        for container in pod.get('containers', []):
            context = dict(namespace=namespace, workload=f"{kind}/{meta.get('name', '<unnamed>')}", container=container.get('name'))
            explicit = {e.get('name') for e in container.get('env', [])}
            for env in container.get('env', []):
                name = env.get('name')
                if 'value' in env:
                    self.add(name, env['value'], file, reference=f'env:{name}', **context)
                else:
                    ref = env.get('valueFrom', {}).get('configMapKeyRef', {})
                    for data, origin in maps.get((namespace, ref.get('name')), []):
                        self.add(name, data.get(ref.get('key')), origin, reference=f"ConfigMap/{ref.get('name')}.data.{ref.get('key')}", via=file, **context)
            for entry in container.get('envFrom', []):
                ref = entry.get('configMapRef', {})
                for data, origin in maps.get((namespace, ref.get('name')), []):
                    for key, val in data.items():
                        name = entry.get('prefix', '') + key
                        if name not in explicit:
                            self.add(name, val, origin, reference=f"ConfigMap/{ref.get('name')}.data.{key}", via=file, **context)

    def resolve(self, findings):
        for finding in findings:
            ref = finding.get('reference') or ''
            if finding['kind'] != 'http-client' or not ref.startswith('env:'):
                continue
            candidates = self.values.get(ref[4:], [])
            # Repo-wide declarations are hypotheses, even when only one matches.
            if candidates:
                finding['status'] = 'candidate'
                finding['candidates'] = sorted(candidates, key=lambda c: (c['target'], c['file'], c.get('reference') or '', str(c)))
