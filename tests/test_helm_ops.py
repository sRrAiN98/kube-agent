"""HelmOps 모듈 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from kube_agent.helm_ops import HelmOps


@pytest.fixture
def helm_ops() -> HelmOps:
    return HelmOps(namespace="test-ns", timeout=5.0)


@pytest.mark.asyncio
async def test_helm_lint_success(helm_ops: HelmOps) -> None:
    """helm lint 성공 결과를 검증합니다."""
    with patch.object(helm_ops, "_run_helm", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "1 chart(s) linted, 0 chart(s) failed", "")
        res = await helm_ops.lint("./charts/my-app")
        assert "Helm Lint 성공" in res
        assert "0 chart(s) failed" in res


@pytest.mark.asyncio
async def test_helm_template_success(helm_ops: HelmOps) -> None:
    """helm template 렌더링을 검증합니다."""
    with patch.object(helm_ops, "_run_helm", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "apiVersion: apps/v1\nkind: Deployment", "")
        res = await helm_ops.template("my-app", "./charts/my-app")
        assert "Helm Template 렌더링 결과" in res
        assert "kind: Deployment" in res


@pytest.mark.asyncio
async def test_helm_upgrade_success(helm_ops: HelmOps) -> None:
    """helm upgrade/install 성공을 검증합니다."""
    with patch.object(helm_ops, "_run_helm", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "Release \"my-app\" has been upgraded. Happy Helming!", "")
        res = await helm_ops.upgrade("my-app", "./charts/my-app")
        assert "Helm Upgrade/Install 성공" in res
        mock_run.assert_called_once_with(["upgrade", "my-app", "./charts/my-app", "-n", "test-ns", "--install"])


@pytest.mark.asyncio
async def test_helm_rollback_success(helm_ops: HelmOps) -> None:
    """helm rollback 성공을 검증합니다."""
    with patch.object(helm_ops, "_run_helm", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "Rollback was a success! Happy Helming!", "")
        res = await helm_ops.rollback("my-app", revision=1)
        assert "Helm Rollback 성공" in res
        mock_run.assert_called_once_with(["rollback", "my-app", "1", "-n", "test-ns"])


@pytest.mark.asyncio
async def test_helm_not_installed(helm_ops: HelmOps) -> None:
    """Helm 바이너리가 없을 때 적절한 가이드 메시지를 반환해야 합니다."""
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        code, out, err = await helm_ops._run_helm(["version"])
        assert code == 127
        assert "바이너리가 설치되어 있지 않습니다" in err


@pytest.mark.asyncio
async def test_helm_timeout(helm_ops: HelmOps) -> None:
    """타임아웃 발생 시 적절한 오류 메시지를 반환해야 합니다."""
    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        code, out, err = await helm_ops._run_helm(["upgrade", "stuck"])
        assert code == 124
        assert "시간이 초과되었습니다" in err

