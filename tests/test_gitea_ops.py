"""GiteaOps 모듈 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from kube_agent.gitea_ops import GiteaOps


class TestGiteaOps:
    """Gitea REST API 및 Git 보안 검증."""

    def test_git_path_sandbox(self, mock_gitea_ops: GiteaOps) -> None:
        """Git 작업 경로가 샌드박스를 벗어나면 차단되어야 합니다."""
        result = mock_gitea_ops._validate_git_path("/etc")
        assert result is not None
        assert "보안 제한" in result

        allowed = mock_gitea_ops._validate_git_path("/tmp/my-repo")
        assert allowed is None

    @pytest.mark.asyncio
    async def test_list_repos(self, mock_gitea_ops: GiteaOps) -> None:
        """저장소 목록 조회가 정상 동작해야 합니다."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"full_name": "admin/infra", "private": True, "description": "K8s manifests"}
            ]
        }
        mock_gitea_ops._client.get.return_value = mock_resp

        result = await mock_gitea_ops.list_repos()
        assert "admin/infra" in result
        assert "K8s manifests" in result

    @pytest.mark.asyncio
    async def test_create_repo(self, mock_gitea_ops: GiteaOps) -> None:
        """새 저장소 생성이 정상 동작해야 합니다."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "full_name": "admin/new-app",
            "clone_url": "http://gitea/admin/new-app.git",
        }
        mock_gitea_ops._client.post.return_value = mock_resp

        result = await mock_gitea_ops.create_repo("new-app", description="test repo")
        assert "admin/new-app" in result
        assert "생성 완료" in result

    @pytest.mark.asyncio
    async def test_disabled_gitea(self) -> None:
        """Gitea URL이 비어있으면 경고 메시지를 반환해야 합니다."""
        ops = GiteaOps(gitea_url="", token="")
        res = await ops.list_repos()
        assert "설정되지 않았습니다" in res

