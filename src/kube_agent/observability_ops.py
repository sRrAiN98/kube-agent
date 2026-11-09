"""Observability (Prometheus & Loki) operations for kube-agent.

Prometheus(PromQL) 메트릭 조회 및 Grafana Loki(LogQL) 분산 로그 쿼리를 지원합니다.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ObservabilityOps:
    """Prometheus 및 Loki 관측성 API 연동 클래스."""

    def __init__(
        self,
        prometheus_url: str = "",
        loki_url: str = "",
        timeout: float = 30.0,
    ) -> None:
        """ObservabilityOps 인스턴스를 초기화합니다.

        Args:
            prometheus_url: Prometheus API 엔드포인트 (예: http://prometheus.monitoring:9090)
            loki_url: Loki API 엔드포인트 (예: http://loki-gateway.logging:3100)
            timeout: HTTP 타임아웃(초)
        """
        self._prometheus_url = prometheus_url.rstrip("/")
        self._loki_url = loki_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """HTTP 클라이언트를 해제합니다."""
        await self._client.aclose()

    async def query_prometheus(self, query: str) -> str:
        """Prometheus에 PromQL 인스턴트 쿼리를 전송하고 결과를 반환합니다.

        Args:
            query: PromQL 쿼리 문자열 (예: 'sum(rate(container_cpu_usage_seconds_total[5m])) by (pod)')

        Returns:
            메트릭 결과 요약 문자열
        """
        if not self._prometheus_url:
            return (
                "Prometheus URL이 설정되지 않았습니다.\n"
                "  - CLI: --prometheus-url http://<host>:9090\n"
                "  - 환경변수: KUBE_AGENT_PROMETHEUS_URL\n"
                "  - 설정파일: kube-agent.yaml의 prometheus.url"
            )

        try:
            url = f"{self._prometheus_url}/api/v1/query"
            resp = await self._client.get(url, params={"query": query})
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "success":
                return f"Prometheus 쿼리 실패: {data.get('error', 'unknown error')}"

            result_data = data.get("data", {})
            result_type = result_data.get("resultType", "")
            results = result_data.get("result", [])

            if not results:
                return f"Prometheus 쿼리 결과 없음 (0건 반환)\n  Query: {query}"

            lines = [f"--- Prometheus PromQL 결과: {query} (타입: {result_type}, 건수: {len(results)}) ---"]

            for idx, item in enumerate(results[:30], 1):  # 최대 30개 표시
                metric = item.get("metric", {})
                metric_desc = ", ".join(f"{k}='{v}'" for k, v in metric.items() if k != "__name__")
                metric_name = metric.get("__name__", "")

                label_str = f"{metric_name}{{{metric_desc}}}" if metric_desc else (metric_name or "metric")

                if result_type == "vector":
                    # [timestamp, value]
                    val = item.get("value", [0, ""])[1]
                    lines.append(f"  {idx}. {label_str} = {val}")
                elif result_type == "matrix":
                    values = item.get("values", [])
                    last_val = values[-1][1] if values else "N/A"
                    lines.append(f"  {idx}. {label_str} (샘플 {len(values)}개, 최근값: {last_val})")
                else:
                    lines.append(f"  {idx}. {label_str} = {item}")

            if len(results) > 30:
                lines.append(f"... (외 {len(results) - 30}개 결과 생략)")

            return "\n".join(lines)

        except httpx.HTTPStatusError as exc:
            return f"Prometheus HTTP 오류 ({exc.response.status_code}): {exc.response.text}"
        except Exception as exc:
            logger.error("Prometheus 쿼리 중 오류: %s", exc)
            return f"Prometheus 쿼리 중 오류 발생: {exc}"

    async def query_loki(self, query: str, limit: int = 50) -> str:
        """Grafana Loki에 LogQL 쿼리를 전송하고 로그 라인을 반환합니다.

        Args:
            query: LogQL 쿼리 문자열 (예: '{namespace=\"kube-agent\"} |= \"error\"')
            limit: 가져올 최대 로그 라인 수 (기본 50)

        Returns:
            로그 라인 목록 문자열
        """
        if not self._loki_url:
            return (
                "Loki URL이 설정되지 않았습니다.\n"
                "  - CLI: --loki-url http://<host>:3100\n"
                "  - 환경변수: KUBE_AGENT_LOKI_URL\n"
                "  - 설정파일: kube-agent.yaml의 loki.url"
            )

        try:
            url = f"{self._loki_url}/loki/api/v1/query_range"
            resp = await self._client.get(
                url,
                params={"query": query, "limit": limit, "direction": "backward"},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "success":
                return f"Loki 쿼리 실패: {data.get('error', 'unknown error')}"

            result_data = data.get("data", {})
            streams: list[dict[str, Any]] = result_data.get("result", [])

            if not streams:
                return f"Loki 로그 쿼리 결과 없음 (0건 반환)\n  Query: {query}"

            lines = [f"--- Loki LogQL 결과: {query} (스트림 {len(streams)}개) ---"]
            total_logs = 0

            for stream in streams:
                stream_labels = stream.get("stream", {})
                target_keys = ("app", "pod", "container", "namespace")
                label_summary = " ".join(f"[{k}={v}]" for k, v in stream_labels.items() if k in target_keys)
                lines.append(f"\nStream {label_summary}:")

                entries = stream.get("values", [])
                for ts_ns, log_line in entries[:limit]:
                    total_logs += 1
                    lines.append(f"  {log_line.strip()}")
                    if total_logs >= limit:
                        break
                if total_logs >= limit:
                    break

            return "\n".join(lines)

        except httpx.HTTPStatusError as exc:
            return f"Loki HTTP 오류 ({exc.response.status_code}): {exc.response.text}"
        except Exception as exc:
            logger.error("Loki 쿼리 중 오류: %s", exc)
            return f"Loki 쿼리 중 오류 발생: {exc}"
