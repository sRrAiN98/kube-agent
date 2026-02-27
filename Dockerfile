# kube-agent: CLI-based AI agent for Kubernetes and Gitea management
# 오프라인 온프레미스 환경의 Kubernetes/Gitea 관리용 대화형 에이전트

FROM python:3.11-slim AS builder

# 빌드 의존성 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# kubectl 설치 (stable release)
RUN ARCH="$(dpkg --print-architecture)" && \
    curl -fsSL "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}/kubectl" \
        -o /usr/local/bin/kubectl && \
    chmod +x /usr/local/bin/kubectl

# Python 패키지 빌드
WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install .

# ---- 런타임 이미지 ----
FROM python:3.11-slim

LABEL org.opencontainers.image.title="kube-agent" \
      org.opencontainers.image.description="CLI-based AI agent for Kubernetes and Gitea management" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/allganize/helm-okds" \
      org.opencontainers.image.licenses="Apache-2.0"

# 런타임 의존성
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# kubectl 복사
COPY --from=builder /usr/local/bin/kubectl /usr/local/bin/kubectl

# Python 패키지 복사
COPY --from=builder /install /usr/local

# non-root 사용자 생성
RUN groupadd -g 1000 agent && \
    useradd -u 1000 -g agent -m -s /bin/bash agent

# 작업 디렉토리
WORKDIR /home/agent
USER 1000

ENTRYPOINT ["kube-agent"]
