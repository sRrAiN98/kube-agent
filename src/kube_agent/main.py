"""Entry point for kube-agent CLI.

click을 사용한 CLI 인자 파싱과 에이전트 실행을 담당합니다.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import click

from kube_agent.agent import Agent
from kube_agent.config import AgentConfig


def _setup_logging(verbose: bool) -> None:
    """로깅을 설정합니다.

    Args:
        verbose: True이면 DEBUG 레벨, False이면 WARNING 레벨
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--llm-url",
    "-l",
    default="",
    envvar="KUBE_AGENT_LLM_URL",
    help="LLM API base URL (default: in-cluster LiteLLM endpoint).",
)
@click.option(
    "--llm-model",
    "-m",
    default="",
    envvar="KUBE_AGENT_LLM_MODEL",
    help="LLM model name (default: gpt-4o).",
)
@click.option(
    "--llm-api-key",
    default="",
    envvar="KUBE_AGENT_LLM_API_KEY",
    help="LLM API key.",
)
@click.option(
    "--gitea-url",
    "-g",
    default="",
    envvar="KUBE_AGENT_GITEA_URL",
    help="Gitea server URL.",
)
@click.option(
    "--gitea-token",
    default="",
    envvar="KUBE_AGENT_GITEA_TOKEN",
    help="Gitea API token.",
)
@click.option(
    "--namespace",
    "-n",
    default="",
    envvar="KUBE_AGENT_NAMESPACE",
    help="Kubernetes namespace (default: default).",
)
@click.option(
    "--kube-context",
    default="",
    envvar="KUBE_AGENT_CONTEXT",
    help="Kubernetes context name.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose (debug) logging.",
)
@click.version_option(package_name="kube-agent")
def main(
    llm_url: str,
    llm_model: str,
    llm_api_key: str,
    gitea_url: str,
    gitea_token: str,
    namespace: str,
    kube_context: str,
    verbose: bool,
) -> None:
    """kube-agent: AI assistant for Kubernetes and Gitea management.

    Interactive terminal chat agent that uses an LLM to manage
    Kubernetes clusters and Gitea repositories in offline
    on-premise environments.
    """
    _setup_logging(verbose)

    # 환경 변수에서 기본 설정 로드
    config = AgentConfig.from_env()

    # CLI 인자로 오버라이드 (빈 문자열이 아닌 값만)
    config = config.merge(
        llm_base_url=llm_url,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        gitea_url=gitea_url,
        gitea_token=gitea_token,
        kube_namespace=namespace,
        kube_context=kube_context,
        verbose=verbose,
    )

    # 기본값 적용
    config = config.resolve()

    agent = Agent(config)

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        # 최상위 Ctrl+C 처리
        sys.exit(0)


if __name__ == "__main__":
    main()
