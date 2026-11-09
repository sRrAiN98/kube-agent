"""KubernetesOps 모듈 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

from kube_agent.kubernetes_ops import KubernetesOps, _age, _safe_name


def test_safe_name_and_age() -> None:
    """_safe_name과 _age 헬퍼 함수를 검증합니다."""
    assert _safe_name(None) == "unknown"
    mock_obj = MagicMock()
    mock_obj.metadata.name = "my-pod"
    assert _safe_name(mock_obj) == "my-pod"
    assert _age(None) == "unknown"


def test_list_pods_empty(mock_k8s_ops: KubernetesOps) -> None:
    """Pod가 없는 경우 적절한 메시지를 반환해야 합니다."""
    mock_k8s_ops._core.list_namespaced_pod.return_value = MagicMock(items=[])
    result = mock_k8s_ops.list_pods()
    assert "Pod가 없습니다" in result


def test_list_pods_with_items(mock_k8s_ops: KubernetesOps) -> None:
    """Pod 목록 조회가 정상 동작해야 합니다."""
    pod = MagicMock()
    pod.metadata.name = "web-pod"
    pod.metadata.creation_timestamp = None
    pod.status.phase = "Running"
    cs = MagicMock()
    cs.restart_count = 2
    pod.status.container_statuses = [cs]

    mock_k8s_ops._core.list_namespaced_pod.return_value = MagicMock(items=[pod])
    result = mock_k8s_ops.list_pods()
    assert "web-pod" in result
    assert "Running" in result


def test_get_pod_logs(mock_k8s_ops: KubernetesOps) -> None:
    """Pod 로그 조회가 정상 동작해야 합니다."""
    mock_k8s_ops._core.read_namespaced_pod_log.return_value = "line 1\nline 2"
    result = mock_k8s_ops.get_pod_logs("web-pod", tail=50)
    assert "line 1" in result
    assert "web-pod" in result


def test_restart_deployment(mock_k8s_ops: KubernetesOps) -> None:
    """Deployment 롤링 재시작이 정상 동작해야 합니다."""
    mock_k8s_ops._apps.patch_namespaced_deployment.return_value = MagicMock()
    result = mock_k8s_ops.restart_deployment("web-deploy")
    assert "롤링 재시작을 시작했습니다" in result


def test_scale_deployment(mock_k8s_ops: KubernetesOps) -> None:
    """Deployment 레플리카 조절이 정상 동작해야 합니다."""
    mock_k8s_ops._apps.patch_namespaced_deployment.return_value = MagicMock()
    result = mock_k8s_ops.scale_deployment("web-deploy", replicas=5)
    assert "5개로 조정했습니다" in result

