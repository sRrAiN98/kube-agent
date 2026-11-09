"""에이전트 루프 및 자율 진행(agent.py) 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from kube_agent.agent import Agent
from kube_agent.config import AgentConfig


class TestAgentAutonomy:
    """에이전트 자율 진행 판단 및 서킷 브레이커 검증."""

    def test_needs_continuation_detection(self) -> None:
        """미완료 지표가 포함된 응답은 계속 진행(True)으로 판단해야 합니다."""
        resp_continue = {"role": "assistant", "content": "다음 단계로 Gitea 저장소를 클론하겠습니다."}
        assert Agent._needs_continuation(resp_continue) is True

        resp_continue_en = {"role": "assistant", "content": "Next, I will inspect the pod logs."}
        assert Agent._needs_continuation(resp_continue_en) is True

    def test_needs_continuation_completion(self) -> None:
        """완료 지표가 포함된 응답은 완료(False)로 판단해야 합니다."""
        resp_done = {
            "role": "assistant",
            "content": "모든 수정 작업이 성공적으로 완료되었습니다. Pod가 정상 동작 중입니다.",
        }
        assert Agent._needs_continuation(resp_done) is False

        resp_done_en = {"role": "assistant", "content": "Task completed successfully."}
        assert Agent._needs_continuation(resp_done_en) is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_after_three_failures(self, agent_config: AgentConfig) -> None:
        """동일한 인자로 3회 연속 실패 시 서킷 브레이커가 동작해야 합니다."""
        agent_config.safety_mode = "disabled"
        agent_config.max_tool_iterations = 5

        with (
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api"),
            patch("kubernetes.client.AppsV1Api"),
            patch("kube_agent.agent.execute_tool", new_callable=AsyncMock) as mock_exec,
        ):
            mock_exec.return_value = "오류 발생: 연결 실패 (Connection refused)"

            agent = Agent(agent_config)
            agent._llm.chat = AsyncMock(return_value={"role": "assistant", "content": "완료"})

            # 4번 연속 동일 실패 도구 호출 시뮬레이션
            tool_call = {
                "id": "tc-1",
                "type": "function",
                "function": {
                    "name": "k8s_get_pod",
                    "arguments": '{"name": "broken-pod"}',
                },
            }

            # 1회차
            await agent._process_tool_calls({"role": "assistant", "tool_calls": [tool_call]})
            # 2회차
            await agent._process_tool_calls({"role": "assistant", "tool_calls": [tool_call]})
            # 3회차
            await agent._process_tool_calls({"role": "assistant", "tool_calls": [tool_call]})
            # 4회차 (서킷 브레이커 트립)
            await agent._process_tool_calls({"role": "assistant", "tool_calls": [tool_call]})

            # execute_tool은 최대 3번만 실행되고, 4번째에는 서킷 브레이커가 가로채야 함
            assert mock_exec.call_count == 3
            last_tool_msg = [m for m in agent._messages if m.get("role") == "tool"][-1]
            assert "[서킷 브레이커]" in last_tool_msg["content"]

    @pytest.mark.asyncio
    async def test_read_only_mode_blocks_mutations(self, agent_config: AgentConfig) -> None:
        """read_only 모드에서는 상태 변경 작업이 즉시 차단되어야 합니다."""
        agent_config.read_only = True
        agent_config.safety_mode = "read_only"
        agent_config.max_tool_iterations = 2

        with (
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api"),
            patch("kubernetes.client.AppsV1Api"),
            patch("kube_agent.agent.execute_tool", new_callable=AsyncMock) as mock_exec,
        ):
            agent = Agent(agent_config)
            agent._llm.chat = AsyncMock(return_value={"role": "assistant", "content": "완료"})

            mutation_call = {
                "id": "tc-del",
                "type": "function",
                "function": {
                    "name": "k8s_delete_pod",
                    "arguments": '{"name": "test-pod"}',
                },
            }

            await agent._process_tool_calls({"role": "assistant", "tool_calls": [mutation_call]})

            # execute_tool은 실행되지 않아야 함
            mock_exec.assert_not_called()
            last_tool_msg = [m for m in agent._messages if m.get("role") == "tool"][-1]
            assert "[Read-Only 차단]" in last_tool_msg["content"]
