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

> **Development branch (`0.2.0.dev0`):** Kubernetes network paths and HTML export are available when installed from the current source. The downloadable v0.1.1 executables do not yet include these features.

## Download standalone executables

Download **[netspector v0.1.1](https://github.com/uknowpro/netspector/releases/tag/v0.1.1)**, extract the archive, and run the executable. Python is bundled.

| System | Download | Target |
| --- | --- | --- |
| Linux x64 | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.1.1/netspector-0.1.1-linux-x86_64.tar.gz) | Ubuntu 22.04+ / glibc 2.35+ |
| macOS Intel | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.1.1/netspector-0.1.1-macos-x86_64.tar.gz) | macOS 15+ |
| macOS Apple Silicon | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.1.1/netspector-0.1.1-macos-arm64.tar.gz) | macOS 15+ |
| Windows 10 x86 (32-bit) | [zip](https://github.com/uknowpro/netspector/releases/download/v0.1.1/netspector-0.1.1-windows-x86.zip) | 32-bit Windows 10 compatibility target |
| Windows 10/11 x64 | [zip](https://github.com/uknowpro/netspector/releases/download/v0.1.1/netspector-0.1.1-windows-x86_64.zip) | Windows 10/11 compatibility target |

Linux/macOS: `./netspector scan ./examples/demo`. Windows PowerShell: `.\netspector.exe scan .\examples\demo`.

Native archives are smoke-tested on Ubuntu 22.04, macOS 15 (both architectures), and Windows Server 2022. The x86 build uses 32-bit Python and its PE32/I386 executable headers are verified before and after packaging. Both Windows builds are executed on Windows Server 2022 (x86 via WOW64); testing on a native 32-bit Windows 10 device is pending. Windows binaries are unsigned; macOS binaries are not Developer ID signed or notarized. Download protections may require user approval. See the [release notes](docs/releases/v0.1.1.md) for details and use the release's `SHA256SUMS` to check downloads. Linux ARM64, Alpine/musl, Windows ARM64, and 32-bit Linux/macOS standalone binaries are not provided. Choose `windows-x86.zip` for 32-bit Windows; `windows-x86_64.zip` requires 64-bit Windows.

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
| Python | Literal FastAPI/APIRouter route paths; requests/httpx HTTP method calls; basic import aliases, local/module client instances, and unique straight-line constant bindings |
| Kubernetes YAML / JSON | Container ports in Pod, Deployment, StatefulSet, DaemonSet, Job, CronJob; Service ports, numeric/named targetPort resolution, selector-to-workload paths; Ingress host/path declarations; multi-document YAML and List resources; environment values and referenced ConfigMaps |
| JSON, YAML, TOML | URL-valued strings with configuration key paths |
| `.env*` | URL-valued assignments with line numbers |

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

Common dependency/build directories (`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`) and symbolic-link files are skipped. Supported files larger than 2 MB generate a diagnostic. `.gitignore` rules are not interpreted; use `--exclude` for additional exclusions.

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

Open `report.html` in a browser. The standalone file includes summary counts, connection paths, endpoint findings, expandable source evidence, and diagnostics. Search and direction filters run locally. No CDN, external assets, or endpoint requests are used. Source text is HTML-escaped, and the report restricts scripts with a content security policy. Without JavaScript, all records remain visible. Reports can contain internal identifiers and should be reviewed before sharing.

## Architecture

```text
Project files
    → Python AST / safe YAML / JSON / TOML / dotenv readers
    → Common finding model + source evidence
    → Deterministic ordering and exact deduplication
    → Table / JSON / CSV / HTML
```

## Limits and roadmap

This is an initial, deliberately bounded implementation. It does not perform whole-program data-flow analysis. Only unique straight-line assignments are resolved; reassigned names, conditional bindings, and parameter shadowing remain unresolved. String interpolation, environment defaults/expansion, wrapper functions, class methods, lambdas, comprehensions, router mounting/prefix composition, and cross-file Python references are unsupported. Source analysis does not model execution order across function calls or dynamic monkey-patching. Environment declarations are searched across the scan root, so scan each application separately or use exclusions to limit candidates.

Kubernetes ports indicate declarations, not actual listeners. Ingress TLS, effective reachability, NetworkPolicy, Secret resolution and deployment/environment selection are not modeled. ConfigMap references are supported only for container environment declarations. Generic URL findings may overlap with source findings. Parser failures preserve other scan results.

Planned next steps:

- [x] Bounded constant and environment-reference resolution with provenance
- [x] Kubernetes container environment and ConfigMap references
- [x] Kubernetes Service → workload correlation and Ingress paths
- [x] Offline HTML reports with search and evidence
- [ ] Helm rendered-manifest workflow and explicit values selection
- [ ] Terraform resource/reference analysis without applying infrastructure
- [ ] Additional language/framework analyzers and database/broker clients
- [x] Standalone releases for Linux, macOS, and Windows
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
