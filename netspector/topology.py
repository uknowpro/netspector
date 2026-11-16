"""Manifest-only network paths; never imply live reachability or pod readiness."""
from collections import Counter
import hashlib
import json

WORKLOADS = {'Pod', 'Deployment', 'StatefulSet', 'DaemonSet', 'ReplicaSet', 'Job', 'CronJob'}


def pod_template(doc):
    spec = doc.get('spec') or {}
    if doc['kind'] == 'Pod':
        return doc.get('metadata') or {}, spec, ''
    prefix = 'spec.'
    if doc['kind'] == 'CronJob':
        spec = spec.get('jobTemplate', {}).get('spec', {})
        prefix += 'jobTemplate.spec.'
    template = spec.get('template') or {}
    return template.get('metadata') or {}, template.get('spec') or {}, prefix + 'template.'


class Topology:
    def __init__(self):
        self.resources = []
        self.diagnostics = []

    def document(self, doc, file, reference):
        if not isinstance(doc, dict):
            return
        if doc.get('kind') == 'List':
            for index, item in enumerate(doc.get('items') or []):
                self.document(item, file, f'{reference}.items[{index}]')
        elif doc.get('kind') in WORKLOADS | {'Service', 'Ingress'}:
            metadata = doc.get('metadata') or {}
            if not isinstance(metadata, dict) or not isinstance(metadata.get('name'), str):
                return
            if not isinstance(metadata.get('namespace') or 'default', str):
                self.diagnostics.append(dict(file=file, message='Invalid topology namespace'))
                return
            self.resources.append(dict(doc=doc, file=file, reference=reference,
                                       namespace=metadata.get('namespace') or 'default', name=metadata['name'], kind=doc['kind']))

    @staticmethod
    def node(resource, reference=None, **extra):
        return {k: resource[k] for k in ('kind', 'name', 'namespace', 'file')} | dict(reference=reference or resource['reference'], **extra)

    @staticmethod
    def evidence(resource, suffix):
        return dict(file=resource['file'], line=None, reference=resource['reference'] + suffix)

    @staticmethod
    def connection(nodes, status='declared', reasons=None, evidence=None):
        return dict(direction='inbound', status=status, reasons=reasons or [], nodes=nodes,
                    evidence=evidence or [], namespace=nodes[0]['namespace'])

    def service_paths(self, service, port, index, workloads):
        spec = service['doc'].get('spec') or {}
        protocol = port.get('protocol', 'TCP').upper()
        target = port.get('targetPort', port.get('port'))
        node = self.node(service, f"{service['reference']}.spec.ports[{index}]", port=port.get('port'), target_port=target, protocol=protocol)
        evidence = [self.evidence(service, f'.spec.ports[{index}]'), self.evidence(service, '.spec.selector')]
        if spec.get('type') == 'ExternalName':
            external = spec.get('externalName')
            if not external:
                return [self.connection([node], 'unresolved', ['external-name-missing'], evidence)]
            endpoint = dict(kind='ExternalName', name=external, namespace=service['namespace'], file=service['file'], reference=service['reference'] + '.spec.externalName')
            return [self.connection([node, endpoint], reasons=['external-dns-not-resolved'], evidence=[evidence[0], self.evidence(service, '.spec.externalName')])]
        selector = spec.get('selector')
        if not selector:
            return [self.connection([node], 'unresolved', ['selectorless-service'], evidence)]
        if not isinstance(selector, dict):
            raise ValueError('Invalid selector')
        matches = [(workload, metadata, pod, prefix) for workload, metadata, pod, prefix in workloads
                   if workload['namespace'] == service['namespace'] and all((metadata.get('labels') or {}).get(k) == v for k, v in selector.items())]
        if not matches:
            return [self.connection([node], 'unresolved', ['no-matching-workload'], evidence)]
        paths = []
        for workload, metadata, pod, prefix in matches:
            worknode = self.node(workload)
            proof = evidence + [self.evidence(workload, '.' + prefix + 'metadata.labels' if prefix else '.metadata.labels')]
            containers = []
            for ci, container in enumerate(pod.get('containers') or []):
                for pi, declared in enumerate(container.get('ports') or []):
                    match = (type(target) is int and declared.get('containerPort') == target or
                             isinstance(target, str) and declared.get('name') == target)
                    if match and declared.get('protocol', 'TCP').upper() == protocol:
                        ref = f"{workload['reference']}.{prefix}spec.containers[{ci}].ports[{pi}]"
                        containers.append(dict(kind='Container', name=container.get('name', '<unnamed>'), namespace=workload['namespace'],
                                               file=workload['file'], reference=ref, port=declared.get('containerPort'), protocol=protocol))
            if not containers:
                numeric = type(target) is int and 1 <= target <= 65535
                paths.append(self.connection([node, worknode], 'partial' if numeric else 'unresolved',
                                             ['container-port-not-declared' if numeric else 'named-target-port-not-found'], proof))
            else:
                for container in containers:
                    paths.append(self.connection([node, worknode, container], 'candidate' if len(containers) > 1 else 'declared',
                                                 ['multiple-container-port-matches'] if len(containers) > 1 else [],
                                                 proof + [dict(file=container['file'], line=None, reference=container['reference'])]))
        return paths

    def build(self):
        workloads, services, ingresses = [], [], []
        for resource in self.resources:
            try:
                if resource['kind'] in WORKLOADS:
                    metadata, pod, prefix = pod_template(resource['doc'])
                    # Validate structures before they can affect other resources.
                    if not isinstance(metadata, dict) or not isinstance(metadata.get('labels') or {}, dict) or not isinstance(pod, dict):
                        raise ValueError()
                    for container in pod.get('containers') or []:
                        if not isinstance(container, dict):
                            raise ValueError()
                        for port in container.get('ports') or []:
                            if not isinstance(port, dict):
                                raise ValueError()
                    workloads.append((resource, metadata, pod, prefix))
                elif resource['kind'] == 'Service':
                    services.append(resource)
                else:
                    ingresses.append(resource)
            except (AttributeError, TypeError, ValueError):
                self.diagnostics.append(dict(file=resource['file'], message='Invalid workload for topology'))
        connections, service_index = [], []
        for service in services:
            try:
                ports = (service['doc'].get('spec') or {}).get('ports') or []
                if not ports:
                    connections.append(self.connection([self.node(service)], 'unresolved', ['service-ports-not-declared']))
                for index, port in enumerate(ports):
                    paths = self.service_paths(service, port, index, workloads)
                    connections.extend(paths)
                    service_index.append((service, port, paths))
            except (AttributeError, TypeError, ValueError):
                self.diagnostics.append(dict(file=service['file'], message='Invalid Service for topology'))
        for ingress in ingresses:
            try:
                spec = ingress['doc'].get('spec') or {}
                backends = []
                if spec.get('defaultBackend'):
                    backends.append(('*', '*', None, spec['defaultBackend'], '.spec.defaultBackend'))
                for ri, rule in enumerate(spec.get('rules') or []):
                    for pi, path in enumerate((rule.get('http') or {}).get('paths') or []):
                        backends.append((rule.get('host', '*'), path.get('path', '/'), path.get('pathType'), path.get('backend') or {},
                                         f'.spec.rules[{ri}].http.paths[{pi}].backend'))
                for host, path, path_type, backend, suffix in backends:
                    origin = self.node(ingress, ingress['reference'] + suffix, host=host, path=path, path_type=path_type)
                    proof = [self.evidence(ingress, suffix)]
                    service_ref = backend.get('service')
                    if not isinstance(service_ref, dict):
                        connections.append(self.connection([origin], 'unresolved', ['unsupported-ingress-backend'], proof))
                        continue
                    name = service_ref.get('name')
                    port_ref = service_ref.get('port') or {}
                    matches = [(service, paths) for service, port, paths in service_index
                               if service['namespace'] == ingress['namespace'] and service['name'] == name
                               and port.get('protocol', 'TCP').upper() == 'TCP'
                               and ((type(port_ref.get('number')) is int and port_ref['number'] == port.get('port'))
                                    or (isinstance(port_ref.get('name'), str) and port_ref['name'] == port.get('name')))]
                    if not matches:
                        exists = any(s['namespace'] == ingress['namespace'] and s['name'] == name for s in services)
                        missing = dict(kind='Service', name=name or '<missing>', namespace=ingress['namespace'], file=None, reference=None,
                                       port=port_ref.get('number', port_ref.get('name')))
                        connections.append(self.connection([origin, missing], 'unresolved',
                                                           ['service-port-not-found' if exists else 'service-not-found'], proof))
                    for service, paths in matches:
                        for downstream in paths:
                            connections.append(self.connection([origin] + downstream['nodes'], downstream['status'],
                                                               list(downstream['reasons']), proof + downstream['evidence']))
            except (AttributeError, TypeError, ValueError):
                self.diagnostics.append(dict(file=ingress['file'], message='Invalid Ingress for topology'))
        identities = Counter((r['kind'], r['namespace'], r['name']) for r in self.resources)
        for connection in connections:
            if any(identities[(n['kind'], n['namespace'], n['name'])] > 1 for n in connection['nodes'] if n['file'] is not None):
                connection['reasons'].append('duplicate-resource-declarations')
                if connection['status'] == 'declared':
                    connection['status'] = 'candidate'
            encoded = json.dumps(connection, sort_keys=True)
            connection['id'] = hashlib.sha256(encoded.encode()).hexdigest()[:16]
        return sorted(connections, key=lambda c: (c['namespace'], json.dumps(c['nodes'], sort_keys=True), c['id'])), self.diagnostics


def path_label(connection):
    def label(node):
        text = f"{node['kind']}/{node['name']}"
        if node.get('host') is not None:
            text += f" ({node['host']}{node.get('path', '')})"
        if node.get('port') is not None:
            text += f":{node['port']}"
        return text
    return ' → '.join(label(node) for node in connection['nodes'])
