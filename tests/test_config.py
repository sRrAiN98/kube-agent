"""AgentConfig 설정 관리 단위 테스트."""

from __future__ import annotations

import os

import pytest

from kube_agent.config import (
    AgentConfig,
    _DEFAULT_LLM_MODEL,
    _DEFAULT_LLM_URL,
    _DEFAULT_MAX_MESSAGES,
    _DEFAULT_NAMESPACE,
)


class TestMerge:
    """merge()의 CLI > env > default 우선순위를 검증합니다."""

    def test_cli_overrides_env(self) -> None:
        """CLI 값이 환경 변수 값을 덮어써야 합니다."""
        config = AgentConfig(llm_base_url="http://from-env")
        merged = config.merge(llm_base_url="http://from-cli")
        assert merged.llm_base_url == "http://from-cli"

    def test_empty_cli_keeps_env(self) -> None:
        """CLI 값이 빈 문자열이면 환경 변수 값을 유지해야 합니다."""
        config = AgentConfig(llm_base_url="http://from-env")
        merged = config.merge(llm_base_url="")
        assert merged.llm_base_url == "http://from-env"

    def test_verbose_flag_set_by_cli(self) -> None:
        """CLI --verbose 플래그가 설정되면 verbose=True여야 합니다."""
        config = AgentConfig(verbose=False)
        merged = config.merge(verbose=True)
        assert merged.verbose is True

    def test_verbose_false_does_not_override_true(self) -> None:
        """CLI verbose=False(기본값)는 env에서 설정된 True를 덮어쓰지 않아야 합니다."""
        config = AgentConfig(verbose=True)
        merged = config.merge(verbose=False)
        # False는 falsy이므로 덮어쓰지 않음
        assert merged.verbose is True

    def test_returns_new_instance(self) -> None:
        """merge()는 원본을 수정하지 않고 새 인스턴스를 반환해야 합니다."""
        original = AgentConfig(llm_base_url="http://original")
        merged = original.merge(llm_base_url="http://new")
        assert original.llm_base_url == "http://original"
        assert merged.llm_base_url == "http://new"

    def test_no_overrides_returns_same(self) -> None:
        """오버라이드할 값이 없으면 같은 인스턴스를 반환해야 합니다."""
        config = AgentConfig(llm_base_url="http://url")
        result = config.merge(llm_base_url="")
        assert result is config

    def test_multiple_fields_merged(self) -> None:
        """여러 필드를 동시에 오버라이드할 수 있어야 합니다."""
        config = AgentConfig(llm_base_url="http://old-url", gitea_url="http://old-gitea")
        merged = config.merge(llm_base_url="http://new-url", gitea_url="http://new-gitea")
        assert merged.llm_base_url == "http://new-url"
        assert merged.gitea_url == "http://new-gitea"


class TestResolve:
    """resolve()의 기본값 적용을 검증합니다."""

    def test_empty_config_gets_defaults(self) -> None:
        """빈 설정에 기본값이 모두 채워져야 합니다."""
        config = AgentConfig().resolve()
        assert config.llm_base_url == _DEFAULT_LLM_URL
        assert config.llm_model == _DEFAULT_LLM_MODEL
        assert config.kube_namespace == _DEFAULT_NAMESPACE
        assert config.max_messages == _DEFAULT_MAX_MESSAGES
        assert config.llm_api_key == "no-key"

    def test_explicit_values_preserved(self) -> None:
        """명시적으로 설정된 값은 resolve() 후에도 유지되어야 합니다."""
        config = AgentConfig(
            llm_base_url="http://custom",
            llm_model="gpt-3.5",
            kube_namespace="prod",
        ).resolve()
        assert config.llm_base_url == "http://custom"
        assert config.llm_model == "gpt-3.5"
        assert config.kube_namespace == "prod"

    def test_zero_int_gets_default(self) -> None:
        """0인 int 필드에 기본값이 채워져야 합니다."""
        config = AgentConfig(max_messages=0).resolve()
        assert config.max_messages == _DEFAULT_MAX_MESSAGES


class TestFromEnv:
    """from_env()의 환경 변수 로드를 검증합니다."""

    def test_reads_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """환경 변수 값이 정확히 로드되어야 합니다."""
        monkeypatch.setenv("KUBE_AGENT_LLM_URL", "http://env-url")
        monkeypatch.setenv("KUBE_AGENT_LLM_MODEL", "gpt-4")
        monkeypatch.setenv("KUBE_AGENT_NAMESPACE", "staging")

        config = AgentConfig.from_env()
        assert config.llm_base_url == "http://env-url"
        assert config.llm_model == "gpt-4"
        assert config.kube_namespace == "staging"

    def test_missing_env_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """환경 변수가 없으면 빈 값이어야 합니다."""
        for key in ("KUBE_AGENT_LLM_URL", "KUBE_AGENT_LLM_MODEL", "KUBE_AGENT_NAMESPACE"):
            monkeypatch.delenv(key, raising=False)

        config = AgentConfig.from_env()
        assert config.llm_base_url == ""
        assert config.llm_model == ""
        assert config.kube_namespace == ""


class TestPriorityChain:
    """from_env() → merge() → resolve() 3단계 체인이 우선순위를 올바르게 적용하는지 검증합니다."""

    def test_cli_beats_env_beats_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI > 환경변수 > 기본값 우선순위가 전체 체인에서 보장되어야 합니다."""
        monkeypatch.setenv("KUBE_AGENT_LLM_URL", "http://env-url")
        monkeypatch.setenv("KUBE_AGENT_LLM_MODEL", "env-model")

        config = (
            AgentConfig.from_env()
            .merge(llm_base_url="http://cli-url")  # CLI가 env를 덮어씀
            .resolve()
        )

        assert config.llm_base_url == "http://cli-url"   # CLI 우선
        assert config.llm_model == "env-model"           # env (CLI 없음)

    def test_env_beats_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI가 없을 때 환경변수가 기본값을 덮어써야 합니다."""
        monkeypatch.setenv("KUBE_AGENT_LLM_MODEL", "env-only-model")
        monkeypatch.delenv("KUBE_AGENT_LLM_URL", raising=False)

        config = AgentConfig.from_env().merge().resolve()

        assert config.llm_model == "env-only-model"      # env 우선
        assert config.llm_base_url == _DEFAULT_LLM_URL   # 기본값 (env 없음)
