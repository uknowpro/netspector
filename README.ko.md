<div align="center">

# netspector

**소스코드와 설정에서 애플리케이션의 네트워크 연결 정보를 발견하세요.**

배포 전에 Inbound 경로, Outbound HTTP 호출, 인프라에 선언된 포트를 확인합니다.

[![CI](https://github.com/uknowpro/netspector/actions/workflows/ci.yml/badge.svg)](https://github.com/uknowpro/netspector/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[English](README.md) · **한국어**

</div>

---

## 소개

애플리케이션의 연결 정보는 코드, 환경변수 파일, 배포 설정에 흩어져 있습니다. netspector는 이를 분석하여 근거 위치와 함께 재현 가능한 목록을 만듭니다.

의존성 검토, 선언된 노출 지점 확인, 네트워크 목록 내보내기에 활용할 수 있습니다. 정적 분석 도구이므로 결과는 코드와 설정의 선언을 의미하며, 실제 트래픽이나 연결 가능성을 보장하지 않습니다.



## 실행 파일 다운로드

**[netspector v0.3.0](https://github.com/uknowpro/netspector/releases/tag/v0.3.0)**에서 운영체제에 맞는 파일을 받아 압축을 풀어 실행하세요. Python을 별도로 설치할 필요가 없습니다.

| 운영체제 | 다운로드 | 대상 |
| --- | --- | --- |
| Linux x64 | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.3.0/netspector-0.3.0-linux-x86_64.tar.gz) | Ubuntu 22.04 이상 / glibc 2.35 이상 |
| macOS Intel | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.3.0/netspector-0.3.0-macos-x86_64.tar.gz) | macOS 15 이상 |
| macOS Apple Silicon | [tar.gz](https://github.com/uknowpro/netspector/releases/download/v0.3.0/netspector-0.3.0-macos-arm64.tar.gz) | macOS 15 이상 |
| Windows 10 x86 (32비트) | [zip](https://github.com/uknowpro/netspector/releases/download/v0.3.0/netspector-0.3.0-windows-x86.zip) | 32비트 Windows 10 호환 대상 |
| Windows 10/11 x64 | [zip](https://github.com/uknowpro/netspector/releases/download/v0.3.0/netspector-0.3.0-windows-x86_64.zip) | Windows 10/11 호환 대상 |

Linux/macOS에서는 `./netspector scan ./examples/demo`, Windows PowerShell에서는 `.\netspector.exe scan .\examples\demo`로 실행합니다.

압축 파일을 풀어 Ubuntu 22.04, macOS 15의 두 아키텍처, Windows Server 2022에서 실행 검증합니다. x86 버전은 32비트 Python으로 빌드하고 압축 전후 PE32/I386 실행 파일 헤더를 검증합니다. Windows 두 버전의 실행 검증은 Windows Server 2022에서 수행하며, x86은 WOW64로 실행합니다. 32비트 Windows 10 실기기 검증은 아직 진행하지 않았습니다. Windows 파일은 미서명이며 macOS 파일은 Developer ID 서명·공증이 없어 다운로드 보호 기능에서 사용자 승인이 필요할 수 있습니다. [릴리스 노트](docs/releases/v0.3.0.md)와 `SHA256SUMS`를 확인하세요. Linux ARM64, Alpine/musl, Windows ARM64, Linux/macOS 32비트 실행 파일은 제공하지 않습니다. 32비트 Windows에서는 `windows-x86.zip`을 선택하세요. `windows-x86_64.zip`은 64비트 Windows 전용입니다.

## 소스에서 설치

Python 3.11 이상과 pip가 필요합니다. 현재는 저장소에서 설치하며, PyPI 배포는 아직 제공하지 않습니다.

```bash
git clone https://github.com/uknowpro/netspector.git
cd netspector
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

netspector scan examples/demo
```

Windows에서는 `.venv\Scripts\activate`로 활성화합니다. 의존성 설치 후 `python -m netspector`로도 실행할 수 있습니다.

예제는 총 8개 발견 항목과 2개 연결 경로를 생성합니다. `/health`, `/weather` Inbound 경로, 외부 HTTP 호출, 미확정 호출, 설정 URL 후보, 컨테이너 8000 포트, Service 80 포트, Ingress 선언이 포함됩니다. `NOTIFY_URL` 동적 호출에는 `deployment.yaml`에서 발견한 `https://notify.example.com/events`와 출처가 후보로 연결됩니다. 실제 배포와 소스의 대응 관계가 확정된 것은 아닙니다.

## 현재 지원 범위

| 대상 | 추출 정보 |
| --- | --- |
| Java (제한된 분석) | 직접 선언한 Spring 컨트롤러 경로, 타입을 확인한 RestTemplate 호출, JDK HttpRequest URI 선언, 상수·getenv·@Value 참조 |
| Python | FastAPI/APIRouter의 문자열 경로, requests/httpx HTTP 메서드 호출, 기본 import 별칭, 지역·모듈 클라이언트 인스턴스, 단일 직선형 상수 할당 |
| Kubernetes YAML / JSON | Pod·Deployment·StatefulSet·DaemonSet·Job·CronJob의 컨테이너 포트, Service 포트와 targetPort 참조, Ingress 호스트·경로, 다중 문서 YAML과 List, 환경변수와 ConfigMap 참조 |
| JSON·YAML·TOML | URL 문자열과 설정 키 경로 |
| `.properties` | URL 값, 키·값 이스케이프, 이어진 줄 및 줄 번호 |
| `.env*` | URL 형태의 할당 값과 줄 번호 |
| `.ini` | 섹션·DEFAULT 상속, URL 값, host/port 조합 |
| `.xml` | 텍스트·속성 URL, Spring bean 속성·map 항목, web.xml servlet 매핑과 context/init 파라미터 |

분석 대상 코드를 import하거나 실행하지 않으며, YAML은 안전한 로더로 읽습니다. 발견한 주소로 접속하거나 현재 프로세스의 환경변수로 값을 보완하지 않습니다. Helm·Terraform 명령도 실행하지 않습니다.

## 사용법

```bash
netspector --version
netspector scan ./project
netspector scan ./project --direction outbound
netspector scan ./project --format json
netspector scan ./project --format csv --output connections.csv
netspector scan ./project --format html --output report.html
netspector scan ./project --exclude 'tests/*' --exclude '**/fixtures/**'
```

| 옵션 | 설명 |
| --- | --- |
| `--format` | `table` 기본값, `json`, `csv`, `html` |
| `--direction` | `inbound`, `outbound`, `unknown`; 생략하면 전체 |
| `--exclude` | 상대 경로 glob, 여러 번 지정 가능; 셸에서는 따옴표 사용 |
| `--output` | 표준 출력 대신 파일로 저장 |

종료 코드: **0** 정상 완료, **1** 일부 파일 분석 실패·건너뜀, **2** 잘못된 인자·경로 또는 출력 실패입니다. 진단 정보는 stderr·JSON·HTML에 포함되며, CSV에는 발견 항목과 연결 경로가 포함됩니다. 연결 참조를 찾지 못하면 미해결 경로로 표시하며 파싱 실패로 처리하지 않습니다.

`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`, `target`, `.gradle` 디렉터리와 심볼릭 링크 파일을 제외합니다. 지원 파일 중 2 MB 초과 파일은 진단과 함께 건너뜁니다. `.gitignore`는 분석 제외 규칙으로 사용하지 않으므로 추가 제외는 `--exclude`로 지정합니다.

## 결과 읽기

| 상태 | 의미 |
| --- | --- |
| `confirmed` | 인식한 HTTP 호출에서 문자열 대상 확인. 실제 실행 확인은 아님 |
| `declared` | Inbound 경로·포트·노출 선언 확인 |
| `candidate` | 설정 URL 또는 환경변수의 가능한 대상. 실제 배포 연결은 미확정 |
| `inferred` | 단일 직선형 Python 할당을 따라 대상 해석 |
| `unresolved` | 동적 대상 또는 연결 경로의 참조를 찾지 못함 |
| `partial` | Service가 워크로드를 선택했지만 숫자 targetPort와 일치하는 컨테이너 포트 선언이 없음 |

결과 필드는 `direction`, `kind`, `target`, `protocol`, `port`, `status`, `file`, `line`, `reference`, `evidence`, `candidates`입니다. JSON은 `schema_version: "1"`, `findings`, `connections`, `diagnostics`로 구성됩니다. 파일 경로는 스캔 루트 기준 상대 경로입니다. 구조화된 설정은 가능한 경우 키 경로를 제공하며 줄 번호는 `null`입니다. 결과를 정렬하고 완전히 동일한 항목을 제거합니다.

URL의 인증 정보·쿼리·fragment는 출력에서 제거하고 CSV 수식 시작 문자를 이스케이프합니다. 내부 호스트명·URL 경로·앱 식별자는 남을 수 있으므로 공유 전 결과를 확인하세요.

## 상수·환경변수 연결

```python
import os
import httpx

URL = os.getenv("NOTIFY_URL")
httpx.post(URL)
```

한 번만 할당된 변수를 따라가며 `evidence`에 할당 파일과 줄 번호를 남깁니다. 환경변수 참조는 스캔한 `.env*` 및 Kubernetes 컨테이너 선언에서 찾습니다. `env.value`, `env.valueFrom.configMapKeyRef`, `envFrom.configMapRef`와 prefix를 지원합니다. ConfigMap은 namespace를 구분하며, 명시적인 `env` 항목이 같은 이름의 `envFrom` 값보다 우선합니다.

일치하는 선언은 민감 정보를 제거한 URL과 출처를 `candidates`에 추가합니다. Kubernetes 후보에는 워크로드·namespace·컨테이너가 포함되며, ConfigMap 후보에는 참조한 Manifest를 `via`로 기록합니다. 후보가 하나여도 기본 대상은 `<dynamic>`, 상태는 `candidate`로 유지합니다. 같은 저장소에 있다고 실제 배포와 소스의 대응 관계가 확정되지는 않기 때문입니다. 여러 파일·워크로드·환경의 값은 임의 선택하지 않고 모두 후보로 보여줍니다. 참조되지 않은 ConfigMap이나 Secret은 환경변수 값으로 사용하지 않습니다.

JSON은 구조화된 근거와 후보를 제공하고, CSV는 배열을 JSON 문자열 셀로 저장합니다. 터미널 표 아래에는 후보 URL과 선언 파일을 표시합니다. 기존 필드는 유지하며 `schema_version`은 `1`입니다. CSV에는 `evidence`, `candidates` 열이 추가되었습니다.

## Java·Spring 지원

```bash
netspector scan ./java-project --format html --output java-report.html
netspector scan examples/java --format json
```

JDK·Maven·Gradle이나 네이티브 파서 의존성 없이 분석하므로 Windows x86 빌드에서도 사용할 수 있습니다. 주석·문자열을 구분하여 토큰과 선언 구조를 읽는 제한된 분석기이며, **Java 컴파일러나 전체 프로그램 타입 분석기는 아닙니다.**

| 패턴 | 동작 |
| --- | --- |
| 직접 선언한 `@RestController` / `@Controller` | 클래스 `@RequestMapping` 접두어와 메서드의 `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping` 경로 결합. `value`·`path` 배열 지원 |
| 타입이 명시된 `RestTemplate` 필드·매개변수·지역 변수 | `getForObject`, `postForEntity`, `exchange`, `put`, `delete` 등 HTTP 메서드 분석. 첫 인자가 URL이 아닌 오버로드는 미확정 처리 |
| JDK `HttpRequest.newBuilder(URI)` / `.newBuilder().uri(URI)` / 타입이 명시된 `HttpRequest.Builder.uri` | Outbound `http-request` **선언**으로 표시. `HttpClient.send` 실행이나 실제 트래픽을 의미하지 않음 |
| 문자열 표현식 | 리터럴, 같은 클래스의 final 필드, 직선형 단일 할당 지역 변수, 모든 값이 알려진 문자열 결합, `URI.create(String)`·`new URI(String)` |
| `System.getenv("NAME")` | 기존 dotenv·Kubernetes 환경변수 후보 연결 |
| 필드의 `@Value("${key}")` | UTF-8 `.properties`, `application*.yaml/yml/json`, `bootstrap*.yaml/yml/json`의 정확한 키와 같은 이름의 환경변수에서 URL 후보 연결 |

import 또는 완전한 패키지명이 확인된 Spring·HTTP 타입을 사용합니다. 메서드나 애너테이션 이름만 같은 사용자 클래스는 제외합니다. 설정의 이름 참조는 아래의 제한된 변수 해석을 적용하며, 프로파일 우선순위·유연한 설정 키 이름 변환·기본값은 평가하지 않습니다. 여러 설정 파일의 값은 후보로 남기며 런타임 설정을 읽지 않습니다. properties의 이어진 줄과 Unicode 등 이스케이프를 지원합니다.

아직 지원하지 않는 범위는 상속·인터페이스의 컨트롤러 매핑, 커스텀 조합 애너테이션, HTTP 메서드·파라미터·헤더 라우팅 조건, servlet context path, WebClient·RestClient·Feign·OkHttp·Apache HttpClient, DB·메시지 브로커, 파일 간 상수, 팩토리 반환 클라이언트, `var` 타입 추론, 필드 초기화의 HTTP 호출, 일반적인 빌더·데이터 흐름입니다. 람다 본문·익명/지역 클래스와 불확실한 중첩 바인딩은 건너뛰거나 미해결로 남깁니다. 텍스트 블록을 URL로 해석하지 않으며 문자열 밖의 Unicode 전처리, 전체 Java 문법 검증, 리플렉션, 생성 코드도 모델링하지 않습니다. 괄호나 리터럴이 닫히지 않으면 해당 파일의 진단을 남기고 다른 파일은 계속 분석합니다. 런타임 Bean 등록이나 메서드를 실행하지 않습니다.

API 의미는 공식 [Spring 요청 매핑](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)과 [JDK HttpRequest](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html) 문서를 참고하세요.

## 설정 변수와 host/port 조합

```bash
netspector scan examples/config --format html --output config-report.html
```

INI·XML·properties·dotenv·JSON·YAML·TOML을 공통 설정 분석기로 처리합니다.

- 스캔한 선언에서 정확한 이름의 `${NAME}`을 재귀적으로 해석하고 파일·키·줄 번호를 근거로 남깁니다. 누락·순환·지원하지 않는 치환 문법은 미해결로 남기며 셸이나 현재 프로세스 환경변수를 읽지 않습니다.
- 같은 그룹의 `host`/`hostname`과 `port`를 결합하고 `scheme`/`protocol`·`path`를 선택적으로 반영합니다. 점 또는 밑줄로 구분된 키를 지원합니다. `api.host=api.example.com`, `api.port=443`, `api.scheme=https`는 `https://api.example.com:443` 후보가 됩니다. scheme이 없으면 `api.example.com:443`으로 표시하고 프로토콜을 추측하지 않습니다.
- 파일·YAML 문서별로 구분합니다. 각 후보는 자체 선언과 **외부 파일/문서 한 개**까지만 참조하므로 여러 외부 파일의 개발/운영 값을 섞지 않습니다. 일치하는 환경별 후보는 모두 남기고 우선순위나 실제 적용 여부를 추측하지 않습니다.
- 해석한 dotenv URL은 `getenv`, properties·application/bootstrap 설정 URL은 Java `@Value` 후보에 연결합니다. host/port 조합으로 존재하지 않는 URL 속성을 만들어 연결하지 않습니다.

설정 결과는 방향 `unknown`, 상태 `candidate`, 종류 `configuration` 또는 `configuration-endpoint`입니다. 잘못되거나 불완전한 조합은 `unresolved`로 남깁니다. 설정 키만으로 실제 수신·발신을 확정하지 않습니다. 중복 키를 임의 선택하지 않으며, INI는 대소문자를 구분하고 `%`를 그대로 보존하며 DEFAULT 상속과 원본 줄 번호를 지원합니다. XML은 스키마 주소를 제외하고 요소 줄 번호, Spring property의 value 속성·중첩 `<value>`·map 항목을 읽습니다. web.xml servlet 패턴은 Inbound 선언으로 표시합니다. DTD·엔티티는 확장 전에 차단하며 bean 참조·import·외부 리소스·런타임 등록 여부는 따라가지 않습니다.

제한: `${NAME:default}`, 셸 확장, INI `%()` 치환, Spring relaxed binding·프로파일 활성화, Kubernetes `$(VAR)`는 평가하지 않습니다. dotenv 따옴표는 어휘 분석 단계에서 제거하며 이후 참조 해석은 정적 후보 검색입니다. 셸 인용 규칙이나 dotenv 로딩 순서를 재현하지 않습니다. 외부 문서 두 개 이상을 거쳐야 하는 참조는 미해결입니다. 최대 16단계·8 KiB 값·값당 2,048회 참조 방문·외부 후보 문서 64개로 제한하며 크기·작업량·후보 수 초과 시 진단을 남깁니다. 순환 YAML 별칭도 거부합니다. 일반 `.conf`, Jenkinsfile, 원본 Helm 템플릿, Terraform `.tf`는 아직 전용 분석기가 필요합니다.

## Kubernetes 연결 경로

```text
Ingress/weather-public (weather.example.com/)
  → Service/weather:80
  → Deployment/weather
  → Container/api:8000
```

같은 namespace에서 Service의 모든 selector 항목과 Pod label 또는 워크로드의 **Pod 템플릿 label**을 비교합니다. namespace가 없으면 `default`로 처리하며 실제 클러스터 설정은 읽지 않습니다. Pod·Deployment·StatefulSet·DaemonSet·ReplicaSet·Job·CronJob을 지원합니다. 숫자·이름 형태의 `targetPort`와 일반 컨테이너의 포트·프로토콜을 연결합니다. `targetPort` 생략 시 Service 포트를 사용합니다. 숫자 대상의 컨테이너 포트 선언이 없으면 `partial`로 남깁니다. Kubernetes에서는 포트 선언 없이도 통신할 수 있기 때문입니다.

Ingress는 Service 포트 번호·이름과 `defaultBackend`를 지원합니다. 경로마다 순서가 있는 `nodes`, 안정적인 `id`, `status`, `reasons`, 파일·문서·설정 키의 `evidence`를 제공합니다. 여러 대상은 모두 보존하고, 동일 리소스의 중복 선언이나 여러 컨테이너 포트 일치는 후보로 표시합니다. 누락된 Service·포트·selector는 미해결 이유를 남기며, selector가 없는 Service를 전체 워크로드에 연결하지 않습니다. ExternalName은 DNS를 조회하지 않고 선언만 표시합니다.

Ingress의 리소스 backend, EndpointSlice, TLS·컨트롤러 동작, Pod 준비 상태, init container, 실제 도달 가능성은 분석하지 않습니다. Python 소스와 워크로드를 자동으로 연결하는 기능도 포함하지 않습니다.

JSON은 기존 `schema_version: "1"`을 유지하면서 `connections`를 추가합니다. CSV는 기존 열에 `record_type`(`finding` 또는 `connection`)과 JSON 형식 `connection` 열을 추가합니다. 엔드포인트만 필요한 소비자는 `record_type=finding`으로 필터링하세요. `--direction outbound`에서는 Inbound 연결 경로를 제외합니다.

설정 의미는 Kubernetes의 [Service](https://kubernetes.io/docs/concepts/services-networking/service/) 및 [Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/) 문서를 참고하세요.

## 오프라인 HTML 보고서

```bash
netspector scan ./project --format html --output report.html
```

생성된 `report.html`을 열면 프로젝트별 네트워크 그래프가 먼저 표시됩니다. 엔드포인트 목록·인프라 경로·진단은 아래에 접어두며 진단이 있으면 해당 영역을 펼칩니다. 노드나 연결을 클릭하면 포트·URL 경로·후보·원본 출처를 확인할 수 있습니다. 서버·게이트웨이·서비스·컨테이너 아이콘, 프로젝트 영역, 직각 연결선, 프로토콜·포트 라벨로 구성도를 표시합니다. 아이콘은 소스에서 발견한 논리적 역할이며 실제 물리 장비를 확인했다는 의미는 아닙니다. 확대/축소, 프로젝트 선택, 검색·방향 필터를 지원합니다. 노드를 영역 안에서 드래그하거나 포커스 후 방향키로 옮길 수 있습니다. **Reset layout**으로 자동 배치에 복귀하고 **Save SVG**로 현재 필터·배치·스타일을 포함한 그림을 저장합니다. SVG에는 펼쳐 보는 원본 목록을 포함하지 않습니다. 수동 배치는 현재 열린 페이지에서만 유지됩니다.

- **같은 호스트는 노드 하나:** DNS 대소문자·끝의 점·IDNA와 IP 표기를 정규화합니다. 프로토콜·포트·URL 경로가 달라도 호스트 노드를 추가하지 않습니다. DNS 별칭이나 다른 IP를 같은 서버라고 추측하지 않습니다. `localhost`를 포함해 동일한 호스트 표기는 보고서 전체에서 공유하므로 물리 서버의 동일성까지 의미하지는 않습니다.
- **방향별 연결 중복 제거:** 같은 출발지→도착지는 선 하나로 묶고 반대 방향은 같은 노드 사이의 별도 화살표로 나타냅니다. 포트·경로·서로 다른 출처는 연결에 보존합니다. 이미 방향이 확인된 연결의 설정 URL은 별도 선 대신 근거에 합칩니다. 설정만 확인된 관계는 화살표 없이, 후보·미해결 관계는 점선으로 표시합니다. 확정된 선언과 후보가 함께 있으면 실선을 사용하고 각 상태는 상세에 남깁니다.
- **프로젝트 구분:** 가장 가까운 `pyproject.toml`, `setup.py`, `setup.cfg`, `package.json`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `go.mod`, `Cargo.toml`, `composer.json`, `*.csproj`의 디렉터리를 기준으로 합니다. 중첩 프로젝트는 분리하고 별도 표식이 없는 파일은 스캔 루트에 묶습니다. 런타임 앱 탐지가 아닌 디렉터리 기반 구분이며 제외한 파일은 구분 기준으로 쓰지 않습니다.
- **Inbound의 의미:** 경로만 선언된 라우트는 호출자 호스트를 알 수 없으므로 앱 노드에 표시합니다. Ingress 호스트는 호출자 주소가 아니라 노출 주소입니다. Kubernetes 리소스는 namespace·워크로드를 구분하고 소스 프로젝트와 배포 리소스를 임의로 연결하지 않습니다.
- **간결한 화면과 출처 보존:** 같은 프로젝트·방향·대상·포트의 표 항목을 묶으며 원본 출처는 펼쳐 볼 수 있습니다. JSON·CSV의 원본 발견 항목은 유지합니다. JSON에는 `project.roots`를 추가하며 `schema_version`은 유지합니다. 그래프는 한 번에 최대 160개 노드를 표시하고 초과 사실을 알립니다. 프로젝트·검색 필터로 나머지를 확인할 수 있으며 전체 항목은 아래 표에도 보존합니다.

그래프에는 JavaScript가 필요하며, 비활성화해도 접힌 표와 인프라 경로를 열어 확인할 수 있습니다. `examples/network-map`에는 두 애플리케이션이 같은 호스트를 공유하는 예제가 있습니다.

모든 동작은 로컬에서 이루어지며 CDN·외부 리소스·엔드포인트 요청을 사용하지 않습니다. 소스 텍스트를 HTML 이스케이프하고 콘텐츠 보안 정책으로 스크립트를 제한합니다. JavaScript를 꺼도 접힌 목록을 펼쳐 전체 결과를 확인할 수 있습니다. 내부 식별자가 포함될 수 있으므로 공유 전에 확인하세요.

## 구조

```text
프로젝트 파일
    → Python AST / Java 토큰 / 안전한 YAML / JSON / TOML / properties / dotenv / INI / XML 분석
    → 공통 결과 모델과 근거 위치
    → 정렬과 완전 중복 제거
    → 표 / JSON / CSV / HTML
```

## 제한 사항과 로드맵

초기 버전은 전체 프로그램의 데이터 흐름을 분석하지 않습니다. Python은 단일 직선형 할당만 해석하며, 재할당·조건부 할당·매개변수에 가려진 값은 미확정으로 남깁니다. 문자열 조합, 런타임 환경변수 기본값·확장, 래퍼 함수, 클래스 메서드, 람다, comprehension, 라우터 prefix·mount, Python 파일 간 참조는 미지원입니다. 함수 호출 간 실행 순서와 동적인 객체 변경은 모델링하지 않습니다. 환경변수 후보는 스캔 루트 전체에서 찾으므로 앱별로 스캔하거나 제외 옵션으로 범위를 제한하세요.

Kubernetes 포트는 선언이며 실제 수신 상태를 의미하지 않습니다. Ingress TLS, 실제 도달 가능성, NetworkPolicy, Secret 참조와 실제 배포 환경 선택은 아직 분석하지 않습니다. ConfigMap은 컨테이너 환경변수 참조에 한해 지원합니다. 설정 URL 후보와 다른 결과가 중복될 수 있으며, 일부 파싱 실패 시 나머지 분석 결과는 유지합니다.

다음 단계:

- [x] 제한된 범위의 상수·환경변수 참조 해석과 값의 출처 추적
- [x] Kubernetes 컨테이너 환경변수와 ConfigMap 참조
- [x] Kubernetes Service와 워크로드 연결 및 Ingress 경로
- [x] 검색과 근거를 제공하는 오프라인 HTML 보고서
- [ ] Helm 렌더링 결과 및 명시적인 values 선택 지원
- [ ] 인프라 적용 없이 Terraform 리소스·참조 분석
- [x] 초기 Java·Spring 및 JDK HTTP 요청 분석
- [ ] 추가 Java 클라이언트·언어 및 DB·메시지 브로커 지원
- [x] Linux·macOS·Windows 실행 파일 배포
- [x] XML·INI 및 제한된 설정 변수·host/port 조합
- [ ] 실제 프로젝트 기반 회귀 테스트 확대

원본 Helm 템플릿과 Terraform `.tf`는 미지원입니다. 렌더링된 Helm YAML은 Kubernetes YAML로 분석할 수 있습니다.

## 개발 및 기여

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m netspector scan examples/demo --format json
```

테스트는 소스 추출, 민감 URL 제거, 동적 참조, 설정 후보, Kubernetes 포트, 제외, 부분 실패, 출력 재현성, CLI 형식을 검증합니다. CI는 Linux·macOS·Windows Server의 Python 3.11–3.13에서 실행하며, Windows x86 인터프리터 작업을 별도로 수행합니다. 태그 릴리스는 다섯 가지 실행 파일 패키지를 만들고, 소스 폴더 밖에서 압축을 풀어 한글 경로·JSON/CSV 출력·종료 코드를 검사합니다. wheel도 깨끗한 환경에 설치하여 실행합니다.

분석기 추가 시 작은 입력 예제, 기대 결과, 오탐 방지 사례를 함께 제공해 주세요. 문서의 지원 범위는 테스트로 확인한 동작과 일치시켜 주세요.

## 라이선스

[MIT](LICENSE) © 2026 uknow.
