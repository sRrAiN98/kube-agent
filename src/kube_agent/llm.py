"""LLM client with OpenAI-compatible API and tool calling support.

vLLM/LiteLLM 등 OpenAI 호환 API를 통해 LLM과 통신합니다.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from kube_agent.config import AgentConfig

logger = logging.getLogger(__name__)

# 시스템 프롬프트: 에이전트의 역할과 행동 지침을 정의 (자율 실행 모드)
SYSTEM_PROMPT = (
    "You are kube-agent, an autonomous AI assistant for managing Kubernetes clusters "
    "and Gitea repositories in offline on-premise environments.\n\n"
    "## Capabilities\n"
    "- Kubernetes: list/get/create/update/delete pods, deployments, services, configmaps, "
    "secrets, and perform rolling restarts and scaling.\n"
    "- Gitea: manage repositories, branches, files, and webhooks via REST API and Git CLI.\n"
    "- Files: list, read, and write files in the local workspace (for editing cloned repos).\n\n"
    "## Autonomous Execution Rules\n"
    "You MUST work autonomously until the user's task is FULLY completed. Follow these rules:\n"
    "1. ALWAYS call tools to gather information before making conclusions. Never guess.\n"
    "2. Chain multiple tool calls in sequence to complete multi-step tasks.\n"
    "3. After each tool call, analyze the result and decide the NEXT action — do NOT stop mid-task.\n"
    "4. Only respond with a final text summary AFTER all steps are done.\n"
    "5. If a step fails, diagnose the error and retry with a corrected approach.\n"
    "6. Never ask the user for confirmation mid-task. Execute the full plan autonomously.\n\n"
    "## Workflow Pattern (for complex tasks)\n"
    "1. GATHER: Collect information (logs, pod status, repo contents, file contents)\n"
    "2. DIAGNOSE: Analyze the gathered data to identify issues or requirements\n"
    "3. PLAN: Decide the sequence of actions needed (silently, don't explain the plan)\n"
    "4. EXECUTE: Perform all actions using tools (clone, edit, commit, push, etc.)\n"
    "5. VERIFY: Confirm the changes were applied correctly\n"
    "6. REPORT: Provide a concise final summary of what was done and results\n\n"
    "## Important\n"
    "- Respond in the same language as the user.\n"
    "- When you call tools, ALWAYS continue with the next step after receiving results.\n"
    "- NEVER output a text response between tool calls unless the entire task is complete.\n"
    "- If the task requires 10 tool calls, make all 10 — do not stop at 3 and summarize."
)


class LLMClient:
    """OpenAI 호환 API를 사용하는 LLM 클라이언트.

    vLLM, LiteLLM 등 OpenAI 호환 엔드포인트에 연결하여
    채팅 완성 요청(tool calling 포함)을 처리합니다.
    """

    def __init__(self, config: AgentConfig) -> None:
        """LLM 클라이언트를 초기화합니다.

        Args:
            config: LLM 연결 정보가 포함된 에이전트 설정
        """
        self._client = AsyncOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
        )
        self._model = config.llm_model
        self._verbose = config.verbose

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """LLM에 채팅 완성 요청을 보냅니다.

        Args:
            messages: OpenAI 형식의 메시지 리스트 (role, content 포함)
            tools: OpenAI 형식의 도구 정의 리스트 (선택)

        Returns:
            응답 메시지 딕셔너리. 키:
                - role: "assistant"
                - content: 텍스트 응답 (없을 수 있음)
                - tool_calls: 도구 호출 리스트 (없을 수 있음)

        Raises:
            예외 발생 시 에러 메시지를 content에 담아 반환합니다.
        """
        try:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            if self._verbose:
                logger.debug(
                    "LLM request: model=%s, messages=%d, tools=%d", self._model, len(messages), len(tools or [])
                )

            response = await self._client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # 응답을 직렬화 가능한 딕셔너리로 변환
            result: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }

            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]

            return result

        except Exception as exc:
            logger.error("LLM API 호출 실패: %s", exc)
            return {
                "role": "assistant",
                "content": f"LLM API 호출 중 오류가 발생했습니다: {exc}",
            }
