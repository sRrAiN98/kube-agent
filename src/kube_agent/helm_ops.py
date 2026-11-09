"""Helm CLI wrapper module for kube-agent.

클러스터 내 차트 린트(lint), 템플릿 렌더링(template), 릴리스 설치/업그레이드(upgrade),
롤백(rollback) 및 상태 조회를 지원합니다.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_DEFAULT_HELM_TIMEOUT = 60.0


class HelmOps:
    """Helm CLI 작업 관리 클래스."""

    def __init__(self, namespace: str = "default", timeout: float = _DEFAULT_HELM_TIMEOUT) -> None:
        """HelmOps 인스턴스를 초기화합니다.

        Args:
            namespace: 기본 작업 네임스페이스
            timeout: Helm 명령어 실행 최대 제한 시간(초)
        """
        self.namespace = namespace
        self.timeout = timeout

    async def _run_helm(self, args: list[str]) -> tuple[int, str, str]:
        """Helm 서브프로세스를 안전하게 실행합니다.

        Args:
            args: helm 명령어 인자 리스트 (예: ['lint', './chart'])

        Returns:
            (returncode, stdout, stderr) 튜플
        """
        cmd = ["helm"] + args
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
            return (
                proc.returncode or 0,
                stdout_bytes.decode("utf-8", errors="replace"),
                stderr_bytes.decode("utf-8", errors="replace"),
            )
        except FileNotFoundError:
            return (
                127,
                "",
                "Helm 바이너리가 설치되어 있지 않습니다. 호스트 또는 컨테이너에 helm을 설치해주세요.",
            )
        except TimeoutError:
            return (
                124,
                "",
                f"Helm 명령어 실행 시간이 초과되었습니다 (제한 시간: {self.timeout}초).",
            )
        except Exception as exc:
            return 1, "", f"Helm 실행 중 예외 발생: {exc}"

    async def lint(self, chart_path: str, values_file: str | None = None) -> str:
        """Helm 차트의 문법 및 무결성을 검사합니다.

        Args:
            chart_path: 차트 디렉토리 또는 tarball 경로
            values_file: 검사에 사용할 values.yaml 파일 경로 (선택)

        Returns:
            검사 결과 문자열
        """
        args = ["lint", chart_path]
        if values_file:
            args.extend(["-f", values_file])

        code, out, err = await self._run_helm(args)
        if code == 0:
            return f"--- Helm Lint 성공: {chart_path} ---\n{out.strip()}"
        return f"--- Helm Lint 실패 (코드 {code}) ---\n{err.strip() or out.strip()}"

    async def template(
        self,
        name: str,
        chart_path: str,
        values_file: str | None = None,
        namespace: str | None = None,
    ) -> str:
        """Helm 차트를 로컬에서 매니페스트로 렌더링합니다.

        Args:
            name: 릴리스 이름
            chart_path: 차트 디렉토리 경로
            values_file: 추가 values.yaml 경로 (선택)
            namespace: 네임스페이스 (선택)

        Returns:
            렌더링된 매니페스트 또는 오류 메시지
        """
        ns = namespace or self.namespace
        args = ["template", name, chart_path, "-n", ns]
        if values_file:
            args.extend(["-f", values_file])

        code, out, err = await self._run_helm(args)
        if code == 0:
            return f"--- Helm Template 렌더링 결과: {name} (Namespace: {ns}) ---\n{out.strip()}"
        return f"--- Helm Template 실패 (코드 {code}) ---\n{err.strip() or out.strip()}"

    async def upgrade(
        self,
        release_name: str,
        chart_path: str,
        values_file: str | None = None,
        install: bool = True,
        namespace: str | None = None,
    ) -> str:
        """Helm 릴리스를 설치 또는 업그레이드합니다.

        Args:
            release_name: 릴리스 이름
            chart_path: 차트 디렉토리 경로
            values_file: 추가 values.yaml 경로 (선택)
            install: 미설치 시 자동 설치 (--install) 플래그 (기본 True)
            namespace: 네임스페이스 (선택)

        Returns:
            업그레이드 결과 메시지
        """
        ns = namespace or self.namespace
        args = ["upgrade", release_name, chart_path, "-n", ns]
        if install:
            args.append("--install")
        if values_file:
            args.extend(["-f", values_file])

        code, out, err = await self._run_helm(args)
        if code == 0:
            return f"--- Helm Upgrade/Install 성공: {release_name} (Namespace: {ns}) ---\n{out.strip()}"
        return f"--- Helm Upgrade 실패 (코드 {code}) ---\n{err.strip() or out.strip()}"

    async def rollback(
        self,
        release_name: str,
        revision: int = 0,
        namespace: str | None = None,
    ) -> str:
        """Helm 릴리스를 이전 버전으로 롤백합니다.

        Args:
            release_name: 릴리스 이름
            revision: 롤백할 리비전 번호 (0이면 직전 리비전)
            namespace: 네임스페이스 (선택)

        Returns:
            롤백 결과 메시지
        """
        ns = namespace or self.namespace
        args = ["rollback", release_name, str(revision), "-n", ns]

        code, out, err = await self._run_helm(args)
        if code == 0:
            return f"--- Helm Rollback 성공: {release_name} (Revision: {revision}) ---\n{out.strip()}"
        return f"--- Helm Rollback 실패 (코드 {code}) ---\n{err.strip() or out.strip()}"

    async def list_releases(
        self,
        namespace: str | None = None,
        all_namespaces: bool = False,
    ) -> str:
        """배포된 Helm 릴리스 목록을 반환합니다.

        Args:
            namespace: 네임스페이스
            all_namespaces: 모든 네임스페이스 대상 여부

        Returns:
            릴리스 목록 테이블 문자열
        """
        args = ["list"]
        if all_namespaces:
            args.append("-A")
        else:
            args.extend(["-n", namespace or self.namespace])

        code, out, err = await self._run_helm(args)
        if code == 0:
            lines = out.strip().splitlines()
            if len(lines) <= 1:
                return f"네임스페이스 '{namespace or self.namespace}'에 배포된 Helm 릴리스가 없습니다."
            return out.strip()
        return f"--- Helm List 실패 (코드 {code}) ---\n{err.strip() or out.strip()}"
