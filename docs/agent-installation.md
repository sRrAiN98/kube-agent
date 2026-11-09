# kube-agent: AI 에이전트 전용 자동 설치 및 셋업 프로토콜 (Agent Installation Guide)

> **대상**: Antigravity, Claude Code, Cursor, Copilot Workspace, SWE-bench 및 CI/CD 오케스트레이터  
> **목적**: 모호함 없는 기계 가독형 단계별 설치, 결정론적 사전 검증, 원클릭 복구 및 자체 치유(Self-Healing) 제공  
> **문서 버전**: 2.0.0 (Team & Open-Source Edition)

---

## 1. 사전 진단 및 환경 요건 (Preflight Checklist)

AI 에이전트는 설치를 진행하기 전, 아래 진단 스크립트를 비대화형(Headless)으로 실행하여 사전 조건을 확인해야 합니다.

### 1.1. 런타임 요구 조건
| 구성 요소 | 최소 버전 | 검증 명령어 | 정상 응답 기준 |
|:---|:---|:---|:---|
| **Python** | `>= 3.11` | `python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"` | Exit Code `0` |
| **pip** | `>= 23.0` | `pip --version` | Exit Code `0` |
| **kubectl** | `>= 1.28` | `kubectl version --client --output=yaml` | Exit Code `0` |
| **Helm** | `>= 3.10` (Helm 4 권장) | `helm version --short` | Exit Code `0` |
| **Git** | `>= 2.30` | `git --version` | Exit Code `0` |

### 1.2. 3초 사전 진단 원라이너 (One-Liner Preflight)

```bash
# Linux / macOS / Bash
python -c "import sys; print('Python OK' if sys.version_info >= (3, 11) else sys.exit(1))" && \
kubectl version --client --output=yaml > /dev/null 2>&1 && echo "Kubectl OK" && \
helm version --short > /dev/null 2>&1 && echo "Helm OK" && \
echo "=== Preflight PASSED ==="
```

```powershell
# Windows PowerShell
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; if ($?) { Write-Host "Python OK" }
kubectl version --client --output=yaml 2>$null; if ($?) { Write-Host "Kubectl OK" }
helm version --short 2>$null; if ($?) { Write-Host "Helm OK" }
Write-Host "=== Preflight PASSED ==="
```

---

## 2. 플레이북 A: 로컬 가상환경 설치 (개발자 머신 / 에이전트 샌드박스)

가장 빠르고 표준적인 설치 방식입니다.

### 실행 절차

```bash
# 1. 저장소 루트 디렉터리로 이동
cd /path/to/kube-agent

# 2. 가상환경 생성 및 활성화 (선택 사항이나 권장)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1

# 3. 의존성 및 CLI 패키지 편집 가능(editable) 모드로 설치
pip install -e .

# 4. 개발 및 테스트 의존성 추가 설치 (테스트 검증 필요 시)
pip install -e ".[dev]"

# 5. 설치 무결성 확인 (0초 검증)
kube-agent --help > /dev/null 2>&1 && echo "kube-agent binary installed successfully!"
```

### 환경 설정 파일 배포
```bash
# 템플릿 복사 (우선순위: CLI > 환경변수 > ./kube-agent.yaml > ~/.kube-agent.yaml)
cp kube-agent.example.yaml kube-agent.yaml
```

---

## 3. 플레이북 B: 컨테이너 이미지 빌드 및 실행 (Docker / Podman)

호스트 머신에 Python 의존성을 설치하지 않고 격리된 환경에서 에이전트를 가동할 때 사용합니다.

```bash
# 1. 최신 Helm 4 및 kubectl이 동적 포함된 멀티스테이지 이미지 빌드
docker build -t kube-agent:0.2.0 .

# 2. 이미지 바이너리 설치 검증
docker run --rm kube-agent:0.2.0 --version
# 기대 출력: kube-agent, version 0.2.0

# 3. 로컬 kubeconfig를 마운트하여 읽기 전용 진단 모드로 대화형 실행
docker run -it --rm \
  -v ~/.kube:/home/agent/.kube:ro \
  -v $(pwd)/kube-agent.yaml:/home/agent/kube-agent.yaml:ro \
  kube-agent:0.2.0 --read-only
```

---

## 4. 플레이북 C: Kubernetes 클러스터 내 Helm 설치 (In-Cluster ServiceAccount)

클러스터 내부 Pod로 상주하며 인프라를 상시 모니터링하거나 실시간 서버로 구동할 때 적용합니다.

```bash
# 1. 전용 네임스페이스 멱등 생성
kubectl create namespace kube-agent --dry-run=client -o yaml | kubectl apply -f -

# 2. Helm 릴리스 배포
helm upgrade --install kube-agent ./helm \
  --namespace kube-agent \
  -f ./helm/kube-agent-values.yaml

# 3. 배포 롤아웃 대기 및 검증 (타임아웃 60초)
kubectl rollout status -n kube-agent deployment/kube-agent --timeout=60s

# 4. Pod 내부 에이전트 동작 확인
kubectl exec -it -n kube-agent deploy/kube-agent -- kube-agent --version
```

---

## 5. 3대 운영 모드별 에이전트 실행 프로토콜

AI 에이전트는 사용자의 의도나 시스템 목적에 따라 알맞은 모드를 선택하여 기동해야 합니다.

### 5.1. [모드 1] 대화형 챗 모드 (Interactive Chat)
인간 엔지니어와 대화하거나, 에이전트가 단독 디버깅 세션을 수행할 때 사용합니다.
```bash
# 기본 실행 (현재 활성 컨텍스트 및 네임스페이스 자동 감지)
kube-agent

# 상태 변경을 원천 차단하는 안전 진단 실행
kube-agent --read-only

# 특정 네임스페이스 및 LLM 지정 실행
kube-agent --namespace prod --llm-url http://litellm.local:4000/v1
```

### 5.2. [모드 2] 실시간 REST API 및 Alertmanager Webhook 데몬 (`serve`)
외부 시스템(웹 UI, 사내 챗봇, Alertmanager)과 연동할 때 백그라운드 데몬으로 실행합니다.
```bash
# 백그라운드 서버 가동 (기본 포트 8080)
kube-agent serve --host 0.0.0.0 --port 8080 &

# 헬스체크 검증 (Exit Code 0 확인)
curl -sSf http://localhost:8080/healthz

# 실시간 진단 API 요청
curl -s -X POST http://localhost:8080/api/v1/diagnose \
  -H "Content-Type: application/json" \
  -d '{"namespace": "default"}'

# 자연어 작업 지시 요청
curl -s -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "현재 네임스페이스의 Warning 이벤트를 요약해줘"}'
```

### 5.3. [모드 3] AI 비용 절감형 헬스체크 및 자동 복구 배치 (`batch`)
AI 토큰 사용량을 최소화하면서 주기적 리포트를 발행하고, 장애 발생 시에만 선별적 LLM 호출 및 자율 복구를 수행합니다.
```bash
# 1회 점검 실행 (클러스터 정상 시 AI 비용 $0.00, 이상 시 incident 리포트 생성)
kube-agent batch --report-dir ./reports

# 이상 발생 시 안전 자동 복구(파드/디플로이먼트 롤링 재시작)까지 즉시 적용
kube-agent batch --report-dir ./reports --auto-fix

# 데몬 모드로 5분(300초)마다 반복 실행
kube-agent batch --interval 300 --report-dir ./reports --auto-fix
```

---

## 6. 에이전트 자가 치유(Self-Healing) 및 트러블슈팅 매트릭스

설치 및 실행 중 에러가 발생하면 AI 에이전트는 아래 결정 트리를 확인하여 자체 복구해야 합니다.

| 에러 시그니처 / 증상 | 근본 원인 | 에이전트 자동 복구 명령어 |
|:---|:---|:---|
| `ModuleNotFoundError: No module named 'aiohttp'` | 비동기 웹 프레임워크 미설치 | `pip install aiohttp>=3.9.0` |
| `openai.OpenAIError: Missing credentials` | LLM API 키 미지정 | `export OPENAI_API_KEY="dummy-or-valid-key"` 또는 `kube-agent --llm-api-key "no-key"` |
| `Kubernetes API connection refused` (로컬) | 로컬 `~/.kube/config` 부재 또는 컨텍스트 오설정 | `kubectl config current-context` 확인 또는 `--kube-context <name>` 전달 |
| `ApiException: 403 Forbidden` (클러스터) | ServiceAccount RBAC 권한 부족 | `helm/templates/role.yaml`에 리소스 동사(get, list, watch, patch) 추가 |
| `Prometheus URL이 설정되지 않았습니다` | 모니터링 주소 미지정 | `--prometheus-url http://prometheus.monitoring:9090` 또는 `KUBE_AGENT_PROMETHEUS_URL` 환경변수 세팅 |
| `Loki URL이 설정되지 않았습니다` | 로그 수집기 주소 미지정 | `--loki-url http://loki.logging:3100` 또는 `KUBE_AGENT_LOKI_URL` 환경변수 세팅 |
| `Line too long` / `ruff` 린트 에러 | 포맷팅 규칙 위반 | `ruff check . --fix` |

---

## 7. 설치 검증 자동화 테스트 스크립트 (Verification Test)

설치 완료 후 모든 기능이 100% 정상 작동하는지 검증하기 위해 아래 테스트 스위트를 실행합니다:

```bash
# 전체 단위 및 통합 테스트 (82개 테스트) 일괄 실행
pytest -v

# 린터 정적 분석 검증
ruff check .
```

- **통과 기준**: `82 passed` 및 `All checks passed!`
- 이 테스트를 통과하면 `kube-agent`의 모든 기능(K8s, Prometheus, Loki, Helm 4, Gitea, Server, Batch)이 온전히 준비된 것입니다.
