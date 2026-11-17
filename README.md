<div align="center">

# netspector

**Discover application network intent from source and configuration.**

Trace inbound routes, outbound HTTP calls, and declared infrastructure ports—before deployment.

[![CI](https://github.com/uknowpro/netspector/actions/workflows/ci.yml/badge.svg)](https://github.com/uknowpro/netspector/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**English** · [한국어](README.ko.md)

</div>

---

## Why netspector?

Network knowledge is scattered across application code, environment files, and deployment manifests. netspector brings those declarations into a reproducible inventory, with a source location for every finding.

Use it to review application dependencies, investigate declared exposure, or export an inventory for further analysis. It performs static analysis: a finding describes code or configuration, not observed traffic or verified reachability.


> **Source preview (`0.3.0.dev0`):** The compact project/host graph described below is available from the current source. The v0.2.0 downloads still use the earlier HTML layout.

## Download standalone executables

Download **[netspector v0.2.0](https://github.com/uknowpro/netspector/releases/tag/v0.2.0)**, extract the archive, and run the executable. Python is bundled.

| System | Download | Target |
| --- | --- | --- |
| Linux x64 | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.2.0/netspector-0.2.0-linux-x86_64.tar.gz) | Ubuntu 22.04+ / glibc 2.35+ |
| macOS Intel | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.2.0/netspector-0.2.0-macos-x86_64.tar.gz) | macOS 15+ |
| macOS Apple Silicon | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.2.0/netspector-0.2.0-macos-arm64.tar.gz) | macOS 15+ |
| Windows 10 x86 (32-bit) | [zip](https://github.com/uknowpro/netspector/releases/download/v0.2.0/netspector-0.2.0-windows-x86.zip) | 32-bit Windows 10 compatibility target |
| Windows 10/11 x64 | [zip](https://github.com/uknowpro/netspector/releases/download/v0.2.0/netspector-0.2.0-windows-x86_64.zip) | Windows 10/11 compatibility target |

Linux/macOS: `./netspector scan ./examples/demo`. Windows PowerShell: `.\netspector.exe scan .\examples\demo`.

Native archives are smoke-tested on Ubuntu 22.04, macOS 15 (both architectures), and Windows Server 2022. The x86 build uses 32-bit Python and its PE32/I386 executable headers are verified before and after packaging. Both Windows builds are executed on Windows Server 2022 (x86 via WOW64); testing on a native 32-bit Windows 10 device is pending. Windows binaries are unsigned; macOS binaries are not Developer ID signed or notarized. Download protections may require user approval. See the [release notes](docs/releases/v0.2.0.md) for details and use the release's `SHA256SUMS` to check downloads. Linux ARM64, Alpine/musl, Windows ARM64, and 32-bit Linux/macOS standalone binaries are not provided. Choose `windows-x86.zip` for 32-bit Windows; `windows-x86_64.zip` requires 64-bit Windows.

## Install from source

Requires Python 3.11+ and pip. Install from this repository; a PyPI release is not currently part of this project.

```bash
git clone https://github.com/uknowpro/netspector.git
cd netspector
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

netspector scan examples/demo
```

On Windows, activate with `.venv\Scripts\activate` instead. You can also run `python -m netspector` after installing dependencies.

The bundled demo produces eight findings and two network paths, including:

```text
DIRECTION  KIND            TARGET                                  PORT  STATUS
inbound    route           /health                                 -     declared
inbound    route           /weather                                -     declared
outbound   http-client     https://weather.example.com/v1/current  443   confirmed
outbound   http-client     <dynamic>                               -     candidate
unknown    configuration   https://notify.example.com/events       443   candidate
inbound    container-port  weather/api                             8000  declared
inbound    service         weather                                 80    declared
inbound    ingress         weather.example.com/                    -     declared
```

The actual table also includes a source column. The dynamic `NOTIFY_URL` call now carries a candidate target, `https://notify.example.com/events`, with its declaration in `deployment.yaml`. Candidates do not establish which deployment runs this source file.

## Current capabilities

| Input | Extracted information |
| --- | --- |
| Java (bounded analysis) | Direct Spring controller mapping annotations; typed RestTemplate calls; JDK HttpRequest URI declarations; constants, getenv, and @Value references |
| Python | Literal FastAPI/APIRouter route paths; requests/httpx HTTP method calls; basic import aliases, local/module client instances, and unique straight-line constant bindings |
| Kubernetes YAML / JSON | Container ports in Pod, Deployment, StatefulSet, DaemonSet, Job, CronJob; Service ports, numeric/named targetPort resolution, selector-to-workload paths; Ingress host/path declarations; multi-document YAML and List resources; environment values and referenced ConfigMaps |
| JSON, YAML, TOML | URL-valued strings with configuration key paths |
| `.properties` | URL-valued properties, escaped keys/values, continuations, and line numbers |
| `.env*` | URL-valued assignments with line numbers |
| `.ini` | Sections, DEFAULT inheritance, URL values, host/port groups |
| `.xml` | URL text/attributes, Spring bean properties/map entries, web.xml servlet mappings and context/init parameters |

No target application code is imported or executed. YAML uses a safe loader. The scanner does not contact discovered endpoints, read your process environment to resolve variables, or invoke Helm/Terraform.

## CLI reference

```bash
netspector --version
netspector scan ./project
netspector scan ./project --direction outbound
netspector scan ./project --format json
netspector scan ./project --format csv --output connections.csv
netspector scan ./project --format html --output report.html
netspector scan ./project --exclude 'tests/*' --exclude '**/fixtures/**'
```

| Option | Values / behavior |
| --- | --- |
| `--format` | `table` (default), `json`, `csv`, `html` |
| `--direction` | `inbound`, `outbound`, `unknown`; omit to show all |
| `--exclude` | Repeatable relative-path glob; quote patterns in your shell |
| `--output` | Write a report to a file instead of standard output |

Exit codes: **0** complete scan; **1** partial scan with diagnostics; **2** invalid invocation, invalid root, or output failure. Diagnostics go to stderr and are also included in JSON and HTML. CSV contains findings and connection records. Missing topology references are reported as unresolved paths, not parser failures.

Common dependency/build directories (`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`, `target`, `.gradle`) and symbolic-link files are skipped. Supported files larger than 2 MB generate a diagnostic. `.gitignore` rules are not interpreted; use `--exclude` for additional exclusions.

## Understand the output

| Status | Meaning |
| --- | --- |
| `confirmed` | A literal outbound target was found in a recognized HTTP call; not proof of execution |
| `declared` | An inbound route, port, or exposure is explicitly declared |
| `candidate` | A configuration URL or possible environment target; deployment association is not established |
| `inferred` | A target was resolved through unique, straight-line Python bindings |
| `unresolved` | A dynamic target or a missing topology reference |
| `partial` | A Service selects a workload with a numeric target, but no matching container port is declared |

Each finding includes `direction`, `kind`, `target`, `protocol`, `port`, `status`, `file`, `line`, `reference`, `evidence`, and `candidates`. JSON wraps findings, connections, and diagnostics in a `schema_version: "1"` envelope. Paths are relative to the scanned root; structured configuration uses key references where available and `line: null`. Output is sorted and exact duplicates are removed.

URL credentials, query strings, and fragments are omitted from reported URL targets. CSV cells starting with formula markers are escaped. Reports may still contain internal hostnames, URL paths, and application identifiers; review them before sharing.

## Constant and environment resolution

```python
import os
import httpx

URL = os.getenv("NOTIFY_URL")
httpx.post(URL)
```

netspector follows unique assignments and records their file/line provenance in `evidence`. For environment references it searches scanned `.env*` files and Kubernetes container declarations. Supported sources include `env.value`, `env.valueFrom.configMapKeyRef`, and `envFrom.configMapRef` (including prefixes). ConfigMap lookup respects namespace; explicit container `env` entries suppress the same name from `envFrom`.

A matching declaration adds a redacted URL and provenance to `candidates`. Kubernetes candidates include workload, namespace, and container; ConfigMap candidates include the referring manifest as `via`. The primary target stays `<dynamic>` and status becomes `candidate`, even for a single match: repository proximity is not proof of an application/deployment relationship. Multiple files, workloads, or environment variants remain visible rather than silently choosing a winner. Unreferenced ConfigMaps and Secrets are not used as environment values.

JSON includes structured evidence and candidates. CSV stores those arrays as JSON cells; terminal tables display candidate URLs and declaration files below findings. No schema fields were removed (`schema_version` remains `1`); CSV includes `evidence` and `candidates` as JSON cells.

## Java and Spring support

```bash
netspector scan ./java-project --format html --output java-report.html
netspector scan examples/java --format json
```

Java is scanned without a JDK, Maven, Gradle, or native parser dependency, including in Windows x86 builds. The analyzer tokenizes comments and literals and inspects a bounded set of declarations; it is **not a Java compiler or a whole-program type resolver**.

| Pattern | Behavior |
| --- | --- |
| Direct `@RestController` / `@Controller` classes | Class `@RequestMapping` prefixes combined with method `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping` paths; `value`/`path` arrays supported |
| Typed `RestTemplate` fields, parameters, scalar locals | Recognized HTTP methods such as `getForObject`, `postForEntity`, `exchange`, `put`, and `delete`; unknown first-argument overloads remain unresolved |
| JDK `HttpRequest.newBuilder(URI)` / `.newBuilder().uri(URI)` / typed `HttpRequest.Builder.uri` | Outbound `http-request` **declarations**, not proof of `HttpClient.send` or actual traffic |
| String expressions | Literals, same-class final fields, unique straight-line scalar locals, and fully known string concatenation; `URI.create(String)` and `new URI(String)` wrappers |
| `System.getenv("NAME")` | Existing dotenv/Kubernetes environment candidates |
| Field `@Value("${key}")` | Exact-key URL candidates from UTF-8 `.properties`, `application*.yaml/yml/json`, `bootstrap*.yaml/yml/json`, and exact-name environment declarations |

Imports or fully qualified Spring/client types are required. Classes merely using the same method or annotation names are not treated as Spring/HTTP clients. Named placeholders in configuration use the bounded resolver described below; profile priority, relaxed property naming, and default values are not evaluated. Multiple configuration sources remain candidates; no runtime configuration is read. Properties files support continuations and escapes, including Unicode escapes.

Remaining cases include inherited/interface controller mappings, custom composed annotations, HTTP-method/parameter/header routing constraints, servlet context paths, WebClient, RestClient, Feign, OkHttp, Apache HttpClient, database/broker clients, cross-file constants, factory-returned clients, `var` type inference, field-initializer HTTP calls, and general builder/data-flow analysis. Lambda bodies, anonymous/local classes, and uncertain nested bindings are skipped or left unresolved. Text blocks are skipped rather than interpreted as URLs. Unicode preprocessing outside string literals, full Java syntax validation, reflection, and generated code are not modeled. Unbalanced/unterminated lexical structures produce file diagnostics; other files continue scanning. Methods and runtime bean registration are not executed.

See the official [Spring request mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) and [JDK HttpRequest](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html) documentation for API semantics.

## Configuration references and endpoint groups

```bash
netspector scan examples/config --format html --output config-report.html
```

INI, XML, properties, dotenv, JSON, YAML, and TOML share a conservative configuration pass:

- Resolve exact `${NAME}` references recursively from scanned declarations, retaining file/key/line evidence. Missing values, cycles, and unsupported placeholder syntax remain unresolved. The shell and process environment are never consulted.
- Combine sibling `host`/`hostname` and `port` keys, with optional `scheme`/`protocol` and `path`. Dot-separated and underscore-separated names are supported. For example, `api.host=api.example.com`, `api.port=443`, and `api.scheme=https` yield `https://api.example.com:443`. Without a scheme, the result is `api.example.com:443` with no inferred protocol.
- Keep each file and YAML document separate. A candidate may use its own declarations and **one** other file/document; dev/prod values are not combined across multiple external files. Every matching variant remains a candidate, with no profile precedence or application association inferred.
- Export resolved dotenv URLs to `getenv` candidates and resolved properties/application/bootstrap configuration URLs to Java `@Value` candidates. Synthetic host/port groups do not invent a URL property.

These are `unknown` direction, `candidate` findings (`configuration` or `configuration-endpoint`), not observed connections. Invalid or incomplete groups remain `unresolved`. Arbitrary keys are not evidence of a listener or outbound call. Duplicate keys are not selected silently. INI uses case-sensitive keys, literal `%` values, and DEFAULT inheritance; inherited entries report their source line. XML ignores schema namespace URLs, records element lines, supports Spring property value attributes/nested `<value>` and map entries, and reads web.xml servlet patterns as declared inbound routes. XML DTDs and entities are rejected before expansion; bean references, imports, external resources, and runtime bean activation are not followed.

Limits: `${NAME:default}`, shell expansion, INI `%()` interpolation, Spring relaxed binding/profile activation, and Kubernetes `$(VAR)` expansion are not evaluated. Dotenv quotes are stripped by the lexical reader; reference resolution is a static candidate search, not a simulation of shell quoting or dotenv load order. Cross-file chains requiring more than one external document remain unresolved. Expansion is bounded to 16 levels, 8 KiB values, 2,048 resolution visits per value, and 64 external candidate documents; size/work/candidate limits produce diagnostics. Recursive YAML aliases are rejected. Generic `.conf`, Jenkinsfile, raw Helm templates, and Terraform `.tf` still require dedicated analyzers.

## Kubernetes network paths

```text
Ingress/weather-public (weather.example.com/)
  → Service/weather:80
  → Deployment/weather
  → Container/api:8000
```

Services match Pod labels or workload **Pod template** labels in the same namespace, requiring every selector entry. Missing namespaces use `default`; no cluster context is read. Supported workloads: Pod, Deployment, StatefulSet, DaemonSet, ReplicaSet, Job, and CronJob. Numeric and named `targetPort` values are matched against regular container port declarations and protocols. Omitted `targetPort` defaults to the Service port. Numeric targets remain partial when container ports are not declared—Kubernetes does not require those declarations for routing.

Ingress service backends resolve by port name or number, including `defaultBackend`. Each connection contains ordered `nodes`, a stable `id`, `status`, `reasons`, and file/document/key-path `evidence`. All matches are retained. Duplicate resource declarations and multiple matching container ports remain candidates. Missing Services, ports, or selectors remain visible; selectorless Services do not select all workloads. ExternalName targets are recorded without DNS resolution. Resource-type Ingress backends, EndpointSlices, TLS/controller behavior, pod readiness, init containers, and effective reachability are not resolved. This does not associate Python source with a workload.

JSON adds `connections` while retaining `schema_version: "1"`. CSV adds `record_type` (`finding` or `connection`) and a JSON `connection` column; existing finding columns remain. Consumers wanting only endpoint rows should filter `record_type=finding`. `--direction outbound` excludes inbound topology paths.

See the Kubernetes [Service](https://kubernetes.io/docs/concepts/services-networking/service/) and [Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/) documentation for manifest semantics.

## Offline HTML reports

```bash
netspector scan ./project --format html --output report.html
```

Open `report.html` in a browser. The first screen is a compact, interactive network graph. Endpoint tables, infrastructure paths, and diagnostics are collapsed below it (diagnostics open when present). Select a node or connection to inspect ports, URL paths, candidates, and original source evidence. Zoom, project selection, search, and direction filters run locally.

- **One host, one node:** DNS names are normalized for case, trailing dots, and IDNA; IP addresses use canonical notation. Scheme, port, and URL path do not create additional host nodes. DNS aliases and different IPs are not guessed to be the same machine. Host identities are shared across the report, including literal `localhost` names; this describes declared addresses, not physical machine identity.
- **Directed, deduplicated connections:** repeated source → target pairs become one edge; the reverse direction remains a separate arrow using the same nodes. Ports, paths, and distinct evidence stay on the edge. Repeated configuration URLs supporting the same directed edge are included as evidence instead of adding another parallel line. Configuration-only associations have no arrow; candidates/unresolved edges are dashed. An edge with both concrete and candidate evidence uses a solid line, with all statuses retained in details.
- **Project grouping:** the nearest scanned `pyproject.toml`, `setup.py`, `setup.cfg`, `package.json`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `go.mod`, `Cargo.toml`, `composer.json`, or `*.csproj` directory defines the group. Nested projects remain separate. Files without a closer marker belong to the scan root. This is directory-based grouping, not runtime application discovery. Excluded markers do not create groups.
- **Meaning of inbound:** path-only routes stay on their application node because no remote caller is known. An Ingress host is an exposure address, not a client identity. Kubernetes Service/workload/container nodes retain namespace and workload scope; source projects are not automatically connected to deployment resources.
- **Compact but traceable:** endpoint rows with the same project, direction, target, and port are grouped; every source record remains expandable. JSON/CSV retain the original findings. JSON adds `project.roots` metadata without changing `schema_version`. The graph shows up to 160 nodes at once and explicitly reports truncation; use the project/search filters to inspect the remainder. Full grouped records remain below.

JavaScript is needed for the interactive graph. Without it, the grouped tables and infrastructure paths remain accessible. Use `examples/network-map` for a two-application example sharing the same host.

No CDN, external assets, or endpoint requests are used. Source text is HTML-escaped, and the report restricts scripts with a content security policy. Without JavaScript, all grouped records remain accessible in the expandable sections. Reports can contain internal identifiers and should be reviewed before sharing.

## Architecture

```text
Project files
    → Python AST / Java tokens / safe YAML / JSON / TOML / properties / dotenv / INI / XML readers
    → Common finding model + source evidence
    → Deterministic ordering and exact deduplication
    → Table / JSON / CSV / HTML
```

## Limits and roadmap

This is an initial, deliberately bounded implementation. It does not perform whole-program data-flow analysis. For Python, only unique straight-line assignments are resolved; reassigned names, conditional bindings, and parameter shadowing remain unresolved. String interpolation, runtime environment defaults/expansion, wrapper functions, class methods, lambdas, comprehensions, router mounting/prefix composition, and cross-file Python references are unsupported. Source analysis does not model execution order across function calls or dynamic monkey-patching. Environment declarations are searched across the scan root, so scan each application separately or use exclusions to limit candidates.

Kubernetes ports indicate declarations, not actual listeners. Ingress TLS, effective reachability, NetworkPolicy, Secret resolution and deployment/environment selection are not modeled. ConfigMap references are supported only for container environment declarations. Generic URL findings may overlap with source findings. Parser failures preserve other scan results.

Planned next steps:

- [x] Bounded constant and environment-reference resolution with provenance
- [x] Kubernetes container environment and ConfigMap references
- [x] Kubernetes Service → workload correlation and Ingress paths
- [x] Offline HTML reports with search and evidence
- [ ] Helm rendered-manifest workflow and explicit values selection
- [ ] Terraform resource/reference analysis without applying infrastructure
- [x] Initial Java/Spring and JDK HTTP request analysis
- [ ] Additional Java clients, languages, and database/broker clients
- [x] Standalone releases for Linux, macOS, and Windows
- [x] XML/INI and bounded configuration references / host-port groups
- [ ] Larger real-world regression fixtures

Raw Helm templates and Terraform `.tf` files are not supported. Rendered Helm YAML can be scanned as Kubernetes YAML.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m netspector scan examples/demo --format json
```

Tests cover source extraction, redaction, dynamic references, configuration candidates, Kubernetes ports, exclusions, partial errors, deterministic output, and CLI formats. CI runs on Python 3.11–3.13 across Linux, macOS, and Windows Server, with separate Windows x86 interpreter jobs. Tagged releases build five native archives and test their extracted executables outside the source checkout, including Unicode paths, JSON/CSV output, and error exit codes. Wheels are installed and exercised in a clean environment.

Contributions are welcome. Include a small input fixture, expected findings, and false-positive cases when adding an analyzer. Keep claimed support aligned with tested behavior.

## License

[MIT](LICENSE) © 2026 uknow.
