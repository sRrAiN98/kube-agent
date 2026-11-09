"""Unit tests for ObservabilityOps (Prometheus & Loki integration)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from kube_agent.observability_ops import ObservabilityOps


@pytest.mark.asyncio
async def test_prom_url_not_configured():
    obs = ObservabilityOps(prometheus_url="")
    try:
        res = await obs.query_prometheus("up")
        assert "Prometheus URL이 설정되지 않았습니다" in res
    finally:
        await obs.close()


@pytest.mark.asyncio
async def test_loki_url_not_configured():
    obs = ObservabilityOps(loki_url="")
    try:
        res = await obs.query_loki('{app="test"}')
        assert "Loki URL이 설정되지 않았습니다" in res
    finally:
        await obs.close()


@pytest.mark.asyncio
async def test_prom_query_vector_success():
    obs = ObservabilityOps(prometheus_url="http://prom:9090")
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"__name__": "up", "instance": "k8s-node-1", "job": "node"},
                    "value": [1700000000, "1"],
                }
            ],
        },
    }

    obs._client.get = AsyncMock(return_value=fake_response)
    try:
        res = await obs.query_prometheus("up")
        assert "Prometheus PromQL 결과: up" in res
        assert "up{instance='k8s-node-1', job='node'} = 1" in res
    finally:
        await obs.close()


@pytest.mark.asyncio
async def test_prom_query_matrix_success():
    obs = ObservabilityOps(prometheus_url="http://prom:9090")
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"__name__": "cpu_usage", "pod": "api-1"},
                    "values": [[1700000000, "0.15"], [1700000060, "0.22"]],
                }
            ],
        },
    }

    obs._client.get = AsyncMock(return_value=fake_response)
    try:
        res = await obs.query_prometheus("cpu_usage[2m]")
        assert "타입: matrix" in res
        assert "최근값: 0.22" in res
    finally:
        await obs.close()


@pytest.mark.asyncio
async def test_prom_query_failure_status():
    obs = ObservabilityOps(prometheus_url="http://prom:9090")
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "status": "error",
        "error": "syntax error at line 1",
    }

    obs._client.get = AsyncMock(return_value=fake_response)
    try:
        res = await obs.query_prometheus("bad query")
        assert "Prometheus 쿼리 실패: syntax error" in res
    finally:
        await obs.close()


@pytest.mark.asyncio
async def test_prom_query_http_error():
    obs = ObservabilityOps(prometheus_url="http://prom:9090")
    req = httpx.Request("GET", "http://prom:9090/api/v1/query")
    resp = httpx.Response(502, request=req, text="Bad Gateway")
    obs._client.get = AsyncMock(side_effect=httpx.HTTPStatusError("502 Bad Gateway", request=req, response=resp))
    try:
        res = await obs.query_prometheus("up")
        assert "Prometheus HTTP 오류 (502)" in res
    finally:
        await obs.close()


@pytest.mark.asyncio
async def test_loki_query_success():
    obs = ObservabilityOps(loki_url="http://loki:3100")
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "streams",
            "result": [
                {
                    "stream": {"app": "order-api", "namespace": "prod"},
                    "values": [
                        ["1700000000000000000", "2026-11-09 ERROR failed to connect DB"],
                        ["1700000001000000000", "2026-11-09 INFO retrying connection"],
                    ],
                }
            ],
        },
    }

    obs._client.get = AsyncMock(return_value=fake_response)
    try:
        res = await obs.query_loki('{app="order-api"}', limit=10)
        assert "Loki LogQL 결과" in res
        assert "[app=order-api]" in res
        assert "ERROR failed to connect DB" in res
    finally:
        await obs.close()


@pytest.mark.asyncio
async def test_loki_query_empty_results():
    obs = ObservabilityOps(loki_url="http://loki:3100")
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "status": "success",
        "data": {"resultType": "streams", "result": []},
    }

    obs._client.get = AsyncMock(return_value=fake_response)
    try:
        res = await obs.query_loki('{app="empty"}')
        assert "0건 반환" in res
    finally:
        await obs.close()
