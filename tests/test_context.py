"""ContextManager 모듈 단위 테스트."""

from __future__ import annotations

from kube_agent.context import ContextManager


class TestContextManager:
    """메시지 압축 및 컨텍스트 보존 검증."""

    def test_truncate_tool_content(self) -> None:
        """도구 출력이 제한을 넘으면 중앙이 압축되어야 합니다."""
        mgr = ContextManager(tool_truncate_chars=100)
        short_text = "abc 123"
        assert mgr.truncate_tool_content(short_text) == short_text

        long_text = "A" * 200 + "B" * 200
        truncated = mgr.truncate_tool_content(long_text)
        assert len(truncated) < len(long_text)
        assert "압축 생략됨" in truncated
        assert truncated.startswith("A" * 50)
        assert truncated.endswith("B" * 50)

    def test_compact_preserves_system_prompt(self) -> None:
        """압축 후에도 시스템 프롬프트는 항상 첫 번째로 보존되어야 합니다."""
        mgr = ContextManager(max_messages=3, keep_recent_turns=1)
        messages = [
            {"role": "system", "content": "You are assistant"},
            {"role": "user", "content": "msg 1"},
            {"role": "assistant", "content": "msg 2"},
            {"role": "user", "content": "msg 3"},
            {"role": "assistant", "content": "msg 4"},
        ]
        compacted = mgr.compact(messages)
        assert len(compacted) == 3
        assert compacted[0]["role"] == "system"
        assert compacted[0]["content"] == "You are assistant"
        assert compacted[-1]["content"] == "msg 4"

    def test_compact_truncates_only_older_tools(self) -> None:
        """최근 턴의 도구는 원본을 유지하고, 이전 턴의 오래된 대형 도구만 압축되어야 합니다."""
        mgr = ContextManager(max_messages=10, tool_truncate_chars=50, keep_recent_turns=2)
        big_content = "X" * 200

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "tool", "content": big_content},          # 오래된 도구 -> 압축 대상
            {"role": "assistant", "content": "step 1 done"},
            {"role": "tool", "content": big_content},          # 최근 턴 도구 -> 원본 보존
            {"role": "assistant", "content": "step 2 done"},
        ]
        compacted = mgr.compact(messages)
        # messages[1]은 압축됨
        assert "압축 생략됨" in compacted[1]["content"]
        # messages[3]은 원본 유지
        assert compacted[3]["content"] == big_content

