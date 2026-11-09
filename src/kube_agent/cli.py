"""Interactive CLI interface for kube-agent.

Rich 라이브러리를 사용한 스타일링된 터미널 출력과
prompt_toolkit을 사용한 인터랙티브 입력을 제공합니다.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# 에이전트 전용 컬러 테마
_THEME = Theme(
    {
        "user": "bold green",
        "agent": "bold blue",
        "tool_name": "bold yellow",
        "tool_result": "yellow",
        "error": "bold red",
        "info": "dim cyan",
        "banner": "bold magenta",
    }
)

# 전역 콘솔 인스턴스
console = Console(theme=_THEME)


def print_banner(
    llm_url: str,
    namespace: str,
    gitea_url: str,
    prometheus_url: str = "",
    loki_url: str = "",
    read_only: bool = False,
    safety_mode: str = "strict",
) -> None:
    """에이전트 시작 배너를 출력합니다.

    Args:
        llm_url: 연결된 LLM 엔드포인트 URL
        namespace: 현재 Kubernetes 네임스페이스
        gitea_url: Gitea 서버 URL
        prometheus_url: Prometheus 서버 URL
        loki_url: Loki 서버 URL
        read_only: 읽기 전용 모드 활성화 여부
        safety_mode: 안전 모드명
    """
    lines = [
        "[banner]-- kube-agent 2.0 (Team Edition) --[/banner]",
        f"[info]Connected to LLM:[/info] {llm_url}",
        f"[info]Namespace:[/info]        {namespace}",
    ]
    if read_only:
        lines.append("[bold red]Mode:[/bold red]             READ-ONLY (모든 상태 변경 차단)")
    else:
        lines.append(f"[info]Safety Mode:[/info]      {safety_mode}")

    if gitea_url:
        lines.append(f"[info]Gitea:[/info]            {gitea_url}")
    if prometheus_url:
        lines.append(f"[info]Prometheus:[/info]       {prometheus_url}")
    if loki_url:
        lines.append(f"[info]Loki:[/info]             {loki_url}")

    lines.append("")
    lines.append("[dim]Type your message and press Enter. Ctrl+C to cancel, Ctrl+D to exit.[/dim]")

    console.print()
    for line in lines:
        console.print(line)
    console.print()


def print_user_input(text: str) -> None:
    """사용자 입력을 스타일링하여 출력합니다.

    Args:
        text: 사용자가 입력한 텍스트
    """
    console.print()
    console.print(Text("You: ", style="user"), end="")
    console.print(text)


def print_thinking() -> None:
    """LLM 응답 대기 중임을 표시합니다."""
    console.print()
    console.print("[info]Thinking...[/info]")


def print_agent_response(content: str) -> None:
    """LLM 응답을 마크다운으로 렌더링하여 출력합니다.

    Args:
        content: LLM이 생성한 텍스트 응답
    """
    if not content:
        return
    console.print()
    console.print(Text("Agent: ", style="agent"), end="")
    # 마크다운 렌더링 시도, 실패하면 일반 텍스트
    try:
        console.print(Markdown(content))
    except Exception:
        console.print(content)


def start_stream_response() -> None:
    """실시간 스트리밍 응답 헤더를 출력합니다."""
    console.print()
    console.print(Text("Agent: ", style="agent"), end="")


def print_stream_token(token: str) -> None:
    """실시간 스트리밍 토큰을 콘솔에 즉시 출력합니다.

    Args:
        token: 수신된 단일 토큰/텍스트 조각
    """
    console.print(token, end="")


def end_stream_response() -> None:
    """실시간 스트리밍 응답 출력을 마감합니다."""
    console.print()


def print_tool_call(tool_name: str) -> None:
    """도구 호출을 표시합니다.

    Args:
        tool_name: 호출할 도구 이름
    """
    console.print()
    console.print(f"[tool_name]Tool: {tool_name}[/tool_name]")


def print_tool_result(tool_name: str, result: str, max_chars: int = 3000) -> None:
    """도구 실행 결과를 패널로 출력합니다.

    Args:
        tool_name: 실행된 도구 이름
        result: 도구 실행 결과 문자열
        max_chars: 최대 표시 글자 수 (기본: 3000)
    """
    # 결과가 너무 길면 잘라서 표시
    display_result = result if len(result) <= max_chars else result[:max_chars] + "\n... (truncated)"
    panel = Panel(
        display_result,
        title=f"[tool_name]{tool_name}[/tool_name]",
        border_style="yellow",
        expand=False,
    )
    console.print(panel)


def print_error(message: str) -> None:
    """오류 메시지를 출력합니다.

    Args:
        message: 오류 메시지
    """
    console.print(f"[error]Error: {message}[/error]")


def print_info(message: str) -> None:
    """정보 메시지를 출력합니다.

    Args:
        message: 정보 메시지
    """
    console.print(f"[info]{message}[/info]")


def print_goodbye() -> None:
    """종료 메시지를 출력합니다."""
    console.print()
    console.print("[banner]Goodbye![/banner]")
    console.print()


def print_auto_continue(round_num: int, max_rounds: int) -> None:
    """자율 실행 모드에서 계속 진행 중임을 표시합니다.

    Args:
        round_num: 현재 자율 실행 라운드 번호 (1-indexed)
        max_rounds: 최대 자율 실행 라운드 수
    """
    console.print()
    console.print(f"[info](자율 실행 중... {round_num}/{max_rounds})[/info]")


def print_safety_warning(assessment: Any) -> None:
    """도구 실행 안전 경고를 출력합니다.

    Args:
        assessment: RiskAssessment 객체
    """
    border = "red" if getattr(assessment, "level", "") == "DESTRUCTIVE" else "yellow"
    title = f"[bold red]SAFETY WARNING: {getattr(assessment, 'level', 'UNKNOWN')}[/bold red]"
    panel = Panel(
        f"[bold]Tool:[/bold] {getattr(assessment, 'tool_name', '')}\n"
        f"[bold]Reason:[/bold] {getattr(assessment, 'reason', '')}",
        title=title,
        border_style=border,
    )
    console.print()
    console.print(panel)


def ask_confirmation(prompt_text: str = "위 작업을 계속 진행하시겠습니까? (y/N): ") -> bool:
    """사용자에게 작업 진행 여부를 확인합니다.

    Args:
        prompt_text: 사용자에게 표시할 확인 프롬프트

    Returns:
        승인 시 True, 거부 또는 취소 시 False
    """
    try:
        console.print(f"[bold yellow]{prompt_text}[/bold yellow]", end="")
        ans = input().strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
