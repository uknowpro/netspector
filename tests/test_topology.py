import copy
import json
import tempfile
import unittest
from pathlib import Path

from netspector.scanner import scan
from netspector.topology import Topology


def workload(name='api', namespace='default', port=8000, protocol='TCP'):
    return {'kind': 'Deployment', 'metadata': {'name': name, 'namespace': namespace, 'labels': {'wrong': 'label'}},
            'spec': {'template': {'metadata': {'labels': {'app': 'api', 'tier': 'web'}},
                                  'spec': {'containers': [{'name': 'server', 'ports': [{'name': 'http', 'containerPort': port, 'protocol': protocol}]}]}}}}


def service(name='api', namespace='default', target='http'):
    return {'kind': 'Service', 'metadata': {'name': name, 'namespace': namespace},
            'spec': {'selector': {'app': 'api', 'tier': 'web'}, 'ports': [{'name': 'web', 'port': 80, 'targetPort': target}]}}


def ingress(namespace='default', backend=None):
    return {'kind': 'Ingress', 'metadata': {'name': 'edge', 'namespace': namespace},
            'spec': {'rules': [{'host': 'api.example.com', 'http': {'paths': [
                {'path': '/v1', 'pathType': 'Prefix', 'backend': backend or {'service': {'name': 'api', 'port': {'name': 'web'}}}}]}}]}}


def build(*docs):
    topology = Topology()
    for i, doc in enumerate(docs):
        topology.document(doc, f'{i}.yaml', 'documents[0]')
    return topology.build()


class TopologyTests(unittest.TestCase):
    def test_named_ports_and_full_ingress_chain(self):
        paths, diagnostics = build(ingress(), service(), workload())
        self.assertEqual(diagnostics, [])
        chain = next(p for p in paths if p['nodes'][0]['kind'] == 'Ingress')
        self.assertEqual([n['kind'] for n in chain['nodes']], ['Ingress', 'Service', 'Deployment', 'Container'])
        self.assertEqual([n.get('port') for n in chain['nodes']], [None, 80, None, 8000])
        self.assertEqual(chain['status'], 'declared')
        self.assertEqual(chain['nodes'][0]['path_type'], 'Prefix')
        self.assertTrue(any(e['reference'].endswith('spec.template.metadata.labels') for e in chain['evidence']))
        self.assertEqual(paths, build(ingress(), service(), workload())[0])

    def test_namespace_and_all_selector_labels_are_required(self):
        paths, _ = build(service(namespace='prod'), workload(namespace='dev'))
        self.assertEqual(paths[0]['reasons'], ['no-matching-workload'])
        doc = workload(namespace='prod')
        doc['spec']['template']['metadata']['labels']['tier'] = 'worker'
        paths, _ = build(service(namespace='prod'), doc)
        self.assertEqual(paths[0]['reasons'], ['no-matching-workload'])

    def test_numeric_default_and_protocol_matching(self):
        svc = service()
        svc['spec']['ports'] = [{'port': 8000}]
        paths, _ = build(svc, workload())
        self.assertEqual(paths[0]['status'], 'declared')
        paths, _ = build(svc, workload(protocol='UDP'))
        self.assertEqual(paths[0]['status'], 'partial')
        self.assertEqual(paths[0]['reasons'], ['container-port-not-declared'])

    def test_numeric_target_without_declaration_and_missing_named_port(self):
        doc = workload()
        doc['spec']['template']['spec']['containers'][0]['ports'] = []
        numeric, _ = build(service(target=8000), doc)
        named, _ = build(service(target='http'), doc)
        self.assertEqual(numeric[0]['status'], 'partial')
        self.assertEqual(len(numeric[0]['nodes']), 2)
        self.assertEqual(named[0]['status'], 'unresolved')
        self.assertIn('named-target-port-not-found', named[0]['reasons'])

    def test_no_selector_is_not_match_all_and_external_name(self):
        svc = service()
        del svc['spec']['selector']
        paths, _ = build(svc, workload())
        self.assertEqual(paths[0]['reasons'], ['selectorless-service'])
        svc['spec'].update(type='ExternalName', externalName='db.example.com')
        paths, _ = build(svc)
        self.assertEqual(paths[0]['nodes'][-1]['kind'], 'ExternalName')
        self.assertEqual(paths[0]['reasons'], ['external-dns-not-resolved'])

    def test_ingress_missing_service_wrong_namespace_and_port(self):
        paths, _ = build(ingress(namespace='prod'), service(namespace='dev'))
        chain = next(p for p in paths if p['nodes'][0]['kind'] == 'Ingress')
        self.assertEqual(chain['reasons'], ['service-not-found'])
        bad = ingress(backend={'service': {'name': 'api', 'port': {'number': 9999}}})
        paths, _ = build(bad, service())
        self.assertEqual(next(p for p in paths if p['nodes'][0]['kind'] == 'Ingress')['reasons'], ['service-port-not-found'])

    def test_ingress_default_and_resource_backends(self):
        doc = ingress()
        doc['spec'] = {'defaultBackend': {'service': {'name': 'api', 'port': {'number': 80}}}}
        paths, _ = build(doc, service(), workload())
        chain = next(p for p in paths if p['nodes'][0]['kind'] == 'Ingress')
        self.assertEqual(chain['nodes'][0]['path'], '*')
        doc['spec']['defaultBackend'] = {'resource': {'kind': 'StorageBucket', 'name': 'assets'}}
        paths, _ = build(doc)
        self.assertEqual(paths[0]['reasons'], ['unsupported-ingress-backend'])

    def test_fanout_and_duplicate_declarations_are_not_silently_selected(self):
        paths, _ = build(service(), workload('a'), workload('b'))
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(p['status'] == 'declared' for p in paths))
        paths, _ = build(service(), service(), workload())
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(p['status'] == 'candidate' for p in paths))
        self.assertTrue(all('duplicate-resource-declarations' in p['reasons'] for p in paths))

    def test_multiple_matching_containers_remain_candidates(self):
        doc = workload()
        other = copy.deepcopy(doc['spec']['template']['spec']['containers'][0])
        other['name'] = 'sidecar'
        doc['spec']['template']['spec']['containers'].append(other)
        paths, _ = build(service(), doc)
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(p['status'] == 'candidate' for p in paths))

    def test_json_list_and_exclusion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'k.json').write_text(json.dumps({'kind': 'List', 'items': [service(), workload()]}))
            report = scan(root)
            self.assertEqual(len(report['connections']), 1)
            self.assertIn('document.items[0]', report['connections'][0]['nodes'][0]['reference'])
            self.assertEqual(scan(root, ['k.json'])['connections'], [])

    def test_malformed_resource_does_not_lose_valid_paths(self):
        broken = service('broken')
        broken['spec']['selector'] = ['not-a-map']
        paths, diagnostics = build(broken, service(), workload())
        self.assertEqual(len(paths), 1)
        self.assertEqual(len(diagnostics), 1)

    def test_pod_and_cronjob_template_references(self):
        base = workload()
        pod = {'kind': 'Pod', 'metadata': {'name': 'pod', 'labels': {'app': 'api', 'tier': 'web'}},
               'spec': base['spec']['template']['spec']}
        cron = {'kind': 'CronJob', 'metadata': {'name': 'scheduled'},
                'spec': {'jobTemplate': {'spec': {'template': base['spec']['template']}}}}
        paths, diagnostics = build(service(), pod, cron)
        self.assertEqual(diagnostics, [])
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(p['status'] == 'declared' for p in paths))
        cronpath = next(p for p in paths if p['nodes'][1]['kind'] == 'CronJob')
        self.assertIn('spec.jobTemplate.spec.template.spec.containers[0]', cronpath['nodes'][-1]['reference'])

    def test_invalid_namespace_is_diagnostic_not_crash(self):
        doc = workload()
        doc['metadata']['namespace'] = ['invalid']
        paths, diagnostics = build(service(), doc)
        self.assertEqual(paths[0]['status'], 'unresolved')
        self.assertEqual(len(diagnostics), 1)
