"""Shared pytest fixtures and mocks for kube-agent testing."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from kube_agent.config import AgentConfig
from kube_agent.file_ops import FileOps
from kube_agent.gitea_ops import GiteaOps
from kube_agent.kubernetes_ops import KubernetesOps


@pytest.fixture
def agent_config() -> AgentConfig:
    """기본 에이전트 설정 픽스처."""
    return AgentConfig(
        llm_base_url="http://mock-llm:4000/v1",
        llm_api_key="mock-key",
        llm_model="gpt-4o",
        gitea_url="http://mock-gitea:3000",
        gitea_token="mock-token",
        kube_namespace="test-ns",
        kube_context="",
        verbose=False,
    )


@pytest.fixture
def mock_k8s_ops() -> Generator[KubernetesOps, None, None]:
    """Kubernetes API가 모킹된 KubernetesOps 인스턴스를 제공합니다."""
    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        patch("kubernetes.client.AppsV1Api") as mock_apps_cls,
    ):
        ops = KubernetesOps(namespace="test-ns")
        ops._core = mock_core_cls.return_value
        ops._apps = mock_apps_cls.return_value
        yield ops


@pytest.fixture
def mock_gitea_ops() -> Generator[GiteaOps, None, None]:
    """HTTP 및 Git 실행이 모킹된 GiteaOps 인스턴스를 제공합니다."""
    ops = GiteaOps(gitea_url="http://mock-gitea:3000", token="mock-token")
    mock_client = AsyncMock()
    ops._client = mock_client
    yield ops


@pytest.fixture
def mock_file_ops(tmp_path: Path) -> Generator[FileOps, None, None]:
    """임시 샌드박스 경로를 허용하도록 설정된 FileOps 인스턴스를 제공합니다."""
    ops = FileOps()
    # 임시 디렉토리를 샌드박스로 허용
    with patch("kube_agent.file_ops._SANDBOX_DIRS", ("/tmp", "/home/agent", str(tmp_path))):
        yield ops
