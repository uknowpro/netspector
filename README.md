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

## Quick start

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

The bundled demo produces seven findings, including:

```text
DIRECTION  KIND            TARGET                                  PORT  STATUS
inbound    route           /health                                 -     declared
inbound    route           /weather                                -     declared
outbound   http-client     https://weather.example.com/v1/current  443   confirmed
outbound   http-client     <dynamic>                               -     unresolved
unknown    configuration   https://notify.example.com/events       443   candidate
inbound    container-port  weather/api                             8000  declared
inbound    service         weather                                 80    declared
```

The actual table also includes a source column. These are independent findings; the initial version does not join the environment URL to the dynamic HTTP call.

## Current capabilities

| Input | Extracted information |
| --- | --- |
| Python | Literal FastAPI/APIRouter route paths; requests/httpx HTTP method calls; basic import aliases and module-level client instances |
| Kubernetes YAML | Container ports in Pod, Deployment, StatefulSet, DaemonSet, Job, CronJob; Service ports and targetPort references; Ingress host/path declarations; multi-document YAML and List resources |
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
netspector scan ./project --exclude 'tests/*' --exclude '**/fixtures/**'
```

| Option | Values / behavior |
| --- | --- |
| `--format` | `table` (default), `json`, `csv` |
| `--direction` | `inbound`, `outbound`, `unknown`; omit to show all |
| `--exclude` | Repeatable relative-path glob; quote patterns in your shell |
| `--output` | Write a report to a file instead of standard output |

Exit codes: **0** complete scan; **1** partial scan with diagnostics; **2** invalid invocation, invalid root, or output failure. Diagnostics go to stderr and are also included in JSON. CSV contains findings only.

Common dependency/build directories (`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`) and symbolic-link files are skipped. Supported files larger than 2 MB generate a diagnostic. `.gitignore` rules are not interpreted; use `--exclude` for additional exclusions.

## Understand the output

| Status | Meaning |
| --- | --- |
| `confirmed` | A literal outbound target was found in a recognized HTTP call; not proof of execution |
| `declared` | An inbound route, port, or exposure is explicitly declared |
| `candidate` | A URL exists in configuration; its use and direction are not established |
| `unresolved` | A recognized call or route has a dynamic target |

Each finding includes `direction`, `kind`, `target`, `protocol`, `port`, `status`, `file`, `line`, and `reference`. JSON wraps findings and diagnostics in a `schema_version: "1"` envelope. Paths are relative to the scanned root; structured configuration uses key references where available and `line: null`. Output is sorted and exact duplicates are removed.

URL credentials, query strings, and fragments are omitted from reported URL targets. CSV cells starting with formula markers are escaped. Reports may still contain internal hostnames, URL paths, and application identifiers; review them before sharing.

## Architecture

```text
Project files
    → Python AST / safe YAML / JSON / TOML / dotenv readers
    → Common finding model + source evidence
    → Deterministic ordering and exact deduplication
    → Table / JSON / CSV
```

## Limits and roadmap

This is an initial, deliberately bounded implementation. It does not perform whole-program data-flow analysis. Variables, string interpolation, wrapper functions, local client instances, router mounting/prefix composition, and cross-file references are not resolved. Direct environment lookups in recognized calls retain their variable name when possible. Simple name matching can misclassify shadowed imports or client names.

Kubernetes ports indicate declarations, not actual listeners. Ingress TLS, effective reachability, NetworkPolicy, service-to-workload correlation, ConfigMap/Secret resolution, and environment-specific overrides are not modeled. Generic URL findings may overlap with source findings. Parser failures preserve other scan results.

Planned next steps:

- [ ] Scoped constant and environment-reference resolution with provenance
- [ ] Kubernetes Service → workload correlation and ConfigMap references
- [ ] Helm rendered-manifest workflow and explicit values selection
- [ ] Terraform resource/reference analysis without applying infrastructure
- [ ] Additional language/framework analyzers and database/broker clients
- [ ] Packaged releases and larger real-world regression fixtures

Raw Helm templates and Terraform `.tf` files are not supported. Rendered Helm YAML can be scanned as Kubernetes YAML.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m netspector scan examples/demo --format json
```

Tests cover source extraction, redaction, dynamic references, configuration candidates, Kubernetes ports, exclusions, partial errors, deterministic output, and CLI formats. CI runs on Python 3.11–3.13.

Contributions are welcome. Include a small input fixture, expected findings, and false-positive cases when adding an analyzer. Keep claimed support aligned with tested behavior.

## License

[MIT](LICENSE) © 2026 uknow.
