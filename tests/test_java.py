import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from netspector.cli import main
from netspector.scanner import scan
from netspector.java_properties import properties


class JavaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')

    def findings(self, direction=None):
        report = scan(self.root)
        self.assertEqual(report['diagnostics'], [])
        return [f for f in report['findings'] if direction is None or f['direction'] == direction]

    def test_spring_class_method_paths_arrays_constants_and_lines(self):
        self.write('Api.java', '''package example;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping(path = {"/api", "/v2"})
class Api {
    private static final String USERS = "/users";
    @GetMapping(path = {USERS, "/people"})
    String users() { return "ok"; }
    @PostMapping
    String create() { return "ok"; }
}
''')
        findings = self.findings('inbound')
        self.assertEqual({f['target'] for f in findings}, {'/api/users', '/api/people', '/v2/users', '/v2/people', '/api', '/v2'})
        self.assertEqual({f['line'] for f in findings if f['target'].endswith('users')}, {7})
        self.assertTrue(any(e['line'] == 6 for f in findings for e in f['evidence']))

    def test_comments_strings_and_non_spring_annotations_are_ignored(self):
        self.write('Api.java', '''import custom.RestController;
import custom.GetMapping;
@RestController class Api {
 @GetMapping("/not-spring") void route() {}
 String example = "http.getForObject(\\"https://fake.example\\", String.class)";
 // @GetMapping("/comment")
 /* client.getForObject("https://comment.example", String.class); */
}
''')
        self.assertEqual(self.findings(), [])

    def test_mapping_without_controller_and_feign_not_inbound(self):
        self.write('Api.java', '''import org.springframework.web.bind.annotation.*;
@RequestMapping("/remote") interface Client { @GetMapping("/users") String get(); }
''')
        self.assertEqual(self.findings(), [])

    def test_resttemplate_fields_parameters_constants_and_concatenation(self):
        self.write('Api.java', '''import org.springframework.web.client.RestTemplate;
class Api {
 final String BASE = "https://user:secret@example.com";
 final RestTemplate rest = new RestTemplate();
 void run(RestTemplate injected) {
   final String URL = BASE + "/v1?token=hidden";
   rest.getForObject(URL, String.class);
   injected.postForEntity("https://other.example/events", null, String.class);
 }
}
''')
        findings = self.findings('outbound')
        self.assertEqual({f['target'] for f in findings}, {'https://example.com/v1', 'https://other.example/events'})
        self.assertNotIn('secret', json.dumps(findings))
        self.assertNotIn('hidden', json.dumps(findings))
        self.assertEqual(next(f for f in findings if f['target'].endswith('/v1'))['status'], 'inferred')

    def test_shadowing_reassignments_and_unknown_receivers(self):
        self.write('Api.java', '''import org.springframework.web.client.RestTemplate;
class Api {
 final String URL = "https://wrong.example";
 RestTemplate rest;
 void run(String URL, Object other) {
   rest.getForObject(URL, String.class);
   other.getForObject("https://fake.example", String.class);
 }
 void change() {
   String target = "https://old.example";
   target = computed();
   rest.getForObject(target, String.class);
 }
}
''')
        findings = self.findings('outbound')
        self.assertEqual(len(findings), 2)
        self.assertTrue(all(f['status'] == 'unresolved' for f in findings))

    def test_explicit_this_field_bypasses_parameter_shadow(self):
        self.write('Api.java', '''import org.springframework.web.client.RestTemplate;
class Api {
 final String URL = "https://field.example";
 RestTemplate rest;
 void run(String URL, Object rest) {
   this.rest.getForObject(this.URL, String.class);
 }
}
''')
        self.assertEqual(self.findings('outbound')[0]['target'], 'https://field.example')

    def test_jdk_builder_direct_chained_and_typed_are_declarations(self):
        self.write('Api.java', '''import java.net.URI;
import java.net.http.HttpRequest;
class Api {
 void run() {
  HttpRequest a = HttpRequest.newBuilder(URI.create("https://one.example")).GET().build();
  HttpRequest b = HttpRequest.newBuilder().uri(new URI("https://two.example")).build();
  HttpRequest.Builder builder = HttpRequest.newBuilder();
  builder.uri(URI.create("https://three.example"));
 }
}
''')
        findings = self.findings('outbound')
        self.assertEqual({f['target'] for f in findings}, {'https://one.example', 'https://two.example', 'https://three.example'})
        self.assertTrue(all(f['kind'] == 'http-request' and f['status'] == 'declared' for f in findings))

    def test_environment_reference_uses_existing_candidates(self):
        self.write('Api.java', '''import org.springframework.web.client.RestTemplate;
class Api {
 RestTemplate rest;
 void run() { rest.getForObject(System.getenv("API_URL"), String.class); }
}
''')
        self.write('.env', 'API_URL=https://env.example\n')
        finding, = self.findings('outbound')
        self.assertEqual(finding['reference'], 'env:API_URL')
        self.assertEqual(finding['candidates'][0]['target'], 'https://env.example')

    def test_value_properties_and_profile_candidates_without_precedence(self):
        self.write('Api.java', '''import org.springframework.web.client.RestTemplate;
import org.springframework.beans.factory.annotation.Value;
class Api {
 @Value("${upstream.url}") String upstream;
 RestTemplate rest;
 void run() { rest.getForObject(upstream, String.class); }
}
''')
        self.write('application.properties', 'upstream.url=https://user:secret@prod.example/api?token=hidden\n')
        self.write('application-dev.yaml', 'upstream:\n  url: https://dev.example/api\n')
        finding, = self.findings('outbound')
        self.assertEqual(finding['reference'], 'property:upstream.url')
        self.assertEqual(finding['status'], 'candidate')
        self.assertEqual({c['target'] for c in finding['candidates']}, {'https://prod.example/api', 'https://dev.example/api'})
        self.assertNotIn('secret', json.dumps(scan(self.root)))

    def test_dynamic_prefix_and_overloaded_requests_remain_unresolved(self):
        self.write('Api.java', '''import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
@RestController @RequestMapping("${api.prefix}") class Api {
 RestTemplate rest;
 @GetMapping("/items") void route() { rest.exchange(makeRequest(), String.class); }
}
''')
        self.assertTrue(all(f['target'] == '<dynamic>' for f in self.findings()))

    def test_nested_controller_does_not_inherit_outer_prefix(self):
        self.write('Api.java', '''import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/outer") class Api {
 @GetMapping("/a") void a() {}
 @RestController @RequestMapping("/inner") static class Inner {
  @GetMapping("/b") void b() {}
 }
}
''')
        self.assertEqual({f['target'] for f in self.findings()}, {'/outer/a', '/inner/b'})

    def test_malformed_java_does_not_abort_other_files(self):
        self.write('Bad.java', 'class Broken { "unterminated')
        self.write('good.json', '{"url":"https://good.example"}')
        report = scan(self.root)
        self.assertEqual(len(report['diagnostics']), 1)
        self.assertEqual(report['findings'][0]['target'], 'https://good.example')

    def test_properties_escapes_continuations_and_line_numbers(self):
        content = '# comment\nupstream\\.url = https\\://example.com/\\\n    api\nname\\ key: https://other.example\nunicode=\\u0068ttps://unicode.example\n'
        self.assertEqual(list(properties(content)), [('upstream.url', 'https://example.com/api', 2), ('name key', 'https://other.example', 4), ('unicode', 'https://unicode.example', 5)])

    def test_exports_and_build_directory_exclusion(self):
        source = 'import org.springframework.web.bind.annotation.*; @RestController class Api { @GetMapping("/java") void get() {} }'
        self.write('Api.java', source)
        self.write('target/Generated.java', source.replace('/java','/ignored'))
        for format in ('table', 'json', 'csv', 'html'):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['scan', str(self.root), '--format', format]), 0)
            self.assertIn('/java', output.getvalue())
            self.assertNotIn('/ignored', output.getvalue())
        self.assertEqual(scan(self.root, ['*.java'])['findings'], [])

    def test_lambda_anonymous_class_and_loop_shadowing_do_not_borrow_fields(self):
        self.write('Api.java', '''import org.springframework.web.client.RestTemplate;
class Api {
 RestTemplate rest;
 final String URL = "https://wrong.example";
 void lambda() {
  java.util.function.Consumer<Other> call = rest -> rest.getForObject("https://fake.example", String.class);
 }
 void anonymous() {
  Runnable r = new Runnable() {
   Other rest;
   public void run() { rest.getForObject("https://fake.example", String.class); }
  };
 }
 void loop(java.util.List<String> urls) {
  for (String URL : urls) { rest.getForObject(URL, String.class); }
 }
}
''')
        findings = self.findings('outbound')
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['status'], 'unresolved')

    def test_fully_qualified_types_and_annotations(self):
        self.write('Api.java', '''@org.springframework.web.bind.annotation.RestController
@org.springframework.web.bind.annotation.RequestMapping("/api")
class Api {
 org.springframework.web.client.RestTemplate rest;
 @org.springframework.web.bind.annotation.GetMapping("/health")
 void run() { rest.getForObject(java.net.URI.create("https://example.com"), String.class); }
}
''')
        self.assertEqual({f['target'] for f in self.findings()}, {'/api/health', 'https://example.com'})

    def test_text_blocks_and_escaped_unicode_strings(self):
        self.write('Api.java', r'''import org.springframework.web.client.RestTemplate;
class Api {
 RestTemplate rest;
 String example = """
 rest.getForObject("https://fake.example", String.class);
 """;
 void run() { rest.getForObject("https://example.com/\uD83D\uDE00", String.class); }
}
''')
        self.assertEqual(self.findings('outbound')[0]['target'], 'https://example.com/😀')
        self.assertEqual(len(self.findings('outbound')), 1)

    def test_same_method_names_on_custom_types_are_ignored(self):
        self.write('Api.java', '''import custom.RestTemplate;
import custom.HttpRequest;
class Api {
 RestTemplate rest;
 void run() {
  rest.getForObject("https://fake.example", String.class);
  HttpRequest.newBuilder("https://fake.example");
 }
}
''')
        self.assertEqual(self.findings(), [])

    def test_class_literal_does_not_hide_later_calls(self):
        self.write('Api.java', '''import org.springframework.web.client.RestTemplate;
class Api {
 RestTemplate rest;
 void run(boolean flag) {
  rest.getForObject("https://one.example", String.class);
  rest.getForObject("https://two.example", String.class);
  if (flag) { rest.getForObject("https://three.example", String.class); }
 }
}
''')
        self.assertEqual({f['target'] for f in self.findings('outbound')}, {'https://one.example', 'https://two.example', 'https://three.example'})
