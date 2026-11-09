"""Unit tests for kube-agent server mode (REST API & Webhook)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from kube_agent.config import AgentConfig
from kube_agent.server import AGENT_KEY, K8S_KEY, create_app


@pytest.fixture
def mock_agent_app():
    config = AgentConfig(
        llm_base_url="http://mock-llm:4000/v1",
        llm_api_key="mock-key",
        kube_namespace="test-ns",
        safety_mode="strict",
        read_only=False,
    )
    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api"),
        patch("kubernetes.client.AppsV1Api"),
    ):
        app = create_app(config)
        # Mock agent and k8s
        app[AGENT_KEY].execute_prompt = AsyncMock(return_value="Agent response mock")
        app[AGENT_KEY].close = AsyncMock()
        app[K8S_KEY].diagnose_cluster = MagicMock(return_value="Cluster diagnosis report mock")
        return app


@pytest.mark.asyncio
async def test_healthz_endpoint(mock_agent_app: web.Application) -> None:
    client = TestClient(TestServer(mock_agent_app))
    await client.start_server()
    try:
        resp = await client.get("/healthz")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["namespace"] == "test-ns"
        assert data["service"] == "kube-agent"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chat_endpoint_success(mock_agent_app: web.Application) -> None:
    client = TestClient(TestServer(mock_agent_app))
    await client.start_server()
    try:
        payload = {"prompt": "Check payment-api pod"}
        resp = await client.post("/api/v1/chat", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "success"
        assert data["response"] == "Agent response mock"
        mock_agent_app[AGENT_KEY].execute_prompt.assert_awaited_once_with("Check payment-api pod")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chat_endpoint_missing_prompt(mock_agent_app: web.Application) -> None:
    client = TestClient(TestServer(mock_agent_app))
    await client.start_server()
    try:
        resp = await client.post("/api/v1/chat", json={})
        assert resp.status == 400
        data = await resp.json()
        assert data["status"] == "error"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_diagnose_endpoint(mock_agent_app: web.Application) -> None:
    client = TestClient(TestServer(mock_agent_app))
    await client.start_server()
    try:
        resp = await client.post("/api/v1/diagnose", json={"namespace": "prod"})
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "success"
        assert "Cluster diagnosis report mock" in data["report"]
        mock_agent_app[K8S_KEY].diagnose_cluster.assert_called_with(namespace="prod")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_webhook_endpoint_processes_alert(mock_agent_app: web.Application) -> None:
    client = TestClient(TestServer(mock_agent_app))
    await client.start_server()
    try:
        payload = {
            "receiver": "kube-agent",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "KubePodCrashLooping",
                        "namespace": "prod",
                        "pod": "payment-api-abc",
                    },
                    "annotations": {
                        "summary": "Pod is in CrashLoopBackOff",
                    },
                }
            ],
        }
        resp = await client.post("/api/v1/webhook", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "success"
        assert data["alerts_processed"] == 1
        assert data["analysis"] == "Agent response mock"
        mock_agent_app[AGENT_KEY].execute_prompt.assert_awaited()
    finally:
        await client.close()
