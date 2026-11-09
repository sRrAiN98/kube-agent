"""Realtime Server mode for kube-agent (REST API & Alert Webhook).

외부 시스템(웹 대시보드, 슬랙 봇, Alertmanager, CI/CD 등)이 실시간으로
LLM 에이전트 엔드포인트를 호출하고 클러스터 진단 및 자동 복구를 요청할 수 있는 API 서버입니다.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from aiohttp.web import AppKey

from kube_agent.agent import Agent
from kube_agent.config import AgentConfig
from kube_agent.kubernetes_ops import KubernetesOps

logger = logging.getLogger(__name__)

AGENT_KEY = AppKey("agent", Agent)
CONFIG_KEY = AppKey("config", AgentConfig)
K8S_KEY = AppKey("k8s", KubernetesOps)


def create_app(config: AgentConfig) -> web.Application:
    """kube-agent REST API 및 Webhook 핸들러가 포함된 aiohttp 애플리케이션을 생성합니다."""
    app = web.Application()
    agent = Agent(config)
    k8s = KubernetesOps(namespace=config.kube_namespace, context=config.kube_context)

    app[AGENT_KEY] = agent
    app[CONFIG_KEY] = config
    app[K8S_KEY] = k8s

    async def handle_healthz(request: web.Request) -> web.Response:
        """서버 상태 확인 엔드포인트."""
        return web.json_response({
            "status": "ok",
            "service": "kube-agent",
            "version": "0.2.0",
            "namespace": config.kube_namespace,
            "safety_mode": config.safety_mode,
            "read_only": config.read_only,
            "prometheus_url": bool(config.prometheus_url),
            "loki_url": bool(config.loki_url),
            "gitea_url": bool(config.gitea_url),
        })

    async def handle_chat(request: web.Request) -> web.Response:
        """외부 솔루션이 자연어 작업을 요청하는 실시간 에이전트 엔드포인트.

        Request Body JSON:
            - prompt (필수): 에이전트에게 내릴 작업 지시
            - namespace (선택): 작업 대상 네임스페이스
        """
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "유효한 JSON 요청이 아닙니다."}, status=400)

        prompt = body.get("prompt", "").strip()
        if not prompt:
            return web.json_response({"status": "error", "message": "'prompt' 필드가 필요합니다."}, status=400)

        logger.info("API Chat 요청 수신: %s", prompt[:80])
        try:
            agent = request.app[AGENT_KEY]
            response_text = await agent.execute_prompt(prompt)
            return web.json_response({
                "status": "success",
                "prompt": prompt,
                "response": response_text,
            })
        except Exception as exc:
            logger.exception("Chat 처리 중 예외 발생")
            return web.json_response({
                "status": "error",
                "message": f"에이전트 실행 중 오류: {exc}",
            }, status=500)

    async def handle_diagnose(request: web.Request) -> web.Response:
        """원클릭 클러스터 정밀 진단 엔드포인트."""
        target_ns = config.kube_namespace
        if request.can_read_body:
            try:
                body = await request.json()
                target_ns = body.get("namespace") or target_ns
            except Exception:
                pass

        query_ns = request.query.get("namespace")
        if query_ns:
            target_ns = query_ns

        try:
            k8s = request.app[K8S_KEY]
            report = k8s.diagnose_cluster(namespace=target_ns)
            return web.json_response({
                "status": "success",
                "namespace": target_ns,
                "report": report,
            })
        except Exception as exc:
            logger.exception("진단 처리 중 예외 발생")
            return web.json_response({
                "status": "error",
                "message": f"진단 실행 중 오류: {exc}",
            }, status=500)

    async def handle_webhook(request: web.Request) -> web.Response:
        """Prometheus Alertmanager 또는 Grafana Webhook 수신 엔드포인트.

        발생한 경보를 분석하여 관련 파드의 로그, 상태, 이벤트를 에이전트가
        자동으로 진단하고 분석 리포트를 생성합니다.
        """
        try:
            payload: dict[str, Any] = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "유효한 JSON 페이로드가 아닙니다."}, status=400)

        alerts = payload.get("alerts", [])
        if not alerts and "alertname" in payload:
            alerts = [payload]

        if not alerts:
            return web.json_response({
                "status": "ignored",
                "message": "처리할 활성 alert 항목이 없습니다.",
            })

        alert_summaries: list[str] = []
        for alert in alerts:
            status = alert.get("status", "firing")
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            name = labels.get("alertname", "UnknownAlert")
            ns = labels.get("namespace", config.kube_namespace)
            pod = labels.get("pod", "N/A")
            desc = annotations.get("description") or annotations.get("summary") or "설명 없음"

            alert_summaries.append(
                f"- [상태: {status}] 경보명: '{name}', Namespace: '{ns}', Pod: '{pod}' (내용: {desc})"
            )

        investigation_prompt = (
            "[Alertmanager 웹훅 경보 수신]\n"
            "시스템에서 다음과 같은 장애/이상 징후 경보가 발령되었습니다:\n"
            + "\n".join(alert_summaries)
            + "\n\n위 경보의 원인을 Kubernetes 상태 조회, Pod 로그 확인, Prometheus/Loki 쿼리를 통해 "
            "원인을 진단하고 즉각적인 조치 방안을 제시해주세요."
        )

        logger.info("Alertmanager 웹훅 분석 시작 (%d건 경보)", len(alerts))
        try:
            agent = request.app[AGENT_KEY]
            analysis_result = await agent.execute_prompt(investigation_prompt)
            return web.json_response({
                "status": "success",
                "alerts_processed": len(alerts),
                "analysis": analysis_result,
            })
        except Exception as exc:
            logger.exception("Webhook 분석 중 예외 발생")
            return web.json_response({
                "status": "error",
                "message": f"경보 분석 중 오류: {exc}",
            }, status=500)

    async def on_cleanup(app_instance: web.Application) -> None:
        """앱 종료 시 외부 세션 리소스 정리."""
        await app_instance[AGENT_KEY].close()

    app.router.add_get("/healthz", handle_healthz)
    app.router.add_get("/api/v1/health", handle_healthz)
    app.router.add_post("/api/v1/chat", handle_chat)
    app.router.add_get("/api/v1/diagnose", handle_diagnose)
    app.router.add_post("/api/v1/diagnose", handle_diagnose)
    app.router.add_post("/api/v1/webhook", handle_webhook)

    app.on_cleanup.append(on_cleanup)
    return app


def run_server(config: AgentConfig, host: str = "0.0.0.0", port: int = 8080) -> None:
    """실시간 API 서버를 실행합니다."""
    app = create_app(config)
    logger.info("kube-agent 실시간 서버 시작 (http://%s:%d)", host, port)
    web.run_app(app, host=host, port=port)
