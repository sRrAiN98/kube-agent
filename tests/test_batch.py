"""Unit tests for kube-agent batch mode (Zero-Token Pre-flight & Auto-Remediation)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kube_agent.batch import run_batch_once
from kube_agent.config import AgentConfig


@pytest.mark.asyncio
async def test_batch_healthy_zero_token_cost(tmp_path: Path) -> None:
    """정상 클러스터 상태에서는 AI 호출을 0회로 유지하고 정상 리포트를 생성해야 합니다."""
    config = AgentConfig(kube_namespace="test-ns")

    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api"),
        patch("kubernetes.client.AppsV1Api"),
        patch("kube_agent.batch.KubernetesOps") as mock_k8s_cls,
        patch("kube_agent.batch.Agent") as mock_agent_cls,
    ):
        mock_k8s = MagicMock()
        mock_k8s.diagnose_cluster.return_value = (
            "=== Kubernetes 클러스터 진단 완료 (Namespace: test-ns) ===\n"
            "상태: 모든 Pod가 정상(Running/Ready) 상태이며 탐지된 장애가 없습니다."
        )
        mock_k8s_cls.return_value = mock_k8s

        res = await run_batch_once(config=config, report_dir=tmp_path, auto_fix=False)

        assert res["status"] == "healthy"
        assert res["ai_called"] is False

        # Agent(LLM)는 전혀 호출되지 않아야 함 (비용 0원)
        mock_agent_cls.assert_not_called()

        # 리포트 파일 확인
        report_file = Path(res["report_path"])
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "HEALTHY (정상)" in content
        assert "AI Token Usage**: `0 tokens`" in content

        # latest.md 확인
        latest = tmp_path / "latest.md"
        assert latest.exists()
        assert "HEALTHY (정상)" in latest.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_batch_anomaly_invokes_ai_analysis(tmp_path: Path) -> None:
    """장애 발생 시에만 선별적으로 LLM을 호출하여 조치 리포트를 생성해야 합니다."""
    config = AgentConfig(kube_namespace="test-ns", read_only=False)

    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api"),
        patch("kubernetes.client.AppsV1Api"),
        patch("kube_agent.batch.KubernetesOps") as mock_k8s_cls,
        patch("kube_agent.batch.Agent") as mock_agent_cls,
    ):
        mock_k8s = MagicMock()
        mock_k8s.diagnose_cluster.return_value = (
            "=== Kubernetes 클러스터 장애 진단 리포트 (Namespace: test-ns) ===\n"
            "[1] Pod: api-crash (Phase: Running)\n"
            "    - 컨테이너 'app' 직전 비정상 종료: 종료 코드 137 (OOMKilled)"
        )
        mock_k8s_cls.return_value = mock_k8s

        mock_agent = MagicMock()
        mock_agent.execute_prompt = AsyncMock(
            return_value="[RCA] 메모리 누수로 인한 OOMKilled 발생. 리소스 한도를 1Gi로 증설 권장."
        )
        mock_agent.close = AsyncMock()
        mock_agent_cls.return_value = mock_agent

        res = await run_batch_once(config=config, report_dir=tmp_path, auto_fix=True)

        assert res["status"] == "anomaly_detected"
        assert res["ai_called"] is True
        assert res["auto_fix"] is True

        # Agent의 execute_prompt가 호출되었는지 확인
        mock_agent.execute_prompt.assert_awaited_once()

        # 리포트 파일 확인
        report_file = Path(res["report_path"])
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "ANOMALY DETECTED" in content
        assert "메모리 누수로 인한 OOMKilled 발생" in content
