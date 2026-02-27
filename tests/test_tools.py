"""도구 레지스트리 및 execute_tool 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kube_agent.tools import TOOLS, _TOOL_REGISTRY, execute_tool


class TestRegistry:
    """_TOOL_REGISTRY가 TOOLS 정의와 일치하는지 검증합니다."""

    def test_all_tools_have_handlers(self) -> None:
        """TOOLS에 정의된 모든 도구에 대해 핸들러가 등록되어 있어야 합니다."""
        defined_names = {t["function"]["name"] for t in TOOLS}
        registered_names = set(_TOOL_REGISTRY.keys())
        missing = defined_names - registered_names
        assert not missing, f"핸들러가 없는 도구: {missing}"

    def test_no_orphan_handlers(self) -> None:
        """TOOLS에 정의되지 않은 핸들러가 없어야 합니다."""
        defined_names = {t["function"]["name"] for t in TOOLS}
        registered_names = set(_TOOL_REGISTRY.keys())
        orphans = registered_names - defined_names
        assert not orphans, f"TOOLS에 정의 없는 핸들러: {orphans}"

    def test_tool_count_matches(self) -> None:
        """등록된 핸들러 수와 TOOLS 정의 수가 일치해야 합니다."""
        assert len(_TOOL_REGISTRY) == len(TOOLS)


class TestExecuteTool:
    """execute_tool의 디스패치 동작을 검증합니다."""

    @pytest.fixture
    def mocks(self):
        k8s = MagicMock()
        gitea = MagicMock()
        files = MagicMock()
        return k8s, gitea, files

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, mocks) -> None:
        k8s, gitea, files = mocks
        result = await execute_tool("no_such_tool", {}, k8s, gitea, files)
        assert "알 수 없는 도구" in result

    @pytest.mark.asyncio
    async def test_k8s_list_pods_dispatched(self, mocks) -> None:
        k8s, gitea, files = mocks
        k8s.list_pods.return_value = "pod-list"
        result = await execute_tool("k8s_list_pods", {}, k8s, gitea, files)
        assert result == "pod-list"
        k8s.list_pods.assert_called_once()

    @pytest.mark.asyncio
    async def test_k8s_get_pod_passes_name(self, mocks) -> None:
        k8s, gitea, files = mocks
        k8s.get_pod.return_value = "pod-detail"
        result = await execute_tool("k8s_get_pod", {"name": "my-pod"}, k8s, gitea, files)
        assert result == "pod-detail"
        k8s.get_pod.assert_called_once_with(name="my-pod")

    @pytest.mark.asyncio
    async def test_gitea_async_handler(self, mocks) -> None:
        """비동기 Gitea 핸들러가 올바르게 await되어야 합니다."""
        k8s, gitea, files = mocks
        gitea.list_repos = AsyncMock(return_value="repo-list")
        result = await execute_tool("gitea_list_repos", {}, k8s, gitea, files)
        assert result == "repo-list"
        gitea.list_repos.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_required_arg_returns_error(self, mocks) -> None:
        """필수 인자 누락 시 에러 메시지를 반환해야 합니다."""
        k8s, gitea, files = mocks
        # k8s_get_pod는 'name' 필수
        k8s.get_pod.side_effect = KeyError("name")
        result = await execute_tool("k8s_get_pod", {}, k8s, gitea, files)
        assert "필수 인자 누락" in result

    @pytest.mark.asyncio
    async def test_file_list_dispatched(self, mocks) -> None:
        k8s, gitea, files = mocks
        files.list_directory.return_value = "dir-listing"
        result = await execute_tool("file_list", {"path": "/tmp/repo"}, k8s, gitea, files)
        assert result == "dir-listing"
        files.list_directory.assert_called_once_with(path="/tmp/repo", recursive=False)

    @pytest.mark.asyncio
    async def test_file_write_with_create_dirs(self, mocks) -> None:
        k8s, gitea, files = mocks
        files.write_file.return_value = "파일 생성 완료"
        result = await execute_tool(
            "file_write",
            {"path": "/tmp/f.txt", "content": "hello", "create_dirs": True},
            k8s, gitea, files,
        )
        assert result == "파일 생성 완료"
        files.write_file.assert_called_once_with(path="/tmp/f.txt", content="hello", create_dirs=True)
