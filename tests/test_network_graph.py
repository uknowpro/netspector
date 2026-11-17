import json
import tempfile
import unittest
from pathlib import Path

from netspector.network_graph import build_graph, host_identity
from netspector.scanner import scan
from netspector.html_report import render_html


def finding(target, direction='outbound', file='app.py', line=1, **extra):
    return dict(target=target, direction=direction, kind='http-client', file=file, line=line,
                status='confirmed', port=None, reference=None, evidence=[], candidates=[], **extra)


def report(findings, connections=None):
    return dict(findings=findings, connections=connections or [], diagnostics=[])


class NetworkGraphTests(unittest.TestCase):
    def test_one_host_for_both_directions_and_multiple_ports_paths(self):
        original = report([finding('https://API.Example.com./in', 'inbound'),
                           finding('http://api.example.com:8080/out'), finding('https://api.example.com/other')])
        graph = build_graph(original)
        hosts = [n for n in graph['nodes'] if n['kind'] == 'Host']
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0]['label'], 'api.example.com')
        self.assertEqual(len(graph['edges']), 2)
        self.assertEqual({(e['source'],e['target']) for e in graph['edges']},
                         {(graph['nodes'][0]['id'],hosts[0]['id']), (hosts[0]['id'],graph['nodes'][0]['id'])})
        self.assertEqual(sum(len(e['records']) for e in graph['edges']), 3)

    def test_duplicate_sources_retained_on_single_edge(self):
        graph = build_graph(report([finding('https://a.local/p', line=1),finding('https://a.local/p', line=2),finding('https://a.local/p', line=2)]))
        self.assertEqual(len(graph['edges']), 1)
        self.assertEqual(len(graph['edges'][0]['records']), 2)

    def test_unknown_configuration_does_not_invent_outbound(self):
        config = finding('https://a.local/p', 'unknown');config['kind']='configuration';config['status']='candidate'
        graph = build_graph(report([config]))
        self.assertEqual(graph['edges'][0]['relation'], 'association')
        combined = build_graph(report([config, finding('https://a.local/p')]))
        self.assertEqual(len(combined['edges']), 1)
        self.assertEqual(len(combined['edges'][0]['records']), 2)
        self.assertFalse(combined['edges'][0]['uncertain'])

    def test_path_only_route_is_not_a_host(self):
        route = finding('/health', 'inbound');route['kind']='route'
        graph = build_graph(report([route]))
        self.assertEqual(len(graph['nodes']), 1)
        self.assertEqual(graph['nodes'][0]['kind'], 'Application')
        self.assertEqual(graph['edges'], [])

    def test_unresolved_and_candidates_remain_uncertain(self):
        unknown = finding('<dynamic>'); unknown['status']='unresolved'
        graph = build_graph(report([unknown]))
        self.assertTrue(graph['edges'][0]['uncertain'])
        unknown['candidates']=[dict(target='https://a.local',file='.env',reference='URL')]
        graph=build_graph(report([unknown]))
        self.assertTrue(graph['edges'][0]['uncertain'])
        self.assertFalse(any(n['kind']=='Unresolved' for n in graph['nodes']))

    def test_monorepo_boundaries_and_excluded_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for path,content in {'pyproject.toml':'', 'services/a/pom.xml':'<project/>',
                                 'services/a/src/app.py':'import httpx\nhttpx.get("https://shared.local")',
                                 'services/b/package.json':'{}', 'services/b/app.py':'import httpx\nhttpx.get("https://shared.local")'}.items():
                dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(content)
            result=scan(root)
            graph=build_graph(result)
            self.assertEqual(graph['projects'], ['services/a','services/b'])
            self.assertEqual(sum(n['kind']=='Host' for n in graph['nodes']),1)
            self.assertEqual(sum(n['kind']=='Application' for n in graph['nodes']),2)
            self.assertEqual(len(graph['edges']),2)
            excluded=scan(root, ['services/a/pom.xml'])
            self.assertNotIn('services/a',excluded['project']['roots'])

    def test_namespace_and_workload_keep_containers_separate(self):
        chains=[]
        for name,namespace in [('a','dev'),('b','dev'),('a','prod')]:
            nodes=[dict(kind='Service', name=name, namespace=namespace, file='k.yaml'),
                   dict(kind='Deployment',name=name,namespace=namespace,file='k.yaml'),
                   dict(kind='Container',name='api',namespace=namespace,file='k.yaml',port=80)]
            chains.append(dict(nodes=nodes, direction='inbound',namespace=namespace,status='declared',evidence=[],reasons=[]))
        graph=build_graph(report([],chains))
        self.assertEqual(sum(n['kind']=='Container' for n in graph['nodes']),3)
        self.assertEqual(len(graph['edges']),6)

    def test_duplicate_topology_edges_and_standalone_port(self):
        demo=Path(__file__).resolve().parents[1]/'examples/demo'
        graph=build_graph(scan(demo))
        self.assertFalse(any(n['kind']=='Port declaration' for n in graph['nodes']))
        self.assertEqual(len({(e['source'],e['target']) for e in graph['edges']}), len(graph['edges']))

    def test_host_canonicalization_without_alias_guessing(self):
        self.assertEqual(host_identity('https://[2001:0db8::1]:443/p'), '2001:db8::1')
        self.assertEqual(host_identity('https://EXAMPLE.com./p'), 'example.com')
        self.assertNotEqual(host_identity('https://example.com'),host_identity('https://www.example.com'))
        for value in ['<dynamic>','/route','https://${HOST}/','https://a:bad','*']:
            self.assertIsNone(host_identity(value))

    def test_compact_html_groups_sources_without_losing_them(self):
        original=report([finding('https://a.local',line=1),finding('https://a.local',line=2)])
        html=render_html(original)
        self.assertEqual(html.count('data-record="finding"'),1)
        self.assertIn('Grouped endpoints · 1',html)
        self.assertIn('2 source record(s)',html)
        self.assertIn('<svg id="network-svg"',html)
        self.assertNotIn('<details class="inventory" open><summary>Grouped',html)
        self.assertEqual(html,render_html(original))
        self.assertEqual(len(original['findings']),2)
