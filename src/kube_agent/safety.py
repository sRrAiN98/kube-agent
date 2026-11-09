"""도구 실행 안전성 평가 및 가드레일 모듈.

에이전트가 실행하려는 도구의 위험도(SAFE, SENSITIVE, DESTRUCTIVE)를 분석하고,
파괴적 명령 실행 전 사용자 승인 또는 정책 기반 차단을 수행합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    """도구 실행 위험도 등급."""

    SAFE = "SAFE"                # 단순 조회 및 무해한 읽기 전용 작업
    SENSITIVE = "SENSITIVE"      # 파일 생성/수정, 재시작 등 일반적인 변경 작업
    DESTRUCTIVE = "DESTRUCTIVE"  # 리소스 삭제, 서비스 중단(replicas=0) 등 파괴적 작업


@dataclass(frozen=True)
class RiskAssessment:
    """도구 호출에 대한 위험도 평가 결과."""

    level: RiskLevel
    tool_name: str
    reason: str
    requires_confirmation: bool


# 기본 읽기 전용 도구 목록 (SAFE)
_SAFE_TOOLS = frozenset({
    "k8s_list_pods",
    "k8s_get_pod",
    "k8s_get_pod_logs",
    "k8s_list_deployments",
    "k8s_get_deployment",
    "k8s_list_services",
    "k8s_list_configmaps",
    "k8s_get_configmap",
    "k8s_list_secrets",
    "k8s_get_events",
    "gitea_list_repos",
    "gitea_get_repo",
    "gitea_list_branches",
    "gitea_list_users",
    "gitea_list_webhooks",
    "gitea_git_status",
    "file_list",
    "file_read",
    "helm_list",
    "helm_status",
    "helm_lint",
    "helm_template",
})


def assess_risk(
    tool_name: str,
    arguments: dict[str, Any],
    safety_mode: str = "strict",
) -> RiskAssessment:
    """도구 호출의 인자를 분석하여 위험도를 평가합니다.

    Args:
        tool_name: 호출할 도구 이름
        arguments: 도구 인자 딕셔너리
        safety_mode: 안전 모드 ("strict", "permissive", "disabled")

    Returns:
        RiskAssessment 평가 결과 객체
    """
    if safety_mode == "disabled":
        return RiskAssessment(
            level=RiskLevel.SAFE,
            tool_name=tool_name,
            reason="안전 모드가 비활성화되어 있습니다.",
            requires_confirmation=False,
        )

    # 1. 명시적 DESTRUCTIVE 도구
    if tool_name == "gitea_delete_repo":
        owner = arguments.get("owner", "unknown")
        repo = arguments.get("name", "unknown")
        return RiskAssessment(
            level=RiskLevel.DESTRUCTIVE,
            tool_name=tool_name,
            reason=f"Gitea 저장소 '{owner}/{repo}'를 영구 삭제합니다. 복구할 수 없습니다.",
            requires_confirmation=True,
        )

    # 2. 인자 조건에 따른 DESTRUCTIVE 판별 (예: replicas=0)
    if tool_name == "k8s_scale_deployment":
        replicas = arguments.get("replicas", 1)
        name = arguments.get("name", "unknown")
        if replicas == 0:
            return RiskAssessment(
                level=RiskLevel.DESTRUCTIVE,
                tool_name=tool_name,
                reason=f"Deployment '{name}'의 레플리카를 0으로 설정하여 서비스를 전면 중단합니다.",
                requires_confirmation=True,
            )
        return RiskAssessment(
            level=RiskLevel.SENSITIVE,
            tool_name=tool_name,
            reason=f"Deployment '{name}'의 레플리카를 {replicas}개로 변경합니다.",
            requires_confirmation=(safety_mode == "strict"),
        )

    # 3. SAFE 도구 검사
    if tool_name in _SAFE_TOOLS:
        return RiskAssessment(
            level=RiskLevel.SAFE,
            tool_name=tool_name,
            reason="읽기 전용 무해한 조회 작업입니다.",
            requires_confirmation=False,
        )

    # 4. 그 외 상태 변경 작업 (SENSITIVE)
    reason = f"시스템 상태를 변경하는 작업입니다: {tool_name}"
    req_confirm = (safety_mode == "strict")

    return RiskAssessment(
        level=RiskLevel.SENSITIVE,
        tool_name=tool_name,
        reason=reason,
        requires_confirmation=req_confirm,
    )
