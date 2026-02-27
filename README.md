# kube-agent

오프라인 온프레미스 K8s 클러스터에서 동작하는 **CLI 기반 AI 에이전트**.
터미널에서 자연어로 요청하면 Kubernetes 리소스 관리, Gitea 저장소 작업, 파일 편집을 자동으로 수행한다.

## 핵심 기능

- **Kubernetes**: Pod/Deployment/Service/ConfigMap 조회·수정·재시작·스케일링
- **Gitea**: 저장소 관리, Git clone/commit/push, 웹훅 설정
- **파일**: 클론한 저장소의 파일 읽기/쓰기 (Helm chart 수정 등)
- **자율 실행**: 복잡한 작업도 완료될 때까지 도구를 자동 호출하며 진행

## 빠른 시작

```bash
# 1. 이미지 빌드
docker build -t kube-agent:0.1.0 .

# 2. Helm 설치
cd kube-agent/helm
helm upgrade --install kube-agent ./charts/kube-agent \
  -n kube-agent --create-namespace \
  -f kube-agent/helm/kube-agent-values.yaml

# 3. Pod 접속 후 실행
kubectl exec -it -n kube-agent deploy/kube-agent -- kube-agent
```

## 사용 예시

```
You: broken-app 로그 보고 문제 찾아서 helm chart 고쳐서 push해줘

Agent: (자동으로) 로그 확인 → 문제 진단 → 저장소 클론 → 파일 수정 → commit & push
```

```
You: 현재 네임스페이스 Pod 목록 보여줘
You: my-app 디플로이먼트 3개로 스케일해줘
You: gitea에 새 저장소 만들어줘
```

종료: `exit` 또는 `Ctrl+D`

## 설정

| 환경 변수 | 설명 | 기본값 |
|-----------|------|--------|
| `KUBE_AGENT_LLM_URL` | LLM API 엔드포인트 | `http://litellm...svc:4000/v1` |
| `KUBE_AGENT_LLM_MODEL` | 모델명 | `gpt-4o` |
| `KUBE_AGENT_GITEA_URL` | Gitea 서버 URL | — |
| `KUBE_AGENT_NAMESPACE` | K8s 네임스페이스 | Pod 내 자동 감지 |

상세 가이드: [`docs/guide.md`](docs/guide.md)
