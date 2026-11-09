"""Batch mode for kube-agent (AI Cost-Optimized Continuous Reporting & Auto-Remediation).

AI 토큰 사용량을 최소화하기 위해 룰 기반 사전 검증(Zero-Token Pre-flight)을 먼저 수행하고,
장애(CrashLoopBackOff, OOMKilled, Pending, Warning 이벤트 등)가 탐지된 경우에만
선별적으로 LLM을 호출하여 근본 원인 분석(RCA) 및 자동 복구(Auto-Remediation)를 진행합니다.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from pathlib import Path
from typing import Any

from rich.console import Console

from kube_agent.agent import Agent
from kube_agent.config import AgentConfig
from kube_agent.kubernetes_ops import KubernetesOps

logger = logging.getLogger(__name__)
console = Console()


async def run_batch_once(
    config: AgentConfig,
    report_dir: Path,
    auto_fix: bool = False,
    namespace: str = "",
) -> dict[str, Any]:
    """배치 점검을 1회 실행하고 리포트를 생성합니다 (AI 토큰 비용 최적화).

    1. 사전 검증 (Zero-Token Heuristic Check):
       Kubernetes API를 통해 장애 Pod 및 Warning 이벤트를 탐색합니다.
       비용: $0 (LLM 호출 0회).
    2. 클러스터 정상 시:
       LLM 호출을 즉시 생략하고 정상 상태 리포트를 생성·저장합니다.
    3. 장애 탐지 시:
       선별적으로 LLM을 호출하여 근본 원인을 심층 분석하고, auto_fix 설정 시
       안전 복구를 자율 실행한 뒤 종합 조치 리포트를 생성합니다.

    Args:
        config: 에이전트 설정
        report_dir: 리포트를 저장할 디렉토리 경로
        auto_fix: True이면 안전 가드레일 내에서 자동 복구 시도
        namespace: 점검할 네임스페이스 (기본값: config 설정)

    Returns:
        점검 결과 요약 딕셔너리
    """
    target_ns = namespace or config.kube_namespace
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    now_iso = datetime.datetime.now().isoformat()

    k8s = KubernetesOps(namespace=target_ns, context=config.kube_context)

    console.print(f"[cyan][Batch][/cyan] 사전 점검 시작 (Namespace: '{target_ns}', Zero-Token Check)...")

    # 1. 룰 기반 클러스터 무비용 진단 실행
    raw_report = k8s.diagnose_cluster(namespace=target_ns)

    is_healthy = "모든 Pod가 정상(Running/Ready) 상태이며 탐지된 장애가 없습니다" in raw_report

    if is_healthy:
        # 정상 상태: AI 호출 0회 (비용 0원)
        console.print("[green][Batch] 클러스터 정상 상태 확인 (AI 토큰 사용량: 0 tokens, 비용 $0.00)[/green]")

        report_content = (
            f"# [Kube-Agent Cluster Health Report]\n\n"
            f"- **Timestamp**: `{now_iso}`\n"
            f"- **Namespace**: `{target_ns}`\n"
            f"- **Status**: `HEALTHY (정상)`\n"
            f"- **AI Token Usage**: `0 tokens` (Zero-Token Heuristic)\n"
            f"- **Auto-Fix**: `N/A`\n\n"
            f"## 클러스터 점검 결과\n"
            f"```text\n{raw_report}\n```\n\n"
            f"---\n*Generated autonomously by kube-agent Batch Engine*\n"
        )

        report_file = report_dir / f"health-report-{timestamp_str}.md"
        report_file.write_text(report_content, encoding="utf-8")

        latest_file = report_dir / "latest.md"
        latest_file.write_text(report_content, encoding="utf-8")

        return {
            "status": "healthy",
            "namespace": target_ns,
            "ai_called": False,
            "report_path": str(report_file),
            "summary": "모든 Pod가 정상 상태입니다.",
        }

    # 2. 장애 탐지: LLM 호출 및 근본 원인 분석/조치
    console.print("[bold red][Batch] 장애 의심 Pod 탐지! 선별적 AI 정밀 분석을 호출합니다...[/bold red]")

    fix_guidance = (
        "안전 모드가 허용하는 범위 내에서 필요한 경우 Deployment 롤링 재시작이나 파드 복구를 직접 시도하세요."
        if (auto_fix and not config.read_only)
        else "조치에 필요한 정확한 kubectl 및 helm 명령어를 명시하세요 (자동 복구 미적용 모드)."
    )

    prompt = (
        f"[배치 자동 점검 시스템 장애 리포트]\n"
        f"네임스페이스 '{target_ns}'에서 다음과 같은 비정상 Pod 및 경고 이벤트가 탐지되었습니다:\n\n"
        f"```text\n{raw_report}\n```\n\n"
        f"지침:\n"
        f"1. 문제가 있는 Pod의 로그 및 상태를 파악하여 근본 원인(Root Cause)을 정확히 규명하세요.\n"
        f"2. {fix_guidance}\n"
        f"3. 최종 리포트에 '1) 원인 분석', '2) 조치 결과 또는 권장 조치 절차', '3) 재발 방지 대책'을 "
        f"포함하여 깔끔하게 정리해주세요."
    )

    agent = Agent(config)
    try:
        ai_response = await agent.execute_prompt(prompt)
    finally:
        await agent.close()

    report_content = (
        f"# [Kube-Agent Incident & Remediation Report]\n\n"
        f"- **Timestamp**: `{now_iso}`\n"
        f"- **Namespace**: `{target_ns}`\n"
        f"- **Status**: `ANOMALY DETECTED (장애 분석 완료)`\n"
        f"- **AI Analysis**: `Invoked`\n"
        f"- **Auto-Fix Enabled**: `{auto_fix and not config.read_only}`\n\n"
        f"## 1. 사전 진단 결과\n"
        f"```text\n{raw_report}\n```\n\n"
        f"## 2. AI 근본 원인 분석 및 복구 권고안\n\n"
        f"{ai_response}\n\n"
        f"---\n*Generated autonomously by kube-agent Batch Engine*\n"
    )

    incident_file = report_dir / f"incident-report-{timestamp_str}.md"
    incident_file.write_text(report_content, encoding="utf-8")

    latest_file = report_dir / "latest.md"
    latest_file.write_text(report_content, encoding="utf-8")

    console.print(f"[yellow][Batch] 장애 분석 리포트 저장 완료: {incident_file}[/yellow]")

    return {
        "status": "anomaly_detected",
        "namespace": target_ns,
        "ai_called": True,
        "auto_fix": auto_fix and not config.read_only,
        "report_path": str(incident_file),
        "summary": ai_response[:200],
    }


async def run_batch_loop(
    config: AgentConfig,
    report_dir: Path,
    interval: int,
    auto_fix: bool = False,
    namespace: str = "",
) -> None:
    """정해진 주기(초)마다 배치 점검을 반복 실행하는 데몬 루프입니다."""
    console.print(
        f"[bold green]kube-agent 배치 모니터링 데몬 가동[/bold green] "
        f"(주기: {interval}초, 리포트 저장소: {report_dir}, auto_fix: {auto_fix})"
    )

    while True:
        try:
            await run_batch_once(
                config=config,
                report_dir=report_dir,
                auto_fix=auto_fix,
                namespace=namespace,
            )
        except Exception as exc:
            logger.exception("배치 점검 실행 중 오류")
            console.print(f"[red][Batch 오류] {exc}[/red]")

        console.print(f"[dim]다음 점검까지 {interval}초 대기... (종료: Ctrl+C)[/dim]")
        await asyncio.sleep(interval)

