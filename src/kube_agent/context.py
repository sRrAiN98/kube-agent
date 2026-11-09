"""컨텍스트 윈도우 최적화 및 메시지 압축 엔진.

오프라인 온프레미스 LLM(vLLM, LiteLLM)의 컨텍스트 한계를 방어하기 위해
오래된 도구 출력 결과를 안전하게 요약/트렁케이션하고 대화 맥락을 보존합니다.
"""

from __future__ import annotations

from typing import Any


class ContextManager:
    """대화 메시지 히스토리 압축 및 컨텍스트 관리자."""

    def __init__(
        self,
        max_messages: int = 60,
        tool_truncate_chars: int = 1500,
        keep_recent_turns: int = 6,
    ) -> None:
        """ContextManager를 초기화합니다.

        Args:
            max_messages: 최대 유지할 메시지 수
            tool_truncate_chars: 오래된 도구 결과의 최대 글자 수
            keep_recent_turns: 압축하지 않고 원본을 유지할 최근 메시지 수
        """
        self.max_messages = max_messages
        self.tool_truncate_chars = tool_truncate_chars
        self.keep_recent_turns = keep_recent_turns

    def truncate_tool_content(self, content: str) -> str:
        """대형 도구 출력 문자열을 앞/뒤 핵심만 남기고 요약 압축합니다.

        Args:
            content: 원본 도구 출력 문자열

        Returns:
            요약 압축된 문자열
        """
        if len(content) <= self.tool_truncate_chars:
            return content

        half = self.tool_truncate_chars // 2
        head = content[:half]
        tail = content[-half:]
        omitted = len(content) - (half * 2)
        return f"{head}\n... [중략: {omitted:,}자 압축 생략됨] ...\n{tail}"

    def compact(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """메시지 목록을 검사하여 오래된 도구 출력을 압축하고 수량을 제한합니다.

        시스템 프롬프트(첫 번째 메시지)는 항상 보존합니다.

        Args:
            messages: OpenAI 형식의 메시지 리스트

        Returns:
            압축이 완료된 최적화 메시지 리스트
        """
        if not messages:
            return []

        system_msg = messages[0] if messages[0].get("role") == "system" else None
        chat_msgs = messages[1:] if system_msg else messages[:]

        # 1. 최근 keep_recent_turns 이전의 오래된 tool 메시지 압축
        compacted: list[dict[str, Any]] = []
        recent_threshold = max(0, len(chat_msgs) - self.keep_recent_turns)

        for idx, msg in enumerate(chat_msgs):
            if idx < recent_threshold and msg.get("role") == "tool":
                original_content = msg.get("content", "")
                truncated = self.truncate_tool_content(original_content)
                new_msg = dict(msg)
                new_msg["content"] = truncated
                compacted.append(new_msg)
            else:
                compacted.append(msg)

        # 2. max_messages 제한 적용 (오래된 메시지부터 슬라이싱)
        effective_max = self.max_messages - (1 if system_msg else 0)
        if len(compacted) > effective_max:
            compacted = compacted[-effective_max:]

        # 3. 시스템 프롬프트 복원
        if system_msg:
            return [system_msg] + compacted
        return compacted

