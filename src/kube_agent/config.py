"""Configuration management for kube-agent.

환경 변수, 설정 파일(kube-agent.yaml), CLI 인자를 통해 에이전트 설정을 통합 관리합니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# 클러스터 내부 기본 LLM 엔드포인트 (LiteLLM)
_DEFAULT_LLM_URL = "http://litellm.litellm.svc.cluster.local:4000/v1"
_DEFAULT_LLM_MODEL = "gpt-4o"
_DEFAULT_NAMESPACE = "default"
_DEFAULT_MAX_MESSAGES = 80
_DEFAULT_MAX_TOOL_ITERATIONS = 30
_DEFAULT_MAX_AUTO_CONTINUE = 5
_DEFAULT_GITEA_TIMEOUT = 30.0
_DEFAULT_TOOL_RESULT_MAX_CHARS = 3000
_DEFAULT_SAFETY_MODE = "strict"


def _detect_kube_namespace(context_name: str = "") -> str:
    """Kubernetes 현재 네임스페이스를 자동 감지합니다.

    1. In-cluster 환경: ServiceAccount 마운트 네임스페이스 파일 확인
    2. 로컬 환경: kubeconfig의 현재 활성 컨텍스트에 설정된 네임스페이스 확인
    3. 실패 시: "default"
    """
    # 1. In-cluster ServiceAccount 네임스페이스 파일
    sa_ns_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if sa_ns_path.exists():
        try:
            ns = sa_ns_path.read_text().strip()
            if ns:
                return ns
        except Exception:
            pass

    # 2. 로컬 kubeconfig 활성 컨텍스트
    try:
        from kubernetes import config as k8s_config
        contexts, active = k8s_config.list_kube_config_contexts()
        target_name = context_name or (active.get("name") if active else "")
        for c in contexts:
            if c.get("name") == target_name:
                ns = c.get("context", {}).get("namespace")
                if ns:
                    return ns
    except Exception:
        pass

    return _DEFAULT_NAMESPACE


def find_config_file(explicit_path: str = "") -> Path | None:
    """팀 공용 설정 파일(kube-agent.yaml)을 탐색합니다.

    탐색 순서:
    1. CLI 지정 경로 (--config)
    2. 현재 작업 디렉토리 (./kube-agent.yaml, ./kube-agent.yml)
    3. 사용자 홈 디렉토리 (~/.kube-agent.yaml, ~/.config/kube-agent/config.yaml)
    """
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        return p if p.is_file() else None

    # 현재 작업 디렉토리
    for candidate in ("kube-agent.yaml", "kube-agent.yml", ".kube-agent.yaml"):
        p = Path(candidate).resolve()
        if p.is_file():
            return p

    # 사용자 홈 디렉토리
    home = Path.home()
    for candidate in (
        home / ".kube-agent.yaml",
        home / ".kube-agent.yml",
        home / ".config" / "kube-agent" / "config.yaml",
        home / ".config" / "kube-agent" / "config.yml",
    ):
        if candidate.is_file():
            return candidate

    return None


@dataclass
class AgentConfig:
    """에이전트 실행에 필요한 모든 설정을 관리하는 데이터클래스.

    설정 우선순위: CLI 인자 > 환경 변수 > 설정 파일(kube-agent.yaml) > 기본값
    """

    llm_base_url: str = field(default="")
    llm_api_key: str = field(default="")
    llm_model: str = field(default="")
    gitea_url: str = field(default="")
    gitea_token: str = field(default="")
    kube_namespace: str = field(default="")
    kube_context: str = field(default="")
    verbose: bool = field(default=False)
    read_only: bool = field(default=False)
    # 에이전트 루프 제한 (0 = 기본값 사용)
    max_messages: int = field(default=0)
    max_tool_iterations: int = field(default=0)
    max_auto_continue: int = field(default=0)
    # Gitea HTTP 타임아웃 (0 = 기본값 사용)
    gitea_timeout: float = field(default=0.0)
    # 도구 실행 결과 최대 표시 글자 수 (0 = 기본값 사용)
    tool_result_max_chars: int = field(default=0)
    # 안전 모드 ("strict", "permissive", "disabled", "read_only")
    safety_mode: str = field(default="")
    # 관측성 (Prometheus & Loki)
    prometheus_url: str = field(default="")
    loki_url: str = field(default="")

    @classmethod
    def from_yaml(cls, path: str | Path) -> AgentConfig:
        """YAML 설정 파일에서 설정을 로드합니다."""
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            return cls()

        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return cls()

        llm_cfg = data.get("llm", {})
        gitea_cfg = data.get("gitea", {})
        k8s_cfg = data.get("kubernetes", {})
        safety_cfg = data.get("safety", {})
        obs_cfg = data.get("observability", {})
        prom_cfg = data.get("prometheus", {})
        loki_cfg = data.get("loki", {})

        prom_url = str(prom_cfg.get("url") or obs_cfg.get("prometheus_url", "") or "")
        loki_url = str(loki_cfg.get("url") or obs_cfg.get("loki_url", "") or "")

        return cls(
            llm_base_url=str(llm_cfg.get("url", "") or ""),
            llm_api_key=str(llm_cfg.get("api_key", "") or ""),
            llm_model=str(llm_cfg.get("model", "") or ""),
            gitea_url=str(gitea_cfg.get("url", "") or ""),
            gitea_token=str(gitea_cfg.get("token", "") or ""),
            gitea_timeout=float(gitea_cfg.get("timeout", 0.0) or 0.0),
            kube_namespace=str(k8s_cfg.get("namespace", "") or ""),
            kube_context=str(k8s_cfg.get("context", "") or ""),
            safety_mode=str(safety_cfg.get("mode", "") or ""),
            read_only=bool(data.get("read_only", False)),
            prometheus_url=prom_url,
            loki_url=loki_url,
            verbose=bool(data.get("verbose", False)),
            max_messages=int(data.get("max_messages", 0) or 0),
            max_tool_iterations=int(data.get("max_tool_iterations", 0) or 0),
            max_auto_continue=int(data.get("max_auto_continue", 0) or 0),
            tool_result_max_chars=int(data.get("tool_result_max_chars", 0) or 0),
        )

    @classmethod
    def from_env(cls) -> AgentConfig:
        """환경 변수에서 설정을 로드합니다."""
        read_only_env = os.environ.get("KUBE_AGENT_READ_ONLY", "").lower() in ("1", "true", "yes")
        return cls(
            llm_base_url=os.environ.get("KUBE_AGENT_LLM_URL", ""),
            llm_api_key=os.environ.get("KUBE_AGENT_LLM_API_KEY", ""),
            llm_model=os.environ.get("KUBE_AGENT_LLM_MODEL", ""),
            gitea_url=os.environ.get("KUBE_AGENT_GITEA_URL", ""),
            gitea_token=os.environ.get("KUBE_AGENT_GITEA_TOKEN", ""),
            kube_namespace=os.environ.get("KUBE_AGENT_NAMESPACE", ""),
            kube_context=os.environ.get("KUBE_AGENT_CONTEXT", ""),
            max_messages=int(os.environ.get("KUBE_AGENT_MAX_MESSAGES", "0")),
            max_tool_iterations=int(os.environ.get("KUBE_AGENT_MAX_TOOL_ITERATIONS", "0")),
            max_auto_continue=int(os.environ.get("KUBE_AGENT_MAX_AUTO_CONTINUE", "0")),
            gitea_timeout=float(os.environ.get("KUBE_AGENT_GITEA_TIMEOUT", "0")),
            tool_result_max_chars=int(os.environ.get("KUBE_AGENT_TOOL_RESULT_MAX_CHARS", "0")),
            safety_mode=os.environ.get("KUBE_AGENT_SAFETY_MODE", ""),
            read_only=read_only_env,
            prometheus_url=os.environ.get("KUBE_AGENT_PROMETHEUS_URL", os.environ.get("PROMETHEUS_URL", "")),
            loki_url=os.environ.get("KUBE_AGENT_LOKI_URL", os.environ.get("LOKI_URL", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        """설정 객체를 딕셔너리로 변환합니다."""
        return self.__dict__.copy()

    def merge(self, **overrides: Any) -> AgentConfig:
        """외부 값으로 필드를 오버라이드합니다 (truthy 값만 적용)."""
        updates: dict[str, Any] = {}
        for key, value in overrides.items():
            if value is not None and value != "" and value != 0:
                updates[key] = value
        if updates:
            current = self.__dict__.copy()
            current.update(updates)
            return AgentConfig(**current)
        return self

    def resolve(self) -> AgentConfig:
        """기본값을 적용하여 최종 설정을 확정합니다."""
        # 1. LLM 엔드포인트 자동 감지 (OpenAI 환경변수 등)
        llm_url = self.llm_base_url
        llm_key = self.llm_api_key
        llm_model = self.llm_model

        if not llm_url:
            if os.environ.get("OPENAI_API_KEY"):
                llm_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
                llm_key = os.environ.get("OPENAI_API_KEY", "")
                llm_model = llm_model or "gpt-4o"
            else:
                llm_url = _DEFAULT_LLM_URL
                llm_key = llm_key or "no-key"
                llm_model = llm_model or _DEFAULT_LLM_MODEL

        # 2. Kubernetes 네임스페이스 자동 감지
        ns = self.kube_namespace
        if not ns:
            ns = _detect_kube_namespace(self.kube_context)

        # 3. Read-only 모드 적용
        effective_safety = self.safety_mode or _DEFAULT_SAFETY_MODE
        if self.read_only:
            effective_safety = "read_only"

        return AgentConfig(
            llm_base_url=llm_url,
            llm_api_key=llm_key or "no-key",
            llm_model=llm_model or _DEFAULT_LLM_MODEL,
            gitea_url=self.gitea_url or "",
            gitea_token=self.gitea_token or "",
            kube_namespace=ns,
            kube_context=self.kube_context or "",
            verbose=self.verbose,
            read_only=self.read_only,
            max_messages=self.max_messages or _DEFAULT_MAX_MESSAGES,
            max_tool_iterations=self.max_tool_iterations or _DEFAULT_MAX_TOOL_ITERATIONS,
            max_auto_continue=self.max_auto_continue or _DEFAULT_MAX_AUTO_CONTINUE,
            gitea_timeout=self.gitea_timeout or _DEFAULT_GITEA_TIMEOUT,
            tool_result_max_chars=self.tool_result_max_chars or _DEFAULT_TOOL_RESULT_MAX_CHARS,
            safety_mode=effective_safety,
            prometheus_url=(
                self.prometheus_url
                or os.environ.get("KUBE_AGENT_PROMETHEUS_URL", os.environ.get("PROMETHEUS_URL", ""))
            ),
            loki_url=(
                self.loki_url
                or os.environ.get("KUBE_AGENT_LOKI_URL", os.environ.get("LOKI_URL", ""))
            ),
        )
