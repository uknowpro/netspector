import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netspector.scanner import scan


class ConfigurationTests(unittest.TestCase):
    def scan(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in files.items():
                path = Path(tmp, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            return scan(Path(tmp))

    def test_ini_sections_protocol_and_plain_port(self):
        report = self.scan({'app.ini': '[api]\nhost=api.example.com\nport=443\nscheme=https\npath=/v1\n[db]\nhost=db.local\nport=5432\n'})
        self.assertFalse(report['diagnostics'])
        rows = {f['target']: f for f in report['findings']}
        self.assertEqual(set(rows), {'https://api.example.com:443/v1', 'db.local:5432'})
        self.assertIsNone(rows['db.local:5432']['protocol'])
        self.assertEqual(rows['https://api.example.com:443/v1']['line'], 2)
        self.assertEqual(len(rows['https://api.example.com:443/v1']['evidence']), 4)

    def test_ini_defaults_and_literal_percent(self):
        report = self.scan({'app.ini': '[DEFAULT]\nport=443\n[api]\nhost=api.local\nurl=https://api.local/%(literal)s\n'})
        targets = {f['target'] for f in report['findings']}
        self.assertIn('api.local:443', targets)
        self.assertIn('https://api.local/%(literal)s', targets)

    def test_malformed_ini_xml_continue_without_secret(self):
        report = self.scan({'a.ini':'[x]\nurl=SECRET\nurl=OTHER_SECRET', 'b.xml':'<bad>SECRET', 'good.json':'{"url":"https://ok.local"}'})
        self.assertEqual(len(report['diagnostics']), 2)
        self.assertEqual(report['findings'][0]['target'], 'https://ok.local')
        self.assertNotIn('SECRET', json.dumps(report))

    def test_xml_spring_and_namespace(self):
        source = '''<beans xmlns="http://www.springframework.org/schema/beans" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://unused/schema">
<bean id="one"><property name="host" value="api.local"/><property name="port"><value>443</value></property><property name="scheme" value="https"/></bean>
<bean id="two"><property name="url" value="https://u:secret@two.local/v1?token=SECRET"/></bean></beans>'''
        report = self.scan({'spring.xml': source})
        self.assertFalse(report['diagnostics'])
        self.assertEqual({f['target'] for f in report['findings']}, {'https://api.local:443', 'https://two.local/v1'})
        self.assertNotIn('SECRET', json.dumps(report))
        self.assertNotIn('secret', json.dumps(report))

    def test_web_xml_mapping_and_params(self):
        report = self.scan({'web.xml': '<web-app><context-param><param-name>audit.url</param-name><param-value>https://audit.local</param-value></context-param><servlet-mapping><servlet-name>api</servlet-name><url-pattern>/api/*</url-pattern><url-pattern>*.do</url-pattern></servlet-mapping></web-app>'})
        self.assertEqual({f['target'] for f in report['findings']}, {'https://audit.local', '/api/*', '*.do'})
        self.assertEqual(sum(f['direction'] == 'inbound' for f in report['findings']), 2)

    def test_xml_external_and_internal_entities_rejected(self):
        for declaration in ['<!DOCTYPE r SYSTEM "file:///etc/passwd">', '<!DOCTYPE r [<!ENTITY x "https://secret.local">]>']:
            with self.subTest(declaration=declaration):
                report = self.scan({'a.xml': declaration + '<r>&x;</r>'})
                self.assertEqual(len(report['diagnostics']), 1)
                self.assertFalse(report['findings'])

    def test_xml_generic_and_no_cross_beans(self):
        report = self.scan({'a.xml': '<root><server host="a.local" port="80"/><server><host>b.local</host><port>81</port></server><bean><property name="host" value="not-combined"/></bean><bean><property name="port" value="99"/></bean></root>'})
        self.assertEqual({f['target'] for f in report['findings']}, {'a.local:80', 'b.local:81'})

    def test_profiles_stay_coherent(self):
        report = self.scan({'application.properties': 'api.url=https://${HOST}:${PORT}/v1\n', '.env.dev': 'HOST=dev.local\nPORT=8443', '.env.prod':'HOST=prod.local\nPORT=443'})
        rows = [f for f in report['findings'] if f['reference'] == 'api.url']
        self.assertEqual({f['target'] for f in rows}, {'https://dev.local:8443/v1', 'https://prod.local:443/v1'})
        self.assertTrue(all(len(f['evidence']) == 3 for f in rows))

    def test_do_not_join_different_external_files(self):
        report = self.scan({'a.properties':'url=https://${HOST}:${PORT}', '.env.host':'HOST=a.local', '.env.port':'PORT=443'})
        self.assertEqual(report['findings'][0]['target'], '<dynamic>')
        self.assertEqual(report['findings'][0]['status'], 'unresolved')

    def test_recursive_and_repeated_references(self):
        report = self.scan({'a.properties':'BASE=https://${HOST}\nHOST=a.local\nurl=${BASE}/${HOST}'})
        self.assertIn('https://a.local/a.local', {f['target'] for f in report['findings']})

    def test_missing_cycle_defaults_no_runtime_environment(self):
        with patch.dict(os.environ, {'HOST':'secret.local'}):
            report = self.scan({'a.properties':'url=https://${HOST}\nloop.url=${A}\nA=${B}\nB=${A}\ndefault.url=https://${HOST:secret.local}'})
        self.assertEqual({f['target'] for f in report['findings']}, {'<dynamic>'})
        self.assertNotIn('secret.local', json.dumps(report))

    def test_all_structured_formats_and_document_boundaries(self):
        files = {'a.json':'{"api":{"host":"a.local","port":443,"scheme":"https"}}', 'b.toml':'[api]\nhost="b.local"\nport=80', 'c.yaml':'api:\n  host: c.local\n---\napi:\n  port: 80\n'}
        self.assertEqual({f['target'] for f in self.scan(files)['findings']}, {'https://a.local:443', 'b.local:80'})

    def test_env_expansion_reaches_python_candidate(self):
        report = self.scan({'.env':'HOST=notify.local\nURL=https://${HOST}/v1', 'app.py':'import os, httpx\nhttpx.get(os.getenv("URL"))'})
        call = next(f for f in report['findings'] if f['kind'] == 'http-client')
        self.assertEqual(call['candidates'][0]['target'], 'https://notify.local/v1')
        self.assertEqual(len(call['candidates'][0]['evidence']), 2)

    def test_java_property_expansion(self):
        report = self.scan({'application.properties':'host=api.local\napi.url=https://${host}', 'App.java':'import org.springframework.web.client.RestTemplate; import org.springframework.beans.factory.annotation.Value; class App { @Value("${api.url}") String url; RestTemplate rest; void run(){rest.getForObject(url, String.class);} }'})
        call = next(f for f in report['findings'] if f['kind'] == 'http-client')
        self.assertEqual(call['candidates'][0]['target'], 'https://api.local')

    def test_invalid_ports_and_credentials_remain_unresolved(self):
        for host, port in [('u:secret@host', '443'), ('host', '99999'), ('host', '-1'), ('host','true')]:
            report = self.scan({'a.ini': f'[api]\nhost={host}\nport={port}'})
            self.assertEqual(report['findings'][0]['target'], '<dynamic>')
            self.assertNotIn('secret', json.dumps(report))

    def test_ipv6_and_env_grouping(self):
        report = self.scan({'.env':'API_HOST=::1\nAPI_PORT=443\nAPI_SCHEME=https'})
        self.assertEqual(report['findings'][0]['target'], 'https://[::1]:443')

    def test_duplicate_keys_not_selected(self):
        report = self.scan({'a.properties':'host=a.local\nhost=b.local\nurl=https://${host}'})
        self.assertEqual({f['target'] for f in report['findings']}, {'<dynamic>'})

    def test_yaml_recursive_alias_is_diagnostic(self):
        report = self.scan({'a.yaml':'a: &a\n  child: *a'})
        self.assertEqual(len(report['diagnostics']), 1)

    def test_deterministic(self):
        files = {'a.ini':'[api]\nhost=${HOST}\nport=${PORT}', '.env':'HOST=a.local\nPORT=80'}
        self.assertEqual(self.scan(files), self.scan(files))

    def test_section_local_reference(self):
        report = self.scan({'a.ini':'[api]\nhost=api.local\nurl=https://${host}'})
        self.assertEqual(report['findings'][0]['target'], 'https://api.local')

    def test_expansion_work_limit_is_reported(self):
        source = 'x0=host\n' + '\n'.join('x%d=${x%d}${x%d}' % (i, i-1, i-1) for i in range(1, 15)) + '\nurl=https://${x14}'
        report = self.scan({'a.properties':source})
        self.assertTrue(report['diagnostics'])
        self.assertEqual({f['target'] for f in report['findings']}, {'<dynamic>'})

    def test_invalid_ipv6_is_not_concrete(self):
        report = self.scan({'a.ini':'[api]\nhost=not:ipv6\nport=443\nscheme=https'})
        self.assertEqual(report['findings'][0]['target'], '<dynamic>')
