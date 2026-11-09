"""LLMClient 모듈 단위 테스트 (스트리밍 및 도구 호출 검증)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from kube_agent.config import AgentConfig
from kube_agent.llm import LLMClient


@pytest.fixture
def llm_client(agent_config: AgentConfig) -> LLMClient:
    return LLMClient(agent_config)


@pytest.mark.asyncio
async def test_chat_non_streaming_success(llm_client: LLMClient) -> None:
    """비스트리밍 일반 채팅 호출을 검증합니다."""
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "안녕하세요"
    mock_choice.message.tool_calls = None
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    llm_client._client.chat.completions.create = AsyncMock(return_value=mock_resp)

    res = await llm_client.chat([{"role": "user", "content": "안녕"}])
    assert res["role"] == "assistant"
    assert res["content"] == "안녕하세요"
    assert "tool_calls" not in res


@pytest.mark.asyncio
async def test_chat_streaming_tokens_and_tool_calls(llm_client: LLMClient) -> None:
    """스트리밍 시 토큰 콜백 호출 및 tool_call 청크 병합을 검증합니다."""

    # 스트리밍 청크 제너레이터 시뮬레이션
    async def mock_stream_chunks():
        # 청크 1: 텍스트 토큰
        c1 = MagicMock()
        c1.choices = [MagicMock()]
        c1.choices[0].delta.content = "단계 "
        c1.choices[0].delta.tool_calls = None
        yield c1

        # 청크 2: 텍스트 토큰
        c2 = MagicMock()
        c2.choices = [MagicMock()]
        c2.choices[0].delta.content = "완료."
        c2.choices[0].delta.tool_calls = None
        yield c2

        # 청크 3: 도구 호출 시작
        c3 = MagicMock()
        c3.choices = [MagicMock()]
        c3.choices[0].delta.content = None
        tc1 = MagicMock()
        tc1.index = 0
        tc1.id = "call_abc"
        tc1.function.name = "k8s_list_pods"
        tc1.function.arguments = "{\""
        c3.choices[0].delta.tool_calls = [tc1]
        yield c3

        # 청크 4: 도구 호출 인자 전달
        c4 = MagicMock()
        c4.choices = [MagicMock()]
        c4.choices[0].delta.content = None
        tc2 = MagicMock()
        tc2.index = 0
        tc2.id = None
        tc2.function.name = None
        tc2.function.arguments = "}"
        c4.choices[0].delta.tool_calls = [tc2]
        yield c4

    llm_client._client.chat.completions.create = AsyncMock(return_value=mock_stream_chunks())

    collected_tokens: list[str] = []
    res = await llm_client.chat(
        messages=[{"role": "user", "content": "테스트"}],
        on_token=collected_tokens.append,
    )

    # 토큰 실시간 수신 검증
    assert collected_tokens == ["단계 ", "완료."]
    assert res["content"] == "단계 완료."

    # 스트리밍 도구 호출 병합 검증
    assert "tool_calls" in res
    assert len(res["tool_calls"]) == 1
    call = res["tool_calls"][0]
    assert call["id"] == "call_abc"
    assert call["function"]["name"] == "k8s_list_pods"
    assert call["function"]["arguments"] == "{\"}"

