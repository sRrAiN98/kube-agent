"""Configuration management for kube-agent.

환경 변수 및 CLI 인자를 통해 에이전트 설정을 관리합니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# 클러스터 내부 기본 LLM 엔드포인트 (LiteLLM)
_DEFAULT_LLM_URL = "http://litellm.litellm.svc.cluster.local:4000/v1"
_DEFAULT_LLM_MODEL = "gpt-4o"
_DEFAULT_NAMESPACE = "default"
_DEFAULT_MAX_MESSAGES = 80
_DEFAULT_MAX_TOOL_ITERATIONS = 30
_DEFAULT_MAX_AUTO_CONTINUE = 5
_DEFAULT_GITEA_TIMEOUT = 30.0
_DEFAULT_TOOL_RESULT_MAX_CHARS = 3000


@dataclass
class AgentConfig:
    """에이전트 실행에 필요한 모든 설정을 관리하는 데이터클래스.

    설정 우선순위: CLI 인자 > 환경 변수 > 기본값
    """

    llm_base_url: str = field(default="")
    llm_api_key: str = field(default="")
    llm_model: str = field(default="")
    gitea_url: str = field(default="")
    gitea_token: str = field(default="")
    kube_namespace: str = field(default="")
    kube_context: str = field(default="")
    verbose: bool = field(default=False)
    # 에이전트 루프 제한 (0 = 기본값 사용)
    max_messages: int = field(default=0)
    max_tool_iterations: int = field(default=0)
    max_auto_continue: int = field(default=0)
    # Gitea HTTP 타임아웃 (0 = 기본값 사용)
    gitea_timeout: float = field(default=0.0)
    # 도구 실행 결과 최대 표시 글자 수 (0 = 기본값 사용)
    tool_result_max_chars: int = field(default=0)

    @classmethod
    def from_env(cls) -> AgentConfig:
        """환경 변수에서 설정을 로드합니다.

        지원하는 환경 변수:
            KUBE_AGENT_LLM_URL: LLM API 엔드포인트
            KUBE_AGENT_LLM_API_KEY: LLM API 인증 키
            KUBE_AGENT_LLM_MODEL: LLM 모델명
            KUBE_AGENT_GITEA_URL: Gitea 서버 URL
            KUBE_AGENT_GITEA_TOKEN: Gitea API 토큰
            KUBE_AGENT_NAMESPACE: 기본 Kubernetes 네임스페이스
            KUBE_AGENT_CONTEXT: Kubernetes 컨텍스트
            KUBE_AGENT_MAX_MESSAGES: 최대 메시지 히스토리 수 (기본: 80)
            KUBE_AGENT_MAX_TOOL_ITERATIONS: 단일 요청당 최대 도구 호출 횟수 (기본: 30)
            KUBE_AGENT_MAX_AUTO_CONTINUE: 자율 실행 최대 라운드 수 (기본: 5)
            KUBE_AGENT_GITEA_TIMEOUT: Gitea API HTTP 타임아웃 초 (기본: 30)
            KUBE_AGENT_TOOL_RESULT_MAX_CHARS: 도구 결과 최대 표시 글자 수 (기본: 3000)

        Returns:
            환경 변수 값이 적용된 AgentConfig 인스턴스
        """
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
        )

    def merge(self, **overrides: str | bool) -> AgentConfig:
        """CLI 인자 등 외부 값으로 빈 필드를 오버라이드합니다.

        이미 값이 설정된 필드는 덮어쓰지 않습니다 (CLI > env > default 순서).
        빈 문자열이 아닌 값만 오버라이드합니다.

        Args:
            **overrides: 오버라이드할 필드 키-값 쌍

        Returns:
            오버라이드가 적용된 새 AgentConfig 인스턴스
        """
        updates: dict[str, str | bool] = {}
        for key, value in overrides.items():
            if value and not getattr(self, key, None):
                updates[key] = value
        if updates:
            current = self.__dict__.copy()
            current.update(updates)
            return AgentConfig(**current)
        return self

    def resolve(self) -> AgentConfig:
        """기본값을 적용하여 최종 설정을 확정합니다.

        빈 문자열 또는 0인 필드에 기본값을 채워넣습니다.

        Returns:
            기본값이 적용된 최종 AgentConfig 인스턴스
        """
        return AgentConfig(
            llm_base_url=self.llm_base_url or _DEFAULT_LLM_URL,
            llm_api_key=self.llm_api_key or "no-key",
            llm_model=self.llm_model or _DEFAULT_LLM_MODEL,
            gitea_url=self.gitea_url or "",
            gitea_token=self.gitea_token or "",
            kube_namespace=self.kube_namespace or _DEFAULT_NAMESPACE,
            kube_context=self.kube_context or "",
            verbose=self.verbose,
            max_messages=self.max_messages or _DEFAULT_MAX_MESSAGES,
            max_tool_iterations=self.max_tool_iterations or _DEFAULT_MAX_TOOL_ITERATIONS,
            max_auto_continue=self.max_auto_continue or _DEFAULT_MAX_AUTO_CONTINUE,
            gitea_timeout=self.gitea_timeout or _DEFAULT_GITEA_TIMEOUT,
            tool_result_max_chars=self.tool_result_max_chars or _DEFAULT_TOOL_RESULT_MAX_CHARS,
        )
