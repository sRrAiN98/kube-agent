"""Entry point for kube-agent CLI.

click을 사용한 CLI 인자 파싱과 에이전트 실행을 담당합니다.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

import click

from kube_agent.agent import Agent
from kube_agent.config import AgentConfig, find_config_file


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
    "--config",
    "-c",
    "config_path",
    default="",
    envvar="KUBE_AGENT_CONFIG",
    help="Path to YAML configuration file (e.g. ./kube-agent.yaml).",
)
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
    help="Kubernetes namespace (default: auto-detected or 'default').",
)
@click.option(
    "--kube-context",
    default="",
    envvar="KUBE_AGENT_CONTEXT",
    help="Kubernetes context name.",
)
@click.option(
    "--prometheus-url",
    default="",
    envvar="KUBE_AGENT_PROMETHEUS_URL",
    help="Prometheus server URL for metrics queries.",
)
@click.option(
    "--loki-url",
    default="",
    envvar="KUBE_AGENT_LOKI_URL",
    help="Grafana Loki server URL for log queries.",
)
@click.option(
    "--read-only",
    is_flag=True,
    default=False,
    help="Enable read-only mode to prevent any cluster or repo state mutations.",
)
@click.option(
    "--safety-mode",
    type=click.Choice(["strict", "permissive", "disabled", "read_only"], case_sensitive=False),
    default="",
    envvar="KUBE_AGENT_SAFETY_MODE",
    help="Safety guardrail evaluation mode.",
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
    config_path: str,
    llm_url: str,
    llm_model: str,
    llm_api_key: str,
    gitea_url: str,
    gitea_token: str,
    namespace: str,
    kube_context: str,
    prometheus_url: str,
    loki_url: str,
    read_only: bool,
    safety_mode: str,
    verbose: bool,
) -> None:
    """kube-agent: AI assistant for Kubernetes, Gitea, and Observability.

    Interactive terminal chat agent that uses an LLM to manage
    Kubernetes clusters, Gitea repositories, and Prometheus/Loki in
    both local workstations and on-premise Kubernetes environments.
    """
    _setup_logging(verbose)

    # 1. YAML 설정 파일 탐색 및 로드
    cfg_file = find_config_file(config_path)
    if cfg_file:
        base_config = AgentConfig.from_yaml(cfg_file)
        # 환경변수로 오버라이드
        env_config = AgentConfig.from_env()
        env_updates = {k: v for k, v in env_config.to_dict().items() if v}
        base_config = base_config.merge(**env_updates)
    else:
        base_config = AgentConfig.from_env()

    # 2. CLI 인자로 오버라이드 (지정된 값만)
    overrides: dict[str, Any] = {
        "llm_base_url": llm_url,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "gitea_url": gitea_url,
        "gitea_token": gitea_token,
        "kube_namespace": namespace,
        "kube_context": kube_context,
        "prometheus_url": prometheus_url,
        "loki_url": loki_url,
        "safety_mode": safety_mode,
        "read_only": read_only if read_only else None,
        "verbose": verbose if verbose else None,
    }
    cli_overrides = {k: v for k, v in overrides.items() if v not in ("", None)}
    config = base_config.merge(**cli_overrides)

    # 3. 기본값 적용
    config = config.resolve()

    agent = Agent(config)

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        # 최상위 Ctrl+C 처리
        sys.exit(0)


if __name__ == "__main__":
    main()
