# kube-agent: CLI-based AI agent for Kubernetes and Gitea management
# 오프라인 온프레미스 환경의 Kubernetes/Gitea/Helm 관리용 대화형 에이전트

# ---- 1단계: 빌더 이미지 ----
FROM python:3.11-slim AS builder

ARG KUBECTL_VERSION=""
ARG HELM_VERSION=""

# 빌드 도구 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# kubectl 바이너리 다운로드 (빌드 시점 최신 stable 자동 조회, amd64/arm64 지원)
RUN ARCH="$(dpkg --print-architecture)" && \
    VERSION="${KUBECTL_VERSION:-$(curl -fsSL https://dl.k8s.io/release/stable.txt)}" && \
    curl -fsSL "https://dl.k8s.io/release/${VERSION}/bin/linux/${ARCH}/kubectl" \
        -o /usr/local/bin/kubectl && \
    chmod +x /usr/local/bin/kubectl

# Helm 바이너리 다운로드 (빌드 시점 최신 Helm 4+ 자동 조회, amd64/arm64 지원)
RUN ARCH="$(dpkg --print-architecture)" && \
    VERSION="${HELM_VERSION:-$(curl -fsSL https://get.helm.sh/helm-latest-version)}" && \
    curl -fsSL "https://get.helm.sh/helm-${VERSION}-linux-${ARCH}.tar.gz" | tar -xz -C /tmp && \
    mv "/tmp/linux-${ARCH}/helm" /usr/local/bin/helm && \
    chmod +x /usr/local/bin/helm && \
    rm -rf "/tmp/linux-${ARCH}"

# Python 의존성 캐싱 레이어 분리
WORKDIR /build
COPY pyproject.toml ./

# hatchling 빌드를 위한 임시 패키지 생성 후 의존성 선설치 (src 코드 변경 시에도 pip 캐시 재사용)
RUN mkdir -p src/kube_agent && \
    touch src/kube_agent/__init__.py && \
    pip install --no-cache-dir --prefix=/install . && \
    rm -rf src

# 실제 소스 코드 복사 및 애플리케이션 설치
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps --prefix=/install .


# ---- 2단계: 경량 런타임 이미지 ----
FROM python:3.11-slim

LABEL org.opencontainers.image.title="kube-agent" \
      org.opencontainers.image.description="CLI-based AI agent for Kubernetes and Gitea management" \
      org.opencontainers.image.version="0.2.0" \
      org.opencontainers.image.source="https://github.com/allganize/helm-okds" \
      org.opencontainers.image.licenses="Apache-2.0"

# CLI 스트리밍 출력 및 UTF-8 터미널 인코딩 보장
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 런타임 필수 패키지 (Git CLI 및 SSL 인증서)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 빌더 스테이지에서 바이너리 및 Python 라이브러리 복사
COPY --from=builder /usr/local/bin/kubectl /usr/local/bin/kubectl
COPY --from=builder /usr/local/bin/helm /usr/local/bin/helm
COPY --from=builder /install /usr/local

# non-root 사용자 생성 및 작업 디렉토리 권한 설정
RUN groupadd -g 1000 agent && \
    useradd -u 1000 -g agent -m -s /bin/bash agent && \
    mkdir -p /home/agent/workspace /tmp && \
    chown -R agent:agent /home/agent

# non-root 사용자로 전환
USER 1000
WORKDIR /home/agent

# Git 자동 커밋을 위한 기본 사용자 설정
RUN git config --global user.name "kube-agent" && \
    git config --global user.email "kube-agent@cluster.local" && \
    git config --global init.defaultBranch main

ENTRYPOINT ["kube-agent"]
