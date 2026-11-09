"""Entry point for kube-agent CLI.

3가지 실행 모드를 지원합니다:
1. 대화형 인터랙티브 셸 (기본 모드): `kube-agent` 또는 `kube-agent chat`
2. 실시간 솔루션 연동 서버 (REST API & Alert Webhook): `kube-agent serve`
3. AI 비용 최적화 지속적 점검 및 자동 복구 배치: `kube-agent batch`
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import click

from kube_agent.agent import Agent
from kube_agent.batch import run_batch_loop, run_batch_once
from kube_agent.config import AgentConfig, find_config_file
from kube_agent.server import run_server


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


def _build_config(
    config_path: str = "",
    llm_url: str = "",
    llm_model: str = "",
    llm_api_key: str = "",
    gitea_url: str = "",
    gitea_token: str = "",
    namespace: str = "",
    kube_context: str = "",
    prometheus_url: str = "",
    loki_url: str = "",
    read_only: bool = False,
    safety_mode: str = "",
    verbose: bool = False,
) -> AgentConfig:
    """YAML 설정, 환경 변수, CLI 플래그를 통합하여 확정된 AgentConfig를 생성합니다."""
    _setup_logging(verbose)

    # 1. YAML 설정 파일 로드
    cfg_file = find_config_file(config_path)
    if cfg_file:
        base_config = AgentConfig.from_yaml(cfg_file)
        env_config = AgentConfig.from_env()
        env_updates = {k: v for k, v in env_config.to_dict().items() if v}
        base_config = base_config.merge(**env_updates)
    else:
        base_config = AgentConfig.from_env()

    # 2. CLI 오버라이드
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
    return config.resolve()


def common_options(f: Any) -> Any:
    """공통 에이전트 설정 CLI 옵션 데코레이터."""
    options = [
        click.option(
            "--config",
            "-c",
            "config_path",
            default="",
            envvar="KUBE_AGENT_CONFIG",
            help="Path to YAML configuration file (e.g. ./kube-agent.yaml).",
        ),
        click.option(
            "--llm-url",
            "-l",
            default="",
            envvar="KUBE_AGENT_LLM_URL",
            help="LLM API base URL (default: in-cluster LiteLLM endpoint).",
        ),
        click.option(
            "--llm-model",
            "-m",
            default="",
            envvar="KUBE_AGENT_LLM_MODEL",
            help="LLM model name (default: gpt-4o).",
        ),
        click.option(
            "--llm-api-key",
            default="",
            envvar="KUBE_AGENT_LLM_API_KEY",
            help="LLM API key.",
        ),
        click.option(
            "--gitea-url",
            "-g",
            default="",
            envvar="KUBE_AGENT_GITEA_URL",
            help="Gitea server URL.",
        ),
        click.option(
            "--gitea-token",
            default="",
            envvar="KUBE_AGENT_GITEA_TOKEN",
            help="Gitea API token.",
        ),
        click.option(
            "--namespace",
            "-n",
            default="",
            envvar="KUBE_AGENT_NAMESPACE",
            help="Kubernetes namespace (default: auto-detected or 'default').",
        ),
        click.option(
            "--kube-context",
            default="",
            envvar="KUBE_AGENT_CONTEXT",
            help="Kubernetes context name.",
        ),
        click.option(
            "--prometheus-url",
            default="",
            envvar="KUBE_AGENT_PROMETHEUS_URL",
            help="Prometheus server URL for metrics queries.",
        ),
        click.option(
            "--loki-url",
            default="",
            envvar="KUBE_AGENT_LOKI_URL",
            help="Grafana Loki server URL for log queries.",
        ),
        click.option(
            "--read-only",
            is_flag=True,
            default=False,
            help="Enable read-only mode to prevent any cluster or repo state mutations.",
        ),
        click.option(
            "--safety-mode",
            type=click.Choice(["strict", "permissive", "disabled", "read_only"], case_sensitive=False),
            default="",
            envvar="KUBE_AGENT_SAFETY_MODE",
            help="Safety guardrail evaluation mode.",
        ),
        click.option(
            "--verbose",
            "-v",
            is_flag=True,
            default=False,
            help="Enable verbose (debug) logging.",
        ),
    ]
    for opt in reversed(options):
        f = opt(f)
    return f


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
@common_options
@click.version_option(package_name="kube-agent")
def main(
    ctx: click.Context,
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

    하위 명령 없이 실행 시 대화형 터미널 챗 모드로 진입합니다.
    - `kube-agent` : 대화형 터미널 챗 (기본)
    - `kube-agent serve` : 실시간 REST API 및 Alert Webhook 데몬 서버
    - `kube-agent batch` : AI 토큰 절감형 지속적 헬스 체크 및 자동 복구 배치
    """
    ctx.ensure_object(dict)
    ctx.obj["config_args"] = {
        "config_path": config_path,
        "llm_url": llm_url,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "gitea_url": gitea_url,
        "gitea_token": gitea_token,
        "namespace": namespace,
        "kube_context": kube_context,
        "prometheus_url": prometheus_url,
        "loki_url": loki_url,
        "read_only": read_only,
        "safety_mode": safety_mode,
        "verbose": verbose,
    }

    if ctx.invoked_subcommand is None:
        # 하위 명령어가 없으면 기본 대화형 챗 셸 실행
        config = _build_config(**ctx.obj["config_args"])
        agent = Agent(config)
        try:
            asyncio.run(agent.run())
        except KeyboardInterrupt:
            sys.exit(0)


@main.command("chat")
@click.pass_context
def chat_cmd(ctx: click.Context) -> None:
    """대화형 인터랙티브 챗 터미널을 실행합니다."""
    config = _build_config(**ctx.obj["config_args"])
    agent = Agent(config)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        sys.exit(0)


@main.command("serve")
@click.pass_context
@click.option("--host", "-H", default="0.0.0.0", envvar="KUBE_AGENT_HOST", help="Server bind host (default: 0.0.0.0).")
@click.option("--port", "-p", default=8080, type=int, envvar="KUBE_AGENT_PORT", help="Server port (default: 8080).")
def serve_cmd(ctx: click.Context, host: str, port: int) -> None:
    """외부 솔루션 연동을 위한 실시간 REST API 및 Webhook 서버를 실행합니다.

    엔드포인트:
    - GET  /healthz        : 서버 헬스체크
    - POST /api/v1/chat    : 실시간 에이전트 질의/수행 요청
    - POST /api/v1/diagnose: 원클릭 클러스터 정밀 진단
    - POST /api/v1/webhook : Prometheus Alertmanager / Grafana Webhook 수신 분석
    """
    config = _build_config(**ctx.obj["config_args"])
    run_server(config, host=host, port=port)


@main.command("batch")
@click.pass_context
@click.option(
    "--report-dir",
    "-r",
    default="./reports",
    envvar="KUBE_AGENT_REPORT_DIR",
    help="Directory to store markdown/json health reports (default: ./reports).",
)
@click.option(
    "--interval",
    "-i",
    default=0,
    type=int,
    envvar="KUBE_AGENT_BATCH_INTERVAL",
    help="Interval in seconds for continuous daemon loop (0 = run once and exit).",
)
@click.option(
    "--auto-fix",
    is_flag=True,
    default=False,
    envvar="KUBE_AGENT_AUTO_FIX",
    help="Attempt autonomous safe remediation when issues are detected (unless read-only).",
)
def batch_cmd(ctx: click.Context, report_dir: str, interval: int, auto_fix: bool) -> None:
    """AI 토큰 비용 절감형 지속적 헬스 체크 및 자동 복구 배치를 실행합니다.

    정상 상태 시: 룰 기반 검증으로 AI 토큰 소비 0회 ($0.00).
    장애 발생 시: 선별적 LLM 호출로 근본 원인 분석(RCA) 및 복구 리포트 생성.
    """
    config = _build_config(**ctx.obj["config_args"])
    rep_path = Path(report_dir).expanduser().resolve()

    if interval > 0:
        try:
            asyncio.run(
                run_batch_loop(
                    config=config,
                    report_dir=rep_path,
                    interval=interval,
                    auto_fix=auto_fix,
                    namespace=config.kube_namespace,
                )
            )
        except KeyboardInterrupt:
            click.echo("\n[Batch] 모니터링 종료.")
            sys.exit(0)
    else:
        result = asyncio.run(
            run_batch_once(
                config=config,
                report_dir=rep_path,
                auto_fix=auto_fix,
                namespace=config.kube_namespace,
            )
        )
        if result["status"] == "healthy":
            sys.exit(0)
        else:
            sys.exit(1 if not auto_fix else 0)


if __name__ == "__main__":
    main()
