# kube-agent 가이드

## 1. 개요

kube-agent는 오프라인 온프레미스 환경에서 Kubernetes 클러스터와 Gitea 저장소를 관리하기 위한 CLI 기반 AI 에이전트다. Claude Code처럼 터미널에서 자연어로 대화하면서 인프라 작업을 수행할 수 있다.

외부 인터넷 없이 클러스터 내부에서 동작하도록 설계되었으며, OpenAI 호환 API를 제공하는 vLLM 또는 LiteLLM 서비스와 통신한다. 사용자는 Pod에 접속해 `kube-agent` 명령을 실행하고, 자연어로 요청하면 에이전트가 적절한 도구를 선택해 실행한다.

### 주요 기능

- Kubernetes 리소스 조회 및 관리 (Pod, Deployment, Service, ConfigMap, Secret, Event)
- Gitea 저장소 관리 (저장소 생성/삭제, 브랜치 조회, 웹훅 설정, Git 작업)
- 총 27개 도구 내장 (Kubernetes 12개 + Gitea 12개 + 파일 3개)
- Rich 터미널 UI로 가독성 높은 출력
- 클러스터 내 ServiceAccount를 통한 인증 (kubeconfig 불필요)
- 환경 변수 또는 CLI 인자로 유연한 설정
- 자율 실행 모드: 복잡한 작업도 완료될 때까지 자동으로 도구를 호출하며 진행

---

## 2. 아키텍처

### 컴포넌트 다이어그램

```
사용자
  |
  | (터미널 입력)
  v
CLI (Rich / prompt_toolkit)
  |
  | (자연어 메시지)
  v
Agent Loop  <------>  LLM (OpenAI 호환 API: vLLM / LiteLLM)
  |
  |---> K8s API (ServiceAccount 인증, 네임스페이스 스코프)
  |
  '---> Gitea API (REST API + Git CLI, 토큰 인증)
```

에이전트 루프는 사용자 메시지를 LLM에 전달하고, LLM이 도구 호출을 요청하면 해당 도구를 실행한 뒤 결과를 다시 LLM에 전달한다. 이 과정을 LLM이 최종 응답을 생성할 때까지 반복한다. 또한 LLM이 중간에 텍스트로만 응답하더라도 작업이 완료되지 않았다고 판단되면 자동으로 "계속 진행"을 요청하여 작업이 끝날 때까지 루프를 이어간다 (자율 실행 모드).

### 파일 구조

```
kube-agent/
├── pyproject.toml          # 프로젝트 메타데이터, 의존성
├── Dockerfile              # 멀티스테이지 빌드
└── src/kube_agent/
    ├── __init__.py
    ├── main.py             # Click CLI 엔트리포인트
    ├── config.py           # 환경변수/CLI 인자 설정
    ├── agent.py            # LLM <-> Tool 루프 + 자율 실행
    ├── llm.py              # AsyncOpenAI 클라이언트
    ├── cli.py              # Rich 터미널 UI
    ├── tools.py            # 27개 도구 정의 + 디스패처
    ├── kubernetes_ops.py   # K8s 12개 작업
    ├── gitea_ops.py        # Gitea 12개 작업
    └── file_ops.py         # 파일 3개 작업 (list, read, write)
```

각 모듈의 역할:

- `main.py`: Click 프레임워크로 CLI 인자를 파싱하고 에이전트를 초기화한다.
- `config.py`: CLI 인자와 환경 변수를 통합해 설정 객체를 생성한다.
- `agent.py`: LLM과의 대화 루프를 관리하고 도구 호출을 조율한다. 자율 실행 모드에서는 LLM이 텍스트로 응답해도 작업 완료 여부를 판단해 자동 계속 진행한다.
- `llm.py`: AsyncOpenAI 클라이언트를 래핑해 LLM API 통신을 담당한다.
- `cli.py`: Rich 라이브러리를 사용해 터미널 출력을 렌더링한다.
- `tools.py`: 27개 도구의 스키마를 정의하고 실제 함수로 디스패치한다.
- `kubernetes_ops.py`: kubernetes Python 클라이언트를 사용해 K8s API를 호출한다.
- `gitea_ops.py`: httpx로 Gitea REST API를 호출하고 subprocess로 Git CLI를 실행한다.
- `file_ops.py`: 로컬 파일 목록 조회, 읽기, 쓰기를 지원한다. 보안을 위해 `/tmp`와 `/home/agent` 디렉토리만 접근 가능하다.

---

## 3. 빌드 방법

### Docker 이미지 빌드

```bash
cd kube-agent
docker build -t kube-agent:0.1.0 .
```

### Dockerfile 구조

Dockerfile은 멀티스테이지 빌드를 사용한다.

- 베이스 이미지: `python:3.11-slim`
- 빌드 스테이지에서 의존성을 설치하고, 런타임 스테이지에서 필요한 파일만 복사한다.
- `kubectl`, `git` 바이너리를 설치해 Kubernetes 조작 및 Git 작업에 활용한다. ArgoCD와 연동하는 GitOps 워크플로우를 지원한다.
- 보안을 위해 UID 1000의 non-root 사용자로 실행한다.

### Docker Hub 푸시 (프로덕션)

빌드한 이미지를 Docker Hub 레지스트리에 푸시한다.

```bash
docker tag kube-agent:0.1.0 docker.io/srrain98/kube-agent:0.1.0
docker push docker.io/srrain98/kube-agent:0.1.0
```

---

## 4. 배포 방법

### 4.1. 사전 요구사항

- Kubernetes 1.24 이상
- Helm 3.x
- Docker Desktop (로컬 테스트) 또는 온프레미스 클러스터
- 클러스터 내 LLM 서비스 (LiteLLM 또는 vLLM) — OpenAI 호환 API 엔드포인트 필수

### 4.2. Helm 차트 구조

Helm 차트 경로: `helm/`

차트를 설치하면 다음 리소스가 생성된다.

- `ServiceAccount`: Pod가 K8s API에 인증하는 데 사용
- `Role`: 네임스페이스 스코프 RBAC 권한 정의
- `RoleBinding`: ServiceAccount에 Role을 바인딩
- `Deployment`: kube-agent Pod를 관리

kube-agent는 CLI 도구이므로 Service나 Ingress는 생성하지 않는다.

### 4.3. Values 설정 설명

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `specs.kube-agent.enabled` | `true` | 배포 활성화 |
| `specs.kube-agent.image.repository` | `docker.io/srrain98/kube-agent` | 이미지 저장소 |
| `specs.kube-agent.image.tag` | `"0.1.0"` | 이미지 태그 |
| `specs.kube-agent.image.pullPolicy` | `IfNotPresent` | 이미지 풀 정책 |
| `specs.kube-agent.replicaCount` | `1` | 레플리카 수 |
| `specs.kube-agent.command` | `["kube-agent"]` | 컨테이너 실행 명령 |
| `specs.kube-agent.resources.requests.cpu` | `100m` | CPU 요청 |
| `specs.kube-agent.resources.requests.memory` | `256Mi` | 메모리 요청 |
| `specs.kube-agent.resources.limits.cpu` | `500m` | CPU 제한 |
| `specs.kube-agent.resources.limits.memory` | `512Mi` | 메모리 제한 |
| `specs.kube-agent.serviceAccount.create` | `true` | SA 생성 |
| `specs.kube-agent.serviceAccount.automount` | `true` | SA 토큰 자동 마운트 |
| `specs.kube-agent.role.enabled` | `true` | RBAC Role 생성 |
| `specs.kube-agent.securityContext.runAsUser` | `1000` | 실행 UID |
| `specs.kube-agent.securityContext.runAsNonRoot` | `true` | 루트 실행 금지 |
| `specs.kube-agent.service.enabled` | `false` | 서비스 비활성화 |

### 4.4. RBAC 권한 상세

kube-agent는 네임스페이스 스코프 Role을 사용한다. 다른 네임스페이스의 리소스에는 접근할 수 없다.

| API 그룹 | 리소스 | 권한 |
|----------|--------|------|
| `""` (core) | pods, pods/log, pods/status | get, list, watch |
| `apps` | deployments, statefulsets, replicasets | get, list, watch, update, patch |
| `apps` | deployments/scale | update, patch |
| `""` (core) | services, configmaps | get, list, watch |
| `""` (core) | secrets | list (이름만 조회, 데이터 접근 불가) |
| `""` (core) | events | get, list, watch |

Secret에 대해서는 `list` 권한만 부여해 이름 목록만 조회할 수 있다. 실제 Secret 데이터에는 접근하지 않는다.

### 4.5. 설치 명령어

**방법 1: Helm 직접 실행**

```bash
helm upgrade --install kube-agent ./helm \
  -n kube-agent --create-namespace \
  -f ./values/kube-agent-values.yaml
```

**로컬 Docker Desktop 테스트:**

```bash
# 1. 이미지 빌드
cd kube-agent
docker build -t kube-agent:0.1.0 .

# 2. Helm 설치 (로컬 이미지 사용)
helm upgrade --install kube-agent ./helm \
  -n kube-agent --create-namespace \
  -f ./values/kube-agent-values.yaml \
  --set 'specs.kube-agent.image.repository=kube-agent' \
  --set 'specs.kube-agent.image.pullPolicy=Never' \
  --set 'specs.kube-agent.command[0]=sleep' \
  --set 'specs.kube-agent.args[0]=infinity'
```

로컬 테스트 시 `sleep infinity`로 실행하면 Pod가 계속 살아있어 `kubectl exec`로 접속해 직접 `kube-agent`를 실행할 수 있다.

### 4.6. 설치 확인

```bash
# Pod 상태 확인
kubectl get pods -n kube-agent -l app.kubernetes.io/name=kube-agent

# RBAC 리소스 확인
kubectl get sa,role,rolebinding -n kube-agent -l app.kubernetes.io/name=kube-agent

# Helm 릴리스 확인
helm list -n kube-agent
```

### 4.7. 삭제

```bash
helm uninstall kube-agent -n kube-agent
```

---

## 5. 사용 방법

### 5.1. Pod에 접속하여 실행

kube-agent는 Pod 내부에서 실행하는 대화형 CLI 도구다. 먼저 Pod에 접속한 뒤 명령을 실행한다.

```bash
# Pod에 대화형 셸 접속
kubectl exec -it -n kube-agent deploy/kube-agent -- kube-agent

# LLM URL 직접 지정
kubectl exec -it -n kube-agent deploy/kube-agent -- kube-agent --llm-url http://my-llm:8000/v1
```

### 5.2. CLI 옵션 전체 목록

| 옵션 | 단축 | 환경 변수 | 기본값 | 설명 |
|------|------|-----------|--------|------|
| `--llm-url` | `-l` | `KUBE_AGENT_LLM_URL` | `http://litellm.litellm.svc.cluster.local:4000/v1` | LLM API 엔드포인트 |
| `--llm-model` | `-m` | `KUBE_AGENT_LLM_MODEL` | `gpt-4o` | LLM 모델명 |
| `--llm-api-key` | — | `KUBE_AGENT_LLM_API_KEY` | `no-key` | LLM API 키 |
| `--gitea-url` | `-g` | `KUBE_AGENT_GITEA_URL` | — | Gitea 서버 URL |
| `--gitea-token` | — | `KUBE_AGENT_GITEA_TOKEN` | — | Gitea API 토큰 |
| `--namespace` | `-n` | `KUBE_AGENT_NAMESPACE` | `default` (Pod 안에서는 자동 감지) | K8s 네임스페이스 |
| `--kube-context` | — | `KUBE_AGENT_CONTEXT` | 현재 컨텍스트 | K8s 컨텍스트 |
| `--verbose` | `-v` | — | `false` | 디버그 로깅 |
| `--version` | — | — | — | 버전 출력 |
| `--help` | `-h` | — | — | 도움말 |

설정 우선순위: CLI 인자 > 환경 변수 > 기본값

### 5.3. 대화 예시

```
-- kube-agent --
Connected to LLM: http://litellm.litellm.svc.cluster.local:4000/v1
Namespace:        kube-agent
Gitea:            http://gitea.ops.svc.cluster.local:3000

Type your message and press Enter. Ctrl+C to cancel, Ctrl+D to exit.

You: 현재 네임스페이스의 Pod 목록을 보여줘

Thinking...
Tool: k8s_list_pods
╭─ k8s_list_pods ─╮
│ NAME                              STATUS    RESTARTS  AGE     │
│ ──────────────────────────────────────────────────────────     │
│ kube-agent-7cfd9679bc-qsdmp       Running   0         5m      │
│ my-app-6b8d4f7c9d-abc12           Running   0         2h      │
╰──────────────────╯

Agent: 현재 kube-agent 네임스페이스에 2개의 Pod가 실행 중입니다...

You: my-app 디플로이먼트를 재시작해줘

Thinking...
Tool: k8s_restart_deployment
╭─ k8s_restart_deployment ─╮
│ Deployment 'my-app' 롤링 재시작을 시작했습니다.               │
╰───────────────────────────╯

Agent: my-app 디플로이먼트의 롤링 재시작을 시작했습니다. 잠시 후 Pod가 새로 생성됩니다.

You: exit
Goodbye!
```

### 5.4. 키보드 단축키

| 키 | 동작 |
|----|------|
| `Enter` | 메시지 전송 |
| `Ctrl+C` | 현재 요청 취소 |
| `Ctrl+D` | 에이전트 종료 |
| `exit`, `quit`, `bye` | 에이전트 종료 |

---

## 6. 도구 레퍼런스

### 6.1. Kubernetes 도구 (12개)

| 도구 | 설명 | 필수 인자 |
|------|------|-----------|
| `k8s_list_pods` | Pod 목록 조회 | — |
| `k8s_get_pod` | Pod 상세 정보 | `name` |
| `k8s_get_pod_logs` | Pod 로그 조회 | `name`, (선택: `container`, `tail`) |
| `k8s_list_deployments` | Deployment 목록 | — |
| `k8s_get_deployment` | Deployment 상세 | `name` |
| `k8s_restart_deployment` | 롤링 재시작 | `name` |
| `k8s_scale_deployment` | 레플리카 조정 | `name`, `replicas` |
| `k8s_list_services` | Service 목록 | — |
| `k8s_list_configmaps` | ConfigMap 목록 | — |
| `k8s_get_configmap` | ConfigMap 상세 | `name` |
| `k8s_list_secrets` | Secret 목록 (이름만) | — |
| `k8s_get_events` | 네임스페이스 이벤트 | (선택: `limit`) |

모든 K8s 도구는 에이전트가 실행 중인 네임스페이스를 기준으로 동작한다. 다른 네임스페이스의 리소스에는 접근할 수 없다.

### 6.2. Gitea 도구 (12개)

| 도구 | 설명 | 필수 인자 |
|------|------|-----------|
| `gitea_list_repos` | 저장소 목록 | — |
| `gitea_get_repo` | 저장소 상세 | `owner`, `name` |
| `gitea_create_repo` | 저장소 생성 | `name`, (선택: `description`, `private`) |
| `gitea_delete_repo` | 저장소 삭제 | `owner`, `name` |
| `gitea_list_branches` | 브랜치 목록 | `owner`, `repo` |
| `gitea_list_users` | 사용자 목록 (관리자) | — |
| `gitea_create_webhook` | 웹훅 생성 | `owner`, `repo`, `target_url`, (선택: `events`) |
| `gitea_list_webhooks` | 웹훅 목록 | `owner`, `repo` |
| `gitea_clone_repo` | Git 클론 | `repo_url`, `path` |
| `gitea_git_pull` | Git 풀 | `path` |
| `gitea_git_status` | Git 상태 | `path` |
| `gitea_commit_and_push` | 커밋 + 푸시 | `path`, `message` |

Gitea 도구를 사용하려면 `--gitea-url`과 `--gitea-token` 설정이 필요하다. 설정하지 않으면 Gitea 관련 도구 호출 시 오류가 발생한다.

### 6.3. 파일 도구 (3개)

| 도구 | 설명 | 필수 인자 |
|------|------|-----------|
| `file_list` | 디렉토리 파일 목록 조회 | `path` |
| `file_read` | 파일 내용 읽기 | `path` |
| `file_write` | 파일 내용 쓰기/생성 | `path`, `content` |

파일 도구는 보안을 위해 `/tmp`와 `/home/agent` 디렉토리만 접근 가능하다. 이 도구들은 Git으로 클론한 Helm 차트 저장소의 파일을 수정하는 데 사용된다.

### 6.4. 자율 실행 모드

kube-agent는 복잡한 작업을 완료될 때까지 자동으로 진행하는 자율 실행 모드를 지원한다.

**동작 방식:**

1. 사용자가 요청을 입력하면 LLM이 필요한 도구를 호출하며 작업을 수행한다.
2. LLM이 도구 호출 없이 텍스트로 응답하더라도, 작업이 완료되지 않았다고 판단되면 자동으로 "계속 진행"을 요청한다.
3. 작업 완료 키워드(완료, 요약, finished 등)가 포함된 긴 응답이 오면 루프를 종료한다.
4. 최대 5회까지 자동 계속 진행하며, 단일 요청당 최대 30회 도구 호출이 가능하다.

**예시 시나리오:**

```
You: broken-app 로그 확인하고 문제 찾아서 helm chart 고쳐서 push해줘

Thinking...
Tool: k8s_get_pod_logs          ← 1단계: 로그 확인
Tool: gitea_clone_repo           ← 2단계: 저장소 클론
Tool: file_read                  ← 3단계: 현재 설정 확인
Tool: file_write                 ← 4단계: configmap.yaml 생성
Tool: file_write                 ← 5단계: values.yaml 수정
Tool: gitea_commit_and_push      ← 6단계: 커밋 + 푸시

Agent: 완료되었습니다. broken-app의 로그에서 DB_HOST 환경변수 누락을 발견하여
       configmap.yaml을 생성하고 values.yaml을 수정한 후 push했습니다.
```

사용자는 하나의 요청만 입력하면 에이전트가 로그 분석부터 코드 수정, Git push까지 자동으로 수행한다.
---

## 7. 환경 변수 레퍼런스

| 환경 변수 | 설명 | 기본값 | Helm values.yaml 매핑 |
|-----------|------|--------|----------------------|
| `KUBE_AGENT_LLM_URL` | LLM API 엔드포인트 | `http://litellm.litellm.svc.cluster.local:4000/v1` | `specs.kube-agent.env[0].value` |
| `KUBE_AGENT_LLM_MODEL` | LLM 모델명 | `gpt-4o` | `specs.kube-agent.env[1].value` |
| `KUBE_AGENT_LLM_API_KEY` | LLM API 인증 키 | `no-key` | Secret `kube-agent-secrets.llm-api-key` |
| `KUBE_AGENT_GITEA_URL` | Gitea 서버 URL | — | `specs.kube-agent.env[4].value` |
| `KUBE_AGENT_GITEA_TOKEN` | Gitea API 토큰 | — | Secret `kube-agent-secrets.gitea-token` |
| `KUBE_AGENT_NAMESPACE` | K8s 네임스페이스 | `default` | Downward API `metadata.namespace` |
| `KUBE_AGENT_CONTEXT` | K8s 컨텍스트 | — | Pod 내부에서는 불필요 |

민감한 값인 `KUBE_AGENT_LLM_API_KEY`와 `KUBE_AGENT_GITEA_TOKEN`은 Kubernetes Secret `kube-agent-secrets`에 저장하고 환경 변수로 주입한다. values.yaml에 평문으로 작성하지 않는다.

Pod 내부에서는 ServiceAccount 토큰을 통해 K8s API에 인증하므로 `KUBE_AGENT_CONTEXT`를 별도로 설정할 필요가 없다. 네임스페이스는 Downward API를 통해 자동으로 주입된다.

---

## 8. 트러블슈팅

### Pod가 ImagePullBackOff 상태

Harbor 레지스트리에 접근할 수 없거나 이미지 태그가 잘못된 경우다.

```bash
# 이벤트 확인
kubectl describe pod -n kube-agent -l app.kubernetes.io/name=kube-agent
```

- Harbor URL과 이미지 태그가 values.yaml에 올바르게 설정되어 있는지 확인한다.
- 클러스터가 Harbor에 접근할 수 있는지 네트워크 정책을 확인한다.
- imagePullSecret이 필요한 경우 values.yaml에 추가한다.

### LLM 연결 실패

에이전트 시작 시 LLM에 연결하지 못하는 경우다.

```bash
# LiteLLM 서비스 확인
kubectl get svc -n litellm | grep litellm

# 클러스터 내부에서 연결 테스트
kubectl exec -it -n kube-agent deploy/kube-agent -- \
  curl http://litellm.litellm.svc.cluster.local:4000/v1/models
```

- LiteLLM 또는 vLLM 서비스가 클러스터에 배포되어 있는지 확인한다.
- `KUBE_AGENT_LLM_URL`이 올바른 서비스 DNS 이름과 포트를 가리키는지 확인한다.
- 네임스페이스 간 네트워크 정책이 트래픽을 허용하는지 확인한다.

### RBAC Forbidden 오류

K8s API 호출 시 `403 Forbidden` 오류가 발생하는 경우다.

```bash
# Role과 RoleBinding 확인
kubectl get role,rolebinding -n kube-agent -l app.kubernetes.io/name=kube-agent -o yaml

# ServiceAccount 확인
kubectl get sa -n kube-agent kube-agent -o yaml
```

- Role과 RoleBinding이 올바른 네임스페이스에 생성되었는지 확인한다.
- RoleBinding의 `subjects`가 올바른 ServiceAccount를 참조하는지 확인한다.
- `role.enabled: true`가 values.yaml에 설정되어 있는지 확인한다.

### Gitea 연결 실패

Gitea 도구 호출 시 연결 오류가 발생하는 경우다.

```bash
# Gitea 서비스 확인
kubectl get svc -n ops | grep gitea

# 연결 테스트
kubectl exec -it -n kube-agent deploy/kube-agent -- \
  curl http://gitea.ops.svc.cluster.local:3000/api/v1/version
```

- `KUBE_AGENT_GITEA_URL`이 올바른 Gitea 서버 URL을 가리키는지 확인한다.
- `KUBE_AGENT_GITEA_TOKEN`이 유효한 토큰인지 Gitea 웹 UI에서 확인한다.
- 네임스페이스 간 네트워크 정책이 Gitea 포트를 허용하는지 확인한다.

### Pod CrashLoopBackOff

kube-agent는 대화형 CLI 도구이므로 TTY 없이 실행하면 즉시 종료된다.

```bash
# 로그 확인
kubectl logs -n kube-agent deploy/kube-agent
```

- 프로덕션 환경에서는 `kubectl exec -it`로 접속해 직접 실행하는 방식을 사용한다.
- 테스트 목적으로 Pod를 계속 살려두려면 command를 `sleep infinity`로 설정한다.

```bash
helm upgrade kube-agent ./helm \
  -n kube-agent \
  --set 'specs.kube-agent.command[0]=sleep' \
  --set 'specs.kube-agent.args[0]=infinity'
```

### 로컬 테스트 시 이미지 Not Found

Docker Desktop 환경에서 로컬 빌드 이미지를 찾지 못하는 경우다.

- `imagePullPolicy: Never`를 반드시 설정해야 Docker Desktop의 로컬 이미지를 사용한다.
- `docker images | grep kube-agent`로 이미지가 로컬에 존재하는지 확인한다.
- 이미지 이름과 태그가 values.yaml의 설정과 정확히 일치하는지 확인한다.

---

## 9. 의존성

`pyproject.toml` 기준 의존성 목록이다.

| 패키지 | 최소 버전 | 용도 |
|--------|-----------|------|
| Python | 3.11 이상 | 런타임 |
| `openai` | 1.40.0 이상 | LLM API 클라이언트 (AsyncOpenAI) |
| `kubernetes` | 31.0.0 이상 | K8s API 클라이언트 |
| `httpx` | 0.27.0 이상 | Gitea REST API HTTP 클라이언트 |
| `rich` | 13.9.0 이상 | 터미널 UI 렌더링 |
| `prompt-toolkit` | 3.0.48 이상 | 대화형 입력 처리 |
| `pyyaml` | 6.0.2 이상 | YAML 파싱 |
| `click` | 8.1.7 이상 | CLI 인자 파싱 |

`openai` 패키지는 OpenAI 서비스뿐 아니라 OpenAI 호환 API를 제공하는 vLLM, LiteLLM과도 동작한다. `base_url`을 클러스터 내 LLM 서비스 주소로 설정하면 된다.

`kubernetes` 패키지는 Pod 내부에서 실행할 때 ServiceAccount 토큰을 자동으로 감지해 인증한다. 별도의 kubeconfig 파일이 필요하지 않다.
