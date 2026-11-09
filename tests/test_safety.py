"""도구 위험도 분류기(safety.py) 단위 테스트 및 에이전트 인터셉터 검증."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from kube_agent.agent import Agent
from kube_agent.config import AgentConfig
from kube_agent.safety import RiskLevel, assess_risk


class TestRiskAssessment:
    """도구 호출 위험도 등급 평가 검증."""

    def test_safe_tools_classified_as_safe(self) -> None:
        """조회성 도구는 SAFE로 분류되고 승인이 불필요해야 합니다."""
        res = assess_risk("k8s_list_pods", {})
        assert res.level == RiskLevel.SAFE
        assert not res.requires_confirmation

        res_file = assess_risk("file_read", {"path": "/tmp/a.txt"})
        assert res_file.level == RiskLevel.SAFE
        assert not res_file.requires_confirmation

    def test_destructive_delete_repo(self) -> None:
        """gitea_delete_repo는 DESTRUCTIVE로 분류되고 승인이 필수여야 합니다."""
        res = assess_risk("gitea_delete_repo", {"owner": "admin", "name": "prod-app"})
        assert res.level == RiskLevel.DESTRUCTIVE
        assert res.requires_confirmation
        assert "영구 삭제" in res.reason

    def test_destructive_scale_zero(self) -> None:
        """replicas=0 스케일링은 DESTRUCTIVE로 분류되어야 합니다."""
        res = assess_risk("k8s_scale_deployment", {"name": "api-gateway", "replicas": 0})
        assert res.level == RiskLevel.DESTRUCTIVE
        assert res.requires_confirmation
        assert "전면 중단" in res.reason

    def test_sensitive_scale_positive(self) -> None:
        """replicas > 0 스케일링은 SENSITIVE로 분류되어야 합니다."""
        res = assess_risk("k8s_scale_deployment", {"name": "api-gateway", "replicas": 3}, safety_mode="strict")
        assert res.level == RiskLevel.SENSITIVE
        assert res.requires_confirmation

        res_permissive = assess_risk(
            "k8s_scale_deployment",
            {"name": "api-gateway", "replicas": 3},
            safety_mode="permissive",
        )
        assert res_permissive.level == RiskLevel.SENSITIVE
        assert not res_permissive.requires_confirmation

    def test_disabled_safety_mode(self) -> None:
        """안전 모드가 disabled이면 어떤 도구도 승인을 요구하지 않아야 합니다."""
        res = assess_risk("gitea_delete_repo", {"owner": "admin", "name": "app"}, safety_mode="disabled")
        assert not res.requires_confirmation


@pytest.mark.asyncio
async def test_agent_safety_interceptor_blocks_when_rejected(agent_config: AgentConfig) -> None:
    """사용자가 승인을 거부하면 파괴적 도구 실행이 차단되어야 합니다."""
    agent_config.safety_mode = "strict"
    agent_config.max_tool_iterations = 1

    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api"),
        patch("kubernetes.client.AppsV1Api"),
        patch("kube_agent.cli.ask_confirmation", return_value=False),
        patch("kube_agent.agent.execute_tool") as mock_exec,
    ):
        agent = Agent(agent_config)
        agent._llm.chat = AsyncMock(return_value={"role": "assistant", "content": "완료"})

        response = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "gitea_delete_repo",
                        "arguments": '{"owner": "admin", "name": "prod"}',
                    },
                }
            ],
        }

        await agent._process_tool_calls(response)

        # execute_tool이 호출되지 않았어야 함
        mock_exec.assert_not_called()

        # 도구 응답 메시지에 안전 차단 내용이 기록되어야 함
        tool_msg = [m for m in agent._messages if m.get("role") == "tool"][0]
        assert "[안전 차단]" in tool_msg["content"]
