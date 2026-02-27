"""Kubernetes operations for kube-agent.

Kubernetes API를 통해 클러스터 리소스를 조회하고 관리합니다.
클러스터 내부(in-cluster) 또는 kubeconfig를 통해 인증합니다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


def _age(creation_timestamp: datetime | None) -> str:
    """리소스 생성 시간을 사람이 읽기 쉬운 형식으로 변환합니다.

    Args:
        creation_timestamp: 리소스 생성 시간 (UTC)

    Returns:
        "3d", "5h", "30m" 등의 문자열
    """
    if creation_timestamp is None:
        return "unknown"
    now = datetime.now(UTC)
    delta = now - creation_timestamp.replace(tzinfo=UTC)
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if days > 0:
        return f"{days}d"
    if hours > 0:
        return f"{hours}h"
    return f"{minutes}m"


def _safe_name(obj: Any) -> str:
    """Kubernetes 오브젝트에서 이름을 안전하게 추출합니다."""
    if hasattr(obj, "metadata") and obj.metadata and obj.metadata.name:
        return obj.metadata.name
    return "unknown"


class KubernetesOps:
    """Kubernetes 클러스터 리소스 관리 클래스.

    Pod, Deployment, Service, ConfigMap, Secret, Event 등의
    조회 및 관리 기능을 제공합니다.
    """

    def __init__(self, namespace: str, context: str = "") -> None:
        """Kubernetes 클라이언트를 초기화합니다.

        클러스터 내부 환경(in-cluster)을 먼저 시도하고,
        실패하면 로컬 kubeconfig를 사용합니다.

        Args:
            namespace: 기본 작업 네임스페이스
            context: kubeconfig 컨텍스트 (빈 문자열이면 현재 컨텍스트 사용)
        """
        self.namespace = namespace
        try:
            config.load_incluster_config()
            logger.info("In-cluster Kubernetes 설정 로드 완료")
        except config.ConfigException:
            try:
                if context:
                    config.load_kube_config(context=context)
                else:
                    config.load_kube_config()
                logger.info("Kubeconfig 설정 로드 완료")
            except config.ConfigException as exc:
                logger.warning("Kubernetes 설정 로드 실패: %s", exc)

        self._core = client.CoreV1Api()
        self._apps = client.AppsV1Api()

    def list_pods(self) -> str:
        """네임스페이스 내 모든 Pod를 목록으로 반환합니다.

        Returns:
            Pod 이름, 상태, 재시작 횟수, 수명이 포함된 테이블 문자열
        """
        try:
            pods = self._core.list_namespaced_pod(namespace=self.namespace)
            if not pods.items:
                return f"네임스페이스 '{self.namespace}'에 Pod가 없습니다."

            lines = [f"{'NAME':<50} {'STATUS':<12} {'RESTARTS':<10} {'AGE':<8}"]
            lines.append("-" * 80)
            for pod in pods.items:
                name = _safe_name(pod)
                phase = pod.status.phase if pod.status else "Unknown"
                restarts = 0
                if pod.status and pod.status.container_statuses:
                    restarts = sum(cs.restart_count for cs in pod.status.container_statuses)
                age = _age(pod.metadata.creation_timestamp if pod.metadata else None)
                lines.append(f"{name:<50} {phase:<12} {restarts:<10} {age:<8}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"Pod 목록 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Pod 목록 조회 중 오류: {exc}"

    def get_pod(self, name: str) -> str:
        """특정 Pod의 상세 정보를 반환합니다.

        Args:
            name: Pod 이름

        Returns:
            Pod 상세 정보 문자열 (상태, 컨테이너, IP, 노드 등)
        """
        try:
            pod = self._core.read_namespaced_pod(name=name, namespace=self.namespace)
            lines = [f"Pod: {_safe_name(pod)}"]
            lines.append(f"  Namespace: {self.namespace}")
            lines.append(f"  Status: {pod.status.phase if pod.status else 'Unknown'}")

            if pod.status and pod.status.pod_ip:
                lines.append(f"  Pod IP: {pod.status.pod_ip}")
            if pod.spec and pod.spec.node_name:
                lines.append(f"  Node: {pod.spec.node_name}")

            # 컨테이너 정보
            if pod.spec and pod.spec.containers:
                lines.append("  Containers:")
                for c in pod.spec.containers:
                    lines.append(f"    - {c.name}: {c.image}")
                    if c.ports:
                        ports_str = ", ".join(f"{p.container_port}/{p.protocol or 'TCP'}" for p in c.ports)
                        lines.append(f"      Ports: {ports_str}")

            # 컨테이너 상태
            if pod.status and pod.status.container_statuses:
                lines.append("  Container Statuses:")
                for cs in pod.status.container_statuses:
                    ready = "Ready" if cs.ready else "NotReady"
                    lines.append(f"    - {cs.name}: {ready}, Restarts={cs.restart_count}")

            # 컨디션
            if pod.status and pod.status.conditions:
                lines.append("  Conditions:")
                for cond in pod.status.conditions:
                    lines.append(f"    - {cond.type}: {cond.status}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"Pod '{name}' 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Pod '{name}' 조회 중 오류: {exc}"

    def get_pod_logs(self, name: str, container: str | None = None, tail: int = 100) -> str:
        """Pod 로그를 반환합니다.

        Args:
            name: Pod 이름
            container: 컨테이너 이름 (None이면 기본 컨테이너)
            tail: 마지막 N줄만 반환 (기본 100)

        Returns:
            Pod 로그 문자열
        """
        try:
            kwargs: dict[str, Any] = {
                "name": name,
                "namespace": self.namespace,
                "tail_lines": tail,
            }
            if container:
                kwargs["container"] = container

            logs = self._core.read_namespaced_pod_log(**kwargs)
            if not logs:
                return f"Pod '{name}'의 로그가 비어있습니다."
            return f"--- Pod '{name}' logs (last {tail} lines) ---\n{logs}"
        except ApiException as exc:
            return f"Pod '{name}' 로그 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Pod '{name}' 로그 조회 중 오류: {exc}"

    def list_deployments(self) -> str:
        """네임스페이스 내 모든 Deployment를 목록으로 반환합니다.

        Returns:
            Deployment 이름, Ready 레플리카, 전체 레플리카, 수명이 포함된 테이블 문자열
        """
        try:
            deps = self._apps.list_namespaced_deployment(namespace=self.namespace)
            if not deps.items:
                return f"네임스페이스 '{self.namespace}'에 Deployment가 없습니다."

            lines = [f"{'NAME':<45} {'READY':<10} {'REPLICAS':<10} {'AGE':<8}"]
            lines.append("-" * 73)
            for dep in deps.items:
                name = _safe_name(dep)
                ready = dep.status.ready_replicas or 0 if dep.status else 0
                replicas = dep.spec.replicas or 0 if dep.spec else 0
                age = _age(dep.metadata.creation_timestamp if dep.metadata else None)
                lines.append(f"{name:<45} {ready:<10} {replicas:<10} {age:<8}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"Deployment 목록 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Deployment 목록 조회 중 오류: {exc}"

    def get_deployment(self, name: str) -> str:
        """특정 Deployment의 상세 정보를 반환합니다.

        Args:
            name: Deployment 이름

        Returns:
            Deployment 상세 정보 문자열
        """
        try:
            dep = self._apps.read_namespaced_deployment(name=name, namespace=self.namespace)
            lines = [f"Deployment: {_safe_name(dep)}"]
            lines.append(f"  Namespace: {self.namespace}")

            if dep.spec:
                lines.append(f"  Replicas: {dep.spec.replicas or 0}")
                if dep.spec.strategy:
                    lines.append(f"  Strategy: {dep.spec.strategy.type}")

            if dep.status:
                lines.append(f"  Ready Replicas: {dep.status.ready_replicas or 0}")
                lines.append(f"  Updated Replicas: {dep.status.updated_replicas or 0}")
                lines.append(f"  Available Replicas: {dep.status.available_replicas or 0}")

                if dep.status.conditions:
                    lines.append("  Conditions:")
                    for cond in dep.status.conditions:
                        lines.append(f"    - {cond.type}: {cond.status} ({cond.reason or ''})")

            # 컨테이너 이미지 정보
            if dep.spec and dep.spec.template and dep.spec.template.spec:
                lines.append("  Containers:")
                for c in dep.spec.template.spec.containers:
                    lines.append(f"    - {c.name}: {c.image}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"Deployment '{name}' 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Deployment '{name}' 조회 중 오류: {exc}"

    def restart_deployment(self, name: str) -> str:
        """Deployment를 롤링 재시작합니다.

        kubectl rollout restart와 동일하게 annotation에 타임스탬프를 패치합니다.

        Args:
            name: Deployment 이름

        Returns:
            재시작 성공/실패 메시지
        """
        try:
            now = datetime.now(UTC).isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": now,
                            }
                        }
                    }
                }
            }
            self._apps.patch_namespaced_deployment(
                name=name,
                namespace=self.namespace,
                body=body,
            )
            return f"Deployment '{name}' 롤링 재시작을 시작했습니다. (restartedAt: {now})"
        except ApiException as exc:
            return f"Deployment '{name}' 재시작 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Deployment '{name}' 재시작 중 오류: {exc}"

    def scale_deployment(self, name: str, replicas: int) -> str:
        """Deployment의 레플리카 수를 조정합니다.

        Args:
            name: Deployment 이름
            replicas: 목표 레플리카 수

        Returns:
            스케일링 성공/실패 메시지
        """
        try:
            body = {"spec": {"replicas": replicas}}
            self._apps.patch_namespaced_deployment(
                name=name,
                namespace=self.namespace,
                body=body,
            )
            return f"Deployment '{name}'의 레플리카를 {replicas}개로 조정했습니다."
        except ApiException as exc:
            return f"Deployment '{name}' 스케일링 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Deployment '{name}' 스케일링 중 오류: {exc}"

    def list_services(self) -> str:
        """네임스페이스 내 모든 Service를 목록으로 반환합니다.

        Returns:
            Service 이름, 타입, ClusterIP, 포트가 포함된 테이블 문자열
        """
        try:
            svcs = self._core.list_namespaced_service(namespace=self.namespace)
            if not svcs.items:
                return f"네임스페이스 '{self.namespace}'에 Service가 없습니다."

            lines = [f"{'NAME':<40} {'TYPE':<15} {'CLUSTER-IP':<18} {'PORTS':<30}"]
            lines.append("-" * 103)
            for svc in svcs.items:
                name = _safe_name(svc)
                svc_type = svc.spec.type if svc.spec else "Unknown"
                cluster_ip = svc.spec.cluster_ip if svc.spec else "None"
                ports = ""
                if svc.spec and svc.spec.ports:
                    ports = ", ".join(f"{p.port}/{p.protocol or 'TCP'}" for p in svc.spec.ports)
                lines.append(f"{name:<40} {svc_type:<15} {cluster_ip:<18} {ports:<30}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"Service 목록 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Service 목록 조회 중 오류: {exc}"

    def list_configmaps(self) -> str:
        """네임스페이스 내 모든 ConfigMap을 목록으로 반환합니다.

        Returns:
            ConfigMap 이름, 데이터 키 수, 수명이 포함된 테이블 문자열
        """
        try:
            cms = self._core.list_namespaced_config_map(namespace=self.namespace)
            if not cms.items:
                return f"네임스페이스 '{self.namespace}'에 ConfigMap이 없습니다."

            lines = [f"{'NAME':<50} {'DATA KEYS':<12} {'AGE':<8}"]
            lines.append("-" * 70)
            for cm in cms.items:
                name = _safe_name(cm)
                data_count = len(cm.data) if cm.data else 0
                age = _age(cm.metadata.creation_timestamp if cm.metadata else None)
                lines.append(f"{name:<50} {data_count:<12} {age:<8}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"ConfigMap 목록 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"ConfigMap 목록 조회 중 오류: {exc}"

    def get_configmap(self, name: str) -> str:
        """특정 ConfigMap의 데이터를 반환합니다.

        Args:
            name: ConfigMap 이름

        Returns:
            ConfigMap 키-값 데이터 문자열
        """
        try:
            cm = self._core.read_namespaced_config_map(name=name, namespace=self.namespace)
            lines = [f"ConfigMap: {_safe_name(cm)}"]
            lines.append(f"  Namespace: {self.namespace}")

            if cm.data:
                lines.append("  Data:")
                for key, value in cm.data.items():
                    # 긴 값은 잘라서 표시
                    display_value = value if len(value) <= 500 else value[:500] + "... (truncated)"
                    lines.append(f"    {key}:")
                    for line in display_value.split("\n"):
                        lines.append(f"      {line}")
            else:
                lines.append("  Data: (empty)")

            return "\n".join(lines)
        except ApiException as exc:
            return f"ConfigMap '{name}' 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"ConfigMap '{name}' 조회 중 오류: {exc}"

    def list_secrets(self) -> str:
        """네임스페이스 내 모든 Secret의 이름만 반환합니다.

        보안을 위해 Secret 데이터는 표시하지 않습니다.

        Returns:
            Secret 이름, 타입, 수명이 포함된 테이블 문자열
        """
        try:
            secrets = self._core.list_namespaced_secret(namespace=self.namespace)
            if not secrets.items:
                return f"네임스페이스 '{self.namespace}'에 Secret이 없습니다."

            lines = [f"{'NAME':<50} {'TYPE':<35} {'AGE':<8}"]
            lines.append("-" * 93)
            for secret in secrets.items:
                name = _safe_name(secret)
                secret_type = secret.type or "Opaque"
                age = _age(secret.metadata.creation_timestamp if secret.metadata else None)
                lines.append(f"{name:<50} {secret_type:<35} {age:<8}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"Secret 목록 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"Secret 목록 조회 중 오류: {exc}"

    def get_events(self, limit: int = 20) -> str:
        """네임스페이스의 최근 이벤트를 반환합니다.

        Args:
            limit: 반환할 최대 이벤트 수 (기본 20)

        Returns:
            최근 이벤트 목록 문자열
        """
        try:
            events = self._core.list_namespaced_event(namespace=self.namespace)
            if not events.items:
                return f"네임스페이스 '{self.namespace}'에 이벤트가 없습니다."

            # 최신 이벤트가 먼저 오도록 정렬
            sorted_events = sorted(
                events.items,
                key=lambda e: e.last_timestamp
                or e.metadata.creation_timestamp
                or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )[:limit]

            lines = [f"{'TYPE':<10} {'REASON':<20} {'OBJECT':<35} {'MESSAGE':<50}"]
            lines.append("-" * 115)
            for event in sorted_events:
                event_type = event.type or "Normal"
                reason = event.reason or ""
                obj = ""
                if event.involved_object:
                    kind = event.involved_object.kind or ""
                    obj_name = event.involved_object.name or ""
                    obj = f"{kind}/{obj_name}"
                message = (event.message or "")[:50]
                lines.append(f"{event_type:<10} {reason:<20} {obj:<35} {message:<50}")

            return "\n".join(lines)
        except ApiException as exc:
            return f"이벤트 조회 실패: {exc.reason} (HTTP {exc.status})"
        except Exception as exc:
            return f"이벤트 조회 중 오류: {exc}"
