"""Agent main loop for kube-agent.

LLM, Kubernetes, Gitea 작업을 조율하는 에이전트 메인 루프입니다.
사용자 입력 -> LLM 호출 -> 도구 실행 -> 결과 반환의 사이클을 관리합니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from kube_agent import cli
from kube_agent.config import AgentConfig
from kube_agent.file_ops import FileOps
from kube_agent.gitea_ops import GiteaOps
from kube_agent.kubernetes_ops import KubernetesOps
from kube_agent.llm import SYSTEM_PROMPT, LLMClient
from kube_agent.tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)


class Agent:
    """Kubernetes/Gitea 관리를 위한 대화형 AI 에이전트.

    사용자와 LLM 간의 대화를 관리하고, LLM이 요청하는
    도구(tool)를 실행하여 결과를 반환합니다.
    """

    def __init__(self, config: AgentConfig) -> None:
        """에이전트를 초기화합니다.

        Args:
            config: 에이전트 설정 (LLM, K8s, Gitea 연결 정보 포함)
        """
        self._config = config
        self._llm = LLMClient(config)
        self._k8s = KubernetesOps(
            namespace=config.kube_namespace,
            context=config.kube_context,
        )
        self._gitea = GiteaOps(
            gitea_url=config.gitea_url,
            token=config.gitea_token,
            timeout=config.gitea_timeout,
        )
        self._files = FileOps()
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

    def _trim_messages(self) -> None:
        """메시지 히스토리가 너무 길면 오래된 메시지를 제거합니다.

        시스템 프롬프트는 항상 유지하고, 나머지 메시지 중
        오래된 것부터 제거하여 max_messages 이하로 유지합니다.
        """
        max_messages = self._config.max_messages
        if len(self._messages) > max_messages:
            # 시스템 프롬프트(첫 번째)는 유지
            system = self._messages[0]
            self._messages = [system] + self._messages[-(max_messages - 1) :]

    async def _process_tool_calls(self, response: dict[str, Any]) -> dict[str, Any]:
        """LLM 응답의 tool_calls를 처리하고 재귀적으로 LLM을 다시 호출합니다.

        최대 _MAX_TOOL_ITERATIONS번까지 반복하며, 도구 호출이 없으면 종료합니다.

        Args:
            response: LLM 응답 딕셔너리 (tool_calls 포함 가능)

        Returns:
            최종 LLM 응답 (텍스트 응답)
        """
        iteration = 0
        current_response = response

        while "tool_calls" in current_response and iteration < self._config.max_tool_iterations:
            iteration += 1
            tool_calls = current_response["tool_calls"]

            # assistant 메시지를 히스토리에 추가 (tool_calls 포함)
            self._messages.append(current_response)

            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "unknown")
                tool_id = tc.get("id", "")

                # 인자 파싱
                raw_args = func.get("arguments", "{}")
                try:
                    arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    arguments = {}

                cli.print_tool_call(tool_name)

                # 도구 실행
                result = await execute_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                    k8s=self._k8s,
                    gitea=self._gitea,
                    files=self._files,
                )

                cli.print_tool_result(tool_name, result, max_chars=self._config.tool_result_max_chars)

                # 도구 결과를 메시지에 추가
                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result,
                    }
                )

            # 도구 결과를 포함하여 LLM 재호출
            self._trim_messages()
            current_response = await self._llm.chat(
                messages=self._messages,
                tools=TOOLS,
            )

        return current_response

    @staticmethod
    def _needs_continuation(response: dict[str, Any]) -> bool:
        """텍스트 응답(tool_calls 없음)이 왔을 때 계속 진행이 필요한지 판단합니다.

        시스템 프롬프트가 "작업 완료 전까지 텍스트 응답 금지"를 지시하므로,
        tool_calls 없이 텍스트가 반환된 경우 작업이 완료된 것으로 간주합니다.
        키워드 휴리스틱은 오탐(false-positive)을 유발하므로 사용하지 않습니다.

        Args:
            response: LLM 응답 딕셔너리

        Returns:
            항상 False (텍스트 응답 = 작업 완료)
        """
        return False

    async def _handle_user_input(self, user_input: str) -> None:
        """사용자 입력을 처리하고 자율 실행 모드로 LLM 응답을 처리합니다.

        LLM이 도구를 호출하는 동안은 자동으로 반복하고,
        텍스트로 응답하더라도 작업이 완료되지 않았으면
        자동으로 계속 진행을 요청합니다.

        Args:
            user_input: 사용자가 입력한 텍스트
        """
        cli.print_user_input(user_input)

        # 사용자 메시지 추가
        self._messages.append({"role": "user", "content": user_input})
        self._trim_messages()

        cli.print_thinking()

        for round_idx in range(self._config.max_auto_continue + 1):
            # LLM 호출
            response = await self._llm.chat(
                messages=self._messages,
                tools=TOOLS,
            )

            # tool_calls가 있으면 모두 처리한 후 최종 응답 받음
            if "tool_calls" in response:
                response = await self._process_tool_calls(response)

            # 텍스트 응답 표시
            content = response.get("content", "")
            if content:
                cli.print_agent_response(content)
                self._messages.append({"role": "assistant", "content": content})
            else:
                cli.print_info("(no response)")
                break

            # 자율 실행 최대 횟수 도달
            if round_idx >= self._config.max_auto_continue:
                break

            # 작업 완료 여부 판단
            if not self._needs_continuation(response):
                break

            # 자동 계속 진행
            round_num = round_idx + 1
            cli.print_auto_continue(round_num, self._config.max_auto_continue)
            self._messages.append({
                "role": "user",
                "content": (
                    "작업을 계속 진행해주세요. 도구를 호출하여 다음 단계를 실행하세요. "
                    "모든 단계가 완료되면 최종 결과를 요약해주세요."
                ),
            })
            self._trim_messages()

    async def run(self) -> None:
        """에이전트 메인 루프를 시작합니다.

        사용자 입력을 받고 LLM과 대화하며 도구를 실행합니다.
        Ctrl+C로 현재 요청을 취소하고, Ctrl+D로 종료합니다.
        """
        cli.print_banner(
            llm_url=self._config.llm_base_url,
            namespace=self._config.kube_namespace,
            gitea_url=self._config.gitea_url,
        )

        # prompt_toolkit 세션 설정
        session: PromptSession[str] = PromptSession(history=InMemoryHistory())

        try:
            while True:
                try:
                    # prompt_toolkit은 동기 함수이므로 executor에서 실행
                    user_input = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: session.prompt("You: "),
                    )

                    # 빈 입력 무시
                    stripped = user_input.strip()
                    if not stripped:
                        continue

                    # 종료 명령어
                    if stripped.lower() in ("exit", "quit", "bye"):
                        cli.print_goodbye()
                        break

                    await self._handle_user_input(stripped)

                except KeyboardInterrupt:
                    # Ctrl+C: 현재 요청 취소
                    cli.print_info("\n(cancelled)")
                    continue

                except EOFError:
                    # Ctrl+D: 종료
                    cli.print_goodbye()
                    break

                except Exception as exc:
                    cli.print_error(f"예기치 않은 오류: {exc}")
                    logger.exception("Agent loop 예외")
                    continue
        finally:
            await self._gitea.close()
