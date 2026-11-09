# kube-agent 2.0 (Team & Open-Source Edition)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-1.28+-326ce5.svg)](https://kubernetes.io/)
[![Helm 4+](https://img.shields.io/badge/helm-v4+-0f1689.svg)](https://helm.sh/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-82%20passed-brightgreen.svg)]()

> 🤖 **AI 에이전트 자동 셋업 프로토콜**: [`docs/agent-installation.md`](docs/agent-installation.md) \| [`AGENTS.md`](AGENTS.md)  
> 📖 **상세 운영 및 아키텍처 가이드**: [`docs/guide.md`](docs/guide.md)

오프라인 온프레미스 K8s 클러스터 및 개발자 워크스테이션 환경에서 동작하는 **자율형 인프라 AI 에이전트**.  
Kubernetes 리소스 제어, Prometheus 메트릭 질의, Grafana Loki 분산 로그 분석, Git/Gitea 조작, Helm 4 차트 배포를 자연어로 통합 관리합니다.

---

## 3가지 핵심 운영 모드 (Operational Modes)

```
                            [ 외부 시스템 / Alertmanager / CI/CD ]
                                         │  (HTTP / Webhook)
                                         ▼
                                ┌─────────────────┐
                                │   Mode 2. SERVE │ ──> REST API / Webhook Daemon
                                └─────────────────┘
                                         │
┌────────────────────────┐      ┌────────▼────────┐      ┌─────────────────────────┐
│   Mode 1. CHAT (CLI)   │ <──> │   kube-agent    │ <──> │      Mode 3. BATCH      │
│  터미널 대화형 자율 셸   │      │   Core Engine   │      │ AI 토큰 절감형 헬스체크   │
└────────────────────────┘      └────────┬────────┘      │  + 지속적 리포트 & 자동복구│
                                         │               └─────────────────────────┘
                                         ▼
            ┌───────────────────┬───────────────────┬───────────────────┐
            │   Kubernetes API  │  Observability    │    Git / Helm     │
            │ (13 Tools + 진단) │ (Prometheus/Loki) │ (16 Tools / v4+)  │
            └───────────────────┴───────────────────┴───────────────────┘
```

| 모드 | 실행 명령어 | 주요 용도 | AI 토큰 비용 |
|:---|:---|:---|:---|
| **1. 대화형 인터랙티브 챗** | `kube-agent` | 터미널에서 엔지니어가 실시간으로 인프라 진단 및 제어 | 대화량에 비례 |
| **2. 실시간 서버 & 웹훅** | `kube-agent serve` | 사내 웹 솔루션, 챗봇, Alertmanager 웹훅 실시간 수신 | 요청별 처리 |
| **3. 토큰 절감형 배치 모드** | `kube-agent batch` | 주기적 클러스터 헬스체크, 리포트 발행 및 자동 복구 | **정상 시 0원 ($0.00)** / 장애 시에만 호출 |

---

## 주요 기능 (Features)

- **Kubernetes 자율 운영 (13개 도구)**:
  - Pod/Deployment/Service/ConfigMap/Secret 관리, 롤링 재시작 및 스케일링
  - **원클릭 클러스터 정밀 진단 (`k8s_diagnose_cluster`)**: `CrashLoopBackOff`, `OOMKilled` (종료코드 137), `ImagePullBackOff`, `Pending` 파드를 자동 탐지하고 K8s Warning 이벤트를 즉시 연계 분석
- **관측성(Observability) 연동 (2개 도구)**:
  - **Prometheus (`prom_query`)**: PromQL 인스턴트 및 범위 쿼리로 CPU/메모리/네트워크/레이턴시 측정
  - **Grafana Loki (`loki_query`)**: LogQL 분산 로그 스트림 필터링 검색
- **GitOps & Helm 4+ (16개 도구)**:
  - Gitea REST API 및 Git CLI 연동 (clone, branch, commit, push, webhook)
  - 최신 **Helm 4+** 바이너리 지원 (`lint`, `template`, `upgrade --install`, `rollback`)
- **AI 토큰 비용 최적화 엔진 (Zero-Token Pre-flight)**:
  - 배치 모드 실행 시 룰 기반 사전 검사를 먼저 수행하여 **정상 클러스터에서는 LLM 호출을 전면 생략(비용 $0.00)**
  - 장애가 발생한 경우에만 선별적으로 LLM을 호출하여 근본 원인 분석(RCA) 및 복구 리포트 작성
- **안전 가드레일 & 읽기 전용 모드 (`--read-only`)**:
  - 파괴적 작업(리포지토리 삭제, `scale 0` 등) 실행 전 대화형 확인
  - `--read-only` 플래그로 상태 변경 도구를 원천 차단하여 순수 조회/진단 모드로 안전 실행
- **팀 공용 설정 파일 (`kube-agent.yaml`)**:
  - 로컬 실행 시 `~/.kube/config`의 활성 Context & Namespace 자동 감지
  - 우선순위: **CLI 플래그 > 환경 변수 > `kube-agent.yaml` > 기본값**

---

## 빠른 시작 (Quick Start)

### 로컬 환경 설치
```bash
# 1. 패키지 설치
pip install -e .

# 2. 팀 공용 설정 파일 생성 (또는 ~/.kube-agent.yaml)
cp kube-agent.example.yaml kube-agent.yaml
```

---

### 모드 1. 대화형 인터랙티브 챗 (CLI Mode)

```bash
# 기본 실행 (현재 kubeconfig 활성 네임스페이스 자동 감지)
kube-agent

# 안전한 읽기 전용 진단 모드로 실행
kube-agent --read-only
```

**대화 예시:**
```text
You: 클러스터에 문제 있는 파드 있나 진단해줘
Agent: (k8s_diagnose_cluster 실행)
  [1] Pod: payment-api-79b8f6c4d-x2m9q (Phase: Running)
      - 컨테이너 'app' 직전 비정상 종료: 종료 코드 137 (OOMKilled)
      - 컨테이너 'app' 대기 중 (CrashLoopBackOff): back-off 5m restarting failed container
      - 관련 경고 이벤트: [BackOff] Back-off restarting failed container

You: payment-api 파드의 최근 5분 메모리 사용량이랑 에러 로그 조회해줘
Agent: (prom_query로 container_memory_working_set_bytes 조회 + loki_query로 에러 로그 취합)
```

---

### 모드 2. 실시간 서버 & 웹훅 (Server / Webhook Mode)

솔루션이나 웹 시스템, Alertmanager에서 `kube-agent`를 백그라운드 데몬으로 띄워놓고 HTTP API로 호출합니다.

```bash
# 서버 구동 (기본 포트: 8080)
kube-agent serve --port 8080
```

#### API 엔드포인트 목록
- `GET  /healthz` : 서버 헬스체크 및 연결 정보 조회
- `POST /api/v1/chat` : 자연어 질의 및 자율 작업 실행
- `POST /api/v1/diagnose` : 원클릭 클러스터 정밀 진단
- `POST /api/v1/webhook` : Prometheus Alertmanager / Grafana Webhook 수신 및 자동 원인 분석

#### cURL 호출 예제
```bash
# 1. 서버 헬스체크
curl http://localhost:8080/healthz

# 2. 실시간 에이전트 질의
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "prod 네임스페이스 파드 목록과 Warning 이벤트 요약해줘"}'

# 3. 원클릭 정밀 진단
curl -X POST http://localhost:8080/api/v1/diagnose \
  -H "Content-Type: application/json" \
  -d '{"namespace": "default"}'
```

#### Prometheus Alertmanager 연동 예시
Alertmanager의 `alertmanager.yaml`에 Webhook 수신기로 등록하면, 경보 발생 시 에이전트가 즉각 장애 원인을 분석합니다:
```yaml
receivers:
  - name: "kube-agent-webhook"
    webhook_configs:
      - url: "http://kube-agent.kube-agent.svc.cluster.local:8080/api/v1/webhook"
        send_resolved: false
```

---

### 모드 3. AI 토큰 절감형 배치 모드 (Batch Mode)

AI 토큰 비용을 획기적으로 절감하면서 정기적으로 클러스터 헬스 리포트를 생성하고, 장애 발생 시 자동으로 복구합니다.

```bash
# 1회성 점검 실행 (CronJob 적합, 정상 시 AI 비용 0원)
kube-agent batch --report-dir ./reports

# 장애 발견 시 자율 복구(auto-fix)까지 허용하여 실행
kube-agent batch --report-dir ./reports --auto-fix

# 데몬 모드로 주기적 실행 (예: 5분마다)
kube-agent batch --interval 300 --report-dir ./reports --auto-fix
```

#### K8s CronJob 배포 매니페스트 예시
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: kube-agent-health-check
  namespace: kube-agent
spec:
  schedule: "*/10 * * * *"  # 10분마다 실행
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: kube-agent
          containers:
            - name: checker
              image: docker.io/srrain98/kube-agent:0.2.0
              command: ["kube-agent", "batch", "--report-dir", "/reports", "--auto-fix"]
              volumeMounts:
                - name: report-volume
                  mountPath: /reports
          restartPolicy: OnFailure
          volumes:
            - name: report-volume
              persistentVolumeClaim:
                claimName: kube-agent-reports-pvc
```

---

## 설정 레퍼런스 (`kube-agent.yaml`)

`kube-agent.example.yaml`을 복사하여 간편하게 환경을 구성할 수 있습니다:

```yaml
llm:
  url: "http://litellm.litellm.svc.cluster.local:4000/v1"
  model: "gpt-4o"
  api_key: ""

kubernetes:
  namespace: ""  # 비워두면 ~/.kube/config 활성 네임스페이스 자동 감지
  context: ""

observability:
  prometheus_url: "http://prometheus-k8s.monitoring.svc.cluster.local:9090"
  loki_url: "http://loki-gateway.logging.svc.cluster.local:3100"

safety:
  mode: "strict" # strict | permissive | disabled | read_only

read_only: false
verbose: false
```

---

## 내장 도구 목록 (총 34개)

| 분류 | 도구명 | 설명 |
|:---|:---|:---|
| **Kubernetes (13)** | `k8s_list_pods`, `k8s_get_pod`, `k8s_get_pod_logs`, `k8s_delete_pod` | Pod 조회, 상세, 로그 및 삭제 |
| | `k8s_list_deployments`, `k8s_get_deployment`, `k8s_restart_deployment`, `k8s_scale_deployment` | 디플로이먼트 관리, 롤링 재시작, 스케일링 |
| | `k8s_list_services`, `k8s_list_configmaps`, `k8s_get_configmap`, `k8s_list_secrets`, `k8s_get_events` | Service, ConfigMap, Secret, 이벤트 조회 |
| | **`k8s_diagnose_cluster`** | **CrashLoop, OOMKilled, ImagePull, Pending 종합 장애 진단** |
| **관측성 (2)** | **`prom_query`** | **Prometheus PromQL 메트릭 쿼리 실행** |
| | **`loki_query`** | **Grafana Loki LogQL 분산 로그 쿼리 실행** |
| **Helm 4+ (4)** | `helm_lint`, `helm_template`, `helm_upgrade`, `helm_rollback` | 차트 린트, 템플릿 렌더링, 설치/업그레이드, 롤백 |
| **Gitea / Git (12)** | `gitea_list_repos`, `gitea_get_repo`, `gitea_create_repo`, `gitea_delete_repo` | 저장소 관리 |
| | `gitea_list_branches`, `gitea_list_users`, `gitea_create_webhook`, `gitea_list_webhooks` | 브랜치, 유저, 웹훅 설정 |
| | `gitea_clone_repo`, `gitea_git_pull`, `gitea_git_status`, `gitea_commit_and_push` | Git 워크플로우 조작 |
| **파일 샌드박스 (3)** | `file_list`, `file_read`, `file_write` | 격리된 워크스페이스 내 파일 I/O |

---

## 라이선스

Apache License 2.0. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
상세한 운영 가이드 및 아키텍처 문서는 [`docs/guide.md`](docs/guide.md)에서 확인하실 수 있습니다.
