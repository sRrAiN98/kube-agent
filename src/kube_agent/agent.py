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
from kube_agent.context import ContextManager
from kube_agent.file_ops import FileOps
from kube_agent.gitea_ops import GiteaOps
from kube_agent.helm_ops import HelmOps
from kube_agent.kubernetes_ops import KubernetesOps
from kube_agent.llm import SYSTEM_PROMPT, LLMClient
from kube_agent.observability_ops import ObservabilityOps
from kube_agent.safety import assess_risk
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
        self._helm = HelmOps(namespace=config.kube_namespace)
        self._obs = ObservabilityOps(
            prometheus_url=config.prometheus_url,
            loki_url=config.loki_url,
        )
        self._context_mgr = ContextManager(max_messages=config.max_messages or 60)
        self._failed_calls: dict[str, int] = {}
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

    def _trim_messages(self) -> None:
        """컨텍스트 관리자를 통해 오래된 도구 출력을 압축하고 메시지를 최적화합니다."""
        self._messages = self._context_mgr.compact(self._messages)

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

                # 서킷 브레이커: 동일 인자 반복 실패 차단
                call_signature = f"{tool_name}:{raw_args}"
                if self._failed_calls.get(call_signature, 0) >= 3:
                    result = (
                        f"[서킷 브레이커] 동일한 인자의 도구 '{tool_name}' 호출이 3회 연속 실패하여 "
                        "반복 실행을 차단했습니다. 다른 접근 방식을 시도하거나 사용자에게 보고하세요."
                    )
                    cli.print_tool_result(
                        tool_name, result, max_chars=self._config.tool_result_max_chars
                    )
                    self._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result,
                        }
                    )
                    continue

                # 안전 가드레일 검사
                assessment = assess_risk(
                    tool_name=tool_name,
                    arguments=arguments,
                    safety_mode=self._config.safety_mode,
                )
                if assessment.requires_confirmation:
                    if self._config.read_only or self._config.safety_mode == "read_only":
                        result = (
                            f"[Read-Only 차단] 읽기 전용 모드에서는 상태 변경 작업이 금지되어 있습니다 "
                            f"({assessment.reason}). 조회 또는 진단 도구만 사용하세요."
                        )
                        cli.print_tool_result(
                            tool_name, result, max_chars=self._config.tool_result_max_chars
                        )
                        self._messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": result,
                            }
                        )
                        continue

                    cli.print_safety_warning(assessment)
                    confirmed = cli.ask_confirmation()
                    if not confirmed:
                        result = (
                            f"[안전 차단] 사용자가 작업을 거부했습니다 ({assessment.reason}). "
                            "작업을 중단하고 대안을 제안하세요."
                        )
                        cli.print_tool_result(
                            tool_name, result, max_chars=self._config.tool_result_max_chars
                        )
                        self._messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": result,
                            }
                        )
                        continue

                # 도구 실행
                result = await execute_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                    k8s=self._k8s,
                    gitea=self._gitea,
                    files=self._files,
                    helm=self._helm,
                    obs=self._obs,
                )

                # 실패 기록 추적 (서킷 브레이커용)
                res_lower = result.lower()
                if "실패" in result or "오류" in result or "error" in res_lower or "exception" in res_lower:
                    self._failed_calls[call_signature] = self._failed_calls.get(call_signature, 0) + 1
                else:
                    self._failed_calls.pop(call_signature, None)

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

        LLM이 중간 계획이나 다음 작업 예정 사항만 텍스트로 말하고
        도구 호출을 중단한 경우(조기 종료)를 감지하여 자율 계속 진행을 유도합니다.

        Args:
            response: LLM 응답 딕셔너리

        Returns:
            계속 진행 필요 시 True, 작업 완료 시 False
        """
        content = response.get("content", "").strip().lower()
        if not content:
            return False

        # 작업 완료 지표 (이 중 하나라도 있으면 완료된 것으로 간주)
        completion_markers = (
            "완료되었습니다",
            "작업 완료",
            "성공적으로",
            "종료되었습니다",
            "모든 작업이 완료",
            "정상적으로 처리되었습니다",
            "task completed",
            "successfully finished",
            "all steps completed",
        )
        if any(marker in content for marker in completion_markers):
            return False

        # 미완료/진행 예정 지표
        continuation_markers = (
            "다음 단계로",
            "이제 ",
            "이어서 ",
            "진행하겠습니다",
            "수정하겠습니다",
            "실행하겠습니다",
            "확인하겠습니다",
            "next, i will",
            "now proceeding",
            "let's proceed",
            "i will now",
        )
        return any(marker in content for marker in continuation_markers)

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
            started_streaming = False

            def on_token(token: str) -> None:
                nonlocal started_streaming
                if not started_streaming:
                    cli.start_stream_response()
                    started_streaming = True
                cli.print_stream_token(token)

            # LLM 호출 (토큰 스트리밍 연동)
            response = await self._llm.chat(
                messages=self._messages,
                tools=TOOLS,
                on_token=on_token,
            )

            if started_streaming:
                cli.end_stream_response()

            # tool_calls가 있으면 모두 처리한 후 최종 응답 받음
            if "tool_calls" in response:
                response = await self._process_tool_calls(response)

            # 텍스트 응답 표시 (이미 스트리밍되지 않은 경우에만 전체 출력)
            content = response.get("content", "")
            if content:
                if not started_streaming:
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
            prometheus_url=self._config.prometheus_url,
            loki_url=self._config.loki_url,
            read_only=self._config.read_only,
            safety_mode=self._config.safety_mode,
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
            await self._obs.close()
