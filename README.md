# kube-agent

오프라인 온프레미스 K8s 클러스터 및 개발자 로컬 워크스테이션에서 동작하는 **CLI 기반 AI 에이전트 (Team Edition)**.
터미널에서 자연어로 요청하면 Kubernetes 리소스 관리, Prometheus 메트릭 조회, Loki 분산 로그 분석, Gitea 저장소 작업, Helm 차트 배포를 자동으로 수행합니다.

## 핵심 기능

- **Kubernetes (13개 도구)**:
  - Pod/Deployment/Service/ConfigMap/Secret 조회·수정·롤링 재시작·스케일링
  - **원클릭 클러스터 정밀 진단 (`k8s_diagnose_cluster`)**: CrashLoopBackOff, OOMKilled(exit code 137), ImagePullBackOff, Evicted, Pending Pod 및 Warning 이벤트를 자동 추적·분석
- **관측성 연동 (Observability - 2개 도구)**:
  - **Prometheus (`prom_query`)**: PromQL 인스턴트 및 범위 메트릭 조회 (CPU, Memory, Latency, Error Rate 등)
  - **Grafana Loki (`loki_query`)**: LogQL 분산 로그 스트림 집계 및 필터링 검색
- **Gitea & Git (12개 도구)**: 저장소 관리, 브랜치 조작, Git clone/commit/push, 웹훅 설정
- **Helm (4개 도구)**: 차트 린트(`lint`), 템플릿 검증(`template`), 업그레이드/설치(`upgrade`), 롤백(`rollback`) (최신 Helm 4+ 지원)
- **파일 (3개 도구)**: 클론한 저장소의 파일 읽기/쓰기 및 샌드박스 보안 격리
- **팀 협업 및 로컬 실행 최적화**:
  - `kube-agent.yaml` 팀 공용 설정 파일 지원 (CLI flag > 환경변수 > YAML 설정 파일 > 기본값)
  - 로컬 실행 시 `~/.kube/config` 활성 Context 및 Namespace 자동 감지
- **안전 가드레일 & Read-Only 모드**:
  - 파괴적 명령(저장소 삭제, `scale 0` 등) 실행 전 대화형 사용자 승인
  - `--read-only` 플래그로 모든 상태 변경 작업을 원천 차단하여 조회/진단 전용 모드로 안전하게 사용 가능
- **자율 실행 & 서킷 브레이커**: 목표 완결까지 도구 체이닝 및 반복 실패 조기 차단
- **실시간 스트리밍 & 컨텍스트 압축**: Rich 실시간 토큰 렌더링 및 온프레미스 소형 LLM 컨텍스트 보존

## 빠른 시작

### 로컬 머신에서 바로 실행
```bash
# 1. 패키지 설치
pip install -e .

# 2. 팀 설정 템플릿 복사 (또는 ~/.kube-agent.yaml)
cp kube-agent.example.yaml kube-agent.yaml

# 3. 실행 (현재 ~/.kube/config의 활성 네임스페이스 자동 감지)
kube-agent

# 읽기 전용 모드로 안전하게 진단만 실행
kube-agent --read-only
```

### 클러스터 내부 Pod 실행
```bash
# 1. 이미지 빌드 (최신 Helm 4 및 kubectl 자동 포함)
docker build -t kube-agent:0.2.0 .

# 2. Helm 배포
helm upgrade --install kube-agent ./charts/kube-agent \
  -n kube-agent --create-namespace \
  -f kube-agent/helm/kube-agent-values.yaml

# 3. Pod 접속 후 실행
kubectl exec -it -n kube-agent deploy/kube-agent -- kube-agent
```

## 사용 예시

```
You: 클러스터에 문제 있는 파드 있나 진단해줘
Agent: (k8s_diagnose_cluster 실행 후)
  CrashLoopBackOff 상태인 payment-api 파드를 발견했습니다.
  직전 종료 코드는 137(OOMKilled)이며, 메모리 한도 초과로 인해 강제 종료되었습니다.
```

```
You: payment-api 파드의 최근 5분 CPU 사용량이랑 에러 로그 보여줘
Agent: (prom_query로 container_cpu_usage_seconds_total 조회 + loki_query로 {app="payment-api"} |= "error" 조회)
```

```
You: broken-app 로그 보고 문제 찾아서 helm chart values 고쳐서 push해줘
Agent: (자동으로) 로그 확인 → 문제 진단 → 저장소 클론 → values.yaml 수정 → commit & push
```

종료: `exit` 또는 `Ctrl+D`

## 설정 옵션

`kube-agent.example.yaml`을 복사하여 `kube-agent.yaml` 또는 `~/.kube-agent.yaml`로 설정할 수 있습니다.

| 설정 키 / 환경 변수 | CLI 옵션 | 설명 | 기본값 |
|---|---|---|---|
| `llm.url` / `KUBE_AGENT_LLM_URL` | `-l`, `--llm-url` | LLM API 엔드포인트 | `http://litellm...svc:4000/v1` |
| `llm.model` / `KUBE_AGENT_LLM_MODEL` | `-m`, `--llm-model` | LLM 모델명 | `gpt-4o` |
| `kubernetes.namespace` / `KUBE_AGENT_NAMESPACE` | `-n`, `--namespace` | K8s 작업 네임스페이스 | 활성 context / default |
| `observability.prometheus_url` | `--prometheus-url` | Prometheus 서버 URL | — |
| `observability.loki_url` | `--loki-url` | Grafana Loki 서버 URL | — |
| `read_only` / `KUBE_AGENT_READ_ONLY` | `--read-only` | 읽기 전용 안전 모드 | `false` |
| `safety.mode` / `KUBE_AGENT_SAFETY_MODE` | `--safety-mode` | 안전 가드레일 모드 | `strict` |

상세 가이드: [`docs/guide.md`](docs/guide.md)
