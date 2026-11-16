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

## 빠른 시작

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

예제는 총 7개 결과를 생성합니다. `/health`, `/weather` Inbound 경로, 외부 HTTP 호출, 미확정 호출, 설정 URL 후보, 컨테이너 8000 포트, Service 80 포트가 포함됩니다. 각 항목은 독립적인 결과이며, 초기 버전에서는 설정 URL을 동적 호출과 자동으로 연결하지 않습니다.

## 현재 지원 범위

| 대상 | 추출 정보 |
| --- | --- |
| Python | FastAPI/APIRouter의 문자열 경로, requests/httpx HTTP 메서드 호출, 기본 import 별칭과 모듈 수준 클라이언트 인스턴스 |
| Kubernetes YAML | Pod·Deployment·StatefulSet·DaemonSet·Job·CronJob의 컨테이너 포트, Service 포트와 targetPort 참조, Ingress 호스트·경로, 다중 문서 YAML과 List |
| JSON·YAML·TOML | URL 문자열과 설정 키 경로 |
| `.env*` | URL 형태의 할당 값과 줄 번호 |

분석 대상 코드를 import하거나 실행하지 않으며, YAML은 안전한 로더로 읽습니다. 발견한 주소로 접속하거나 현재 프로세스의 환경변수로 값을 보완하지 않습니다. Helm·Terraform 명령도 실행하지 않습니다.

## 사용법

```bash
netspector --version
netspector scan ./project
netspector scan ./project --direction outbound
netspector scan ./project --format json
netspector scan ./project --format csv --output connections.csv
netspector scan ./project --exclude 'tests/*' --exclude '**/fixtures/**'
```

| 옵션 | 설명 |
| --- | --- |
| `--format` | `table` 기본값, `json`, `csv` |
| `--direction` | `inbound`, `outbound`, `unknown`; 생략하면 전체 |
| `--exclude` | 상대 경로 glob, 여러 번 지정 가능; 셸에서는 따옴표 사용 |
| `--output` | 표준 출력 대신 파일로 저장 |

종료 코드: **0** 정상 완료, **1** 일부 파일 분석 실패·건너뜀, **2** 잘못된 인자·경로 또는 출력 실패입니다. 진단 정보는 stderr와 JSON에 포함되며 CSV에는 분석 결과만 포함됩니다.

`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build` 디렉터리와 심볼릭 링크 파일을 제외합니다. 지원 파일 중 2 MB 초과 파일은 진단과 함께 건너뜁니다. `.gitignore`는 분석 제외 규칙으로 사용하지 않으므로 추가 제외는 `--exclude`로 지정합니다.

## 결과 읽기

| 상태 | 의미 |
| --- | --- |
| `confirmed` | 인식한 HTTP 호출에서 문자열 대상 확인. 실제 실행 확인은 아님 |
| `declared` | Inbound 경로·포트·노출 선언 확인 |
| `candidate` | 설정에 URL이 있으나 사용 여부와 방향 미확인 |
| `unresolved` | 호출·경로를 인식했으나 대상이 동적 값 |

결과 필드는 `direction`, `kind`, `target`, `protocol`, `port`, `status`, `file`, `line`, `reference`입니다. JSON은 `schema_version: "1"`, `findings`, `diagnostics`로 구성됩니다. 파일 경로는 스캔 루트 기준 상대 경로입니다. 구조화된 설정은 가능한 경우 키 경로를 제공하며 줄 번호는 `null`입니다. 결과를 정렬하고 완전히 동일한 항목을 제거합니다.

URL의 인증 정보·쿼리·fragment는 출력에서 제거하고 CSV 수식 시작 문자를 이스케이프합니다. 내부 호스트명·URL 경로·앱 식별자는 남을 수 있으므로 공유 전 결과를 확인하세요.

## 구조

```text
프로젝트 파일
    → Python AST / 안전한 YAML / JSON / TOML / dotenv 분석
    → 공통 결과 모델과 근거 위치
    → 정렬과 완전 중복 제거
    → 표 / JSON / CSV
```

## 제한 사항과 로드맵

초기 버전은 전체 프로그램의 데이터 흐름을 분석하지 않습니다. 변수, 문자열 조합, 래퍼 함수, 함수 내부 클라이언트, 라우터 prefix·mount, 파일 간 참조는 해석하지 않습니다. 인식한 호출의 직접 환경변수 조회는 가능한 경우 변수 이름을 보존합니다. import나 클라이언트 이름을 재정의하면 단순 이름 매칭으로 오탐할 수 있습니다.

Kubernetes 포트는 선언이며 실제 수신 상태를 의미하지 않습니다. Ingress TLS, 실제 도달 가능성, NetworkPolicy, Service와 워크로드 연결, ConfigMap·Secret 참조, 환경별 우선순위는 아직 분석하지 않습니다. 설정 URL 후보와 다른 결과가 중복될 수 있으며, 일부 파싱 실패 시 나머지 분석 결과는 유지합니다.

다음 단계:

- [ ] 범위를 고려한 상수·환경변수 참조 해석과 값의 출처 추적
- [ ] Kubernetes Service와 워크로드 연결, ConfigMap 참조
- [ ] Helm 렌더링 결과 및 명시적인 values 선택 지원
- [ ] 인프라 적용 없이 Terraform 리소스·참조 분석
- [ ] 추가 언어·프레임워크 및 DB·메시지 브로커 클라이언트 지원
- [ ] 배포 패키지와 실제 프로젝트 기반 회귀 테스트 확대

원본 Helm 템플릿과 Terraform `.tf`는 미지원입니다. 렌더링된 Helm YAML은 Kubernetes YAML로 분석할 수 있습니다.

## 개발 및 기여

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m netspector scan examples/demo --format json
```

테스트는 소스 추출, 민감 URL 제거, 동적 참조, 설정 후보, Kubernetes 포트, 제외, 부분 실패, 출력 재현성, CLI 형식을 검증합니다. CI는 Python 3.11–3.13에서 실행합니다.

분석기 추가 시 작은 입력 예제, 기대 결과, 오탐 방지 사례를 함께 제공해 주세요. 문서의 지원 범위는 테스트로 확인한 동작과 일치시켜 주세요.

## 라이선스

[MIT](LICENSE) © 2026 uknow.
