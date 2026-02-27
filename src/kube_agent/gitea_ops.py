"""Gitea operations for kube-agent.

Gitea REST API와 Git CLI를 통해 저장소를 관리합니다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Git 작업에 허용된 sandbox 디렉토리 (file_ops.py와 동일)
_GIT_SANDBOX_DIRS = ("/tmp", "/home/agent")


class GiteaOps:
    """Gitea 저장소 및 Git 관리 클래스.

    Gitea REST API (httpx 비동기)와 Git CLI (subprocess)를
    통해 저장소, 브랜치, 웹훅 등을 관리합니다.

    httpx.AsyncClient를 클래스 레벨에서 관리하여 커넥션 풀을 재사용합니다.
    사용 후 close()를 반드시 호출하세요.
    """

    def __init__(self, gitea_url: str, token: str, timeout: float = 30.0) -> None:
        """Gitea 클라이언트를 초기화합니다.

        Args:
            gitea_url: Gitea 서버 URL (예: http://gitea.ops:3000)
            token: Gitea API 인증 토큰
            timeout: HTTP 요청 타임아웃 초 (기본: 30)
        """
        self._base_url = gitea_url.rstrip("/")
        self._token = token
        self._api_url = f"{self._base_url}/api/v1"
        # 커넥션 풀 재사용을 위해 클라이언트를 클래스 레벨에서 관리
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=self._build_headers(),
        )

    def _build_headers(self) -> dict[str, str]:
        """API 요청에 사용할 인증 헤더를 반환합니다."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    def _enabled(self) -> bool:
        """Gitea 연결이 설정되어 있는지 확인합니다."""
        return bool(self._base_url)

    async def close(self) -> None:
        """httpx 클라이언트를 닫고 커넥션 풀을 해제합니다."""
        await self._client.aclose()

    def _validate_git_path(self, path: str) -> str | None:
        """Git 작업 경로가 sandbox 내에 있는지 검증합니다.

        Args:
            path: 검증할 디렉토리 경로

        Returns:
            검증 통과 시 None, 실패 시 오류 메시지 문자열
        """
        try:
            resolved = str(Path(path).resolve())
        except (OSError, ValueError) as exc:
            return f"경로를 확인할 수 없습니다: {exc}"

        for sandbox in _GIT_SANDBOX_DIRS:
            if resolved.startswith(sandbox):
                return None

        return f"보안 제한: '{path}'에 접근할 수 없습니다. 허용된 디렉토리: {', '.join(_GIT_SANDBOX_DIRS)}"

    # ---- REST API 메서드 (httpx 비동기) ----

    async def list_repos(self) -> str:
        """접근 가능한 모든 저장소를 목록으로 반환합니다.

        Returns:
            저장소 이름, 소유자, 설명이 포함된 목록 문자열
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            resp = await self._client.get(
                f"{self._api_url}/repos/search",
                params={"limit": 50},
            )
            resp.raise_for_status()
            data = resp.json()

            repos: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else data
            if not repos:
                return "접근 가능한 저장소가 없습니다."

            lines = [f"{'OWNER/NAME':<40} {'PRIVATE':<10} {'DESCRIPTION':<50}"]
            lines.append("-" * 100)
            for repo in repos:
                full_name = repo.get("full_name", "unknown")
                private = "Yes" if repo.get("private") else "No"
                desc = (repo.get("description", "") or "")[:50]
                lines.append(f"{full_name:<40} {private:<10} {desc:<50}")

            return "\n".join(lines)
        except httpx.HTTPStatusError as exc:
            return f"저장소 목록 조회 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"저장소 목록 조회 중 오류: {exc}"

    async def get_repo(self, owner: str, name: str) -> str:
        """특정 저장소의 상세 정보를 반환합니다.

        Args:
            owner: 저장소 소유자
            name: 저장소 이름

        Returns:
            저장소 상세 정보 문자열
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            resp = await self._client.get(f"{self._api_url}/repos/{owner}/{name}")
            resp.raise_for_status()
            repo = resp.json()

            lines = [f"Repository: {repo.get('full_name', 'unknown')}"]
            lines.append(f"  Description: {repo.get('description', '(none)')}")
            lines.append(f"  Private: {repo.get('private', False)}")
            lines.append(f"  Default Branch: {repo.get('default_branch', 'main')}")
            lines.append(f"  Stars: {repo.get('stars_count', 0)}")
            lines.append(f"  Forks: {repo.get('forks_count', 0)}")
            lines.append(f"  Size: {repo.get('size', 0)} KB")
            lines.append(f"  Clone URL: {repo.get('clone_url', '')}")
            lines.append(f"  Created: {repo.get('created_at', 'unknown')}")
            lines.append(f"  Updated: {repo.get('updated_at', 'unknown')}")

            return "\n".join(lines)
        except httpx.HTTPStatusError as exc:
            return f"저장소 '{owner}/{name}' 조회 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"저장소 '{owner}/{name}' 조회 중 오류: {exc}"

    async def create_repo(self, name: str, description: str = "", private: bool = True) -> str:
        """새 저장소를 생성합니다.

        Args:
            name: 저장소 이름
            description: 저장소 설명
            private: 비공개 여부 (기본 True)

        Returns:
            생성 결과 메시지
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            payload = {
                "name": name,
                "description": description,
                "private": private,
                "auto_init": True,
            }
            resp = await self._client.post(f"{self._api_url}/user/repos", json=payload)
            resp.raise_for_status()
            repo = resp.json()

            return f"저장소 '{repo.get('full_name', name)}' 생성 완료.\n  Clone URL: {repo.get('clone_url', '')}"
        except httpx.HTTPStatusError as exc:
            return f"저장소 '{name}' 생성 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"저장소 '{name}' 생성 중 오류: {exc}"

    async def delete_repo(self, owner: str, name: str) -> str:
        """저장소를 삭제합니다.

        Args:
            owner: 저장소 소유자
            name: 저장소 이름

        Returns:
            삭제 결과 메시지
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            resp = await self._client.delete(f"{self._api_url}/repos/{owner}/{name}")
            resp.raise_for_status()

            return f"저장소 '{owner}/{name}' 삭제 완료."
        except httpx.HTTPStatusError as exc:
            return f"저장소 '{owner}/{name}' 삭제 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"저장소 '{owner}/{name}' 삭제 중 오류: {exc}"

    async def list_branches(self, owner: str, repo: str) -> str:
        """저장소의 브랜치 목록을 반환합니다.

        Args:
            owner: 저장소 소유자
            repo: 저장소 이름

        Returns:
            브랜치 이름 목록 문자열
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            resp = await self._client.get(f"{self._api_url}/repos/{owner}/{repo}/branches")
            resp.raise_for_status()
            branches = resp.json()

            if not branches:
                return f"저장소 '{owner}/{repo}'에 브랜치가 없습니다."

            lines = [f"{'BRANCH':<40} {'COMMIT (short)':<15}"]
            lines.append("-" * 55)
            for branch in branches:
                branch_name = branch.get("name", "unknown")
                commit_id = branch.get("commit", {}).get("id", "")[:8]
                lines.append(f"{branch_name:<40} {commit_id:<15}")

            return "\n".join(lines)
        except httpx.HTTPStatusError as exc:
            return f"브랜치 목록 조회 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"브랜치 목록 조회 중 오류: {exc}"

    async def list_users(self) -> str:
        """Gitea 사용자 목록을 반환합니다 (관리자 전용).

        Returns:
            사용자 이름, 이메일, 관리자 여부가 포함된 목록 문자열
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            resp = await self._client.get(f"{self._api_url}/admin/users", params={"limit": 50})
            resp.raise_for_status()
            users = resp.json()

            if not users:
                return "사용자가 없습니다."

            lines = [f"{'USERNAME':<25} {'EMAIL':<35} {'ADMIN':<8}"]
            lines.append("-" * 68)
            for user in users:
                username = user.get("login", "unknown")
                email = user.get("email", "")
                is_admin = "Yes" if user.get("is_admin") else "No"
                lines.append(f"{username:<25} {email:<35} {is_admin:<8}")

            return "\n".join(lines)
        except httpx.HTTPStatusError as exc:
            return f"사용자 목록 조회 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"사용자 목록 조회 중 오류: {exc}"

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        target_url: str,
        events: list[str] | None = None,
    ) -> str:
        """저장소에 웹훅을 추가합니다.

        Args:
            owner: 저장소 소유자
            repo: 저장소 이름
            target_url: 웹훅 대상 URL
            events: 트리거할 이벤트 목록 (기본: ["push"])

        Returns:
            웹훅 생성 결과 메시지
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            payload = {
                "type": "gitea",
                "active": True,
                "events": events or ["push"],
                "config": {
                    "url": target_url,
                    "content_type": "json",
                },
            }
            resp = await self._client.post(
                f"{self._api_url}/repos/{owner}/{repo}/hooks",
                json=payload,
            )
            resp.raise_for_status()
            hook = resp.json()

            return (
                f"웹훅 생성 완료 (ID: {hook.get('id', 'unknown')})\n"
                f"  URL: {target_url}\n"
                f"  Events: {', '.join(events or ['push'])}"
            )
        except httpx.HTTPStatusError as exc:
            return f"웹훅 생성 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"웹훅 생성 중 오류: {exc}"

    async def list_webhooks(self, owner: str, repo: str) -> str:
        """저장소의 웹훅 목록을 반환합니다.

        Args:
            owner: 저장소 소유자
            repo: 저장소 이름

        Returns:
            웹훅 목록 문자열
        """
        if not self._enabled():
            return "Gitea URL이 설정되지 않았습니다."

        try:
            resp = await self._client.get(f"{self._api_url}/repos/{owner}/{repo}/hooks")
            resp.raise_for_status()
            hooks = resp.json()

            if not hooks:
                return f"저장소 '{owner}/{repo}'에 웹훅이 없습니다."

            lines = [f"{'ID':<8} {'URL':<50} {'ACTIVE':<8} {'EVENTS':<30}"]
            lines.append("-" * 96)
            for hook in hooks:
                hook_id = str(hook.get("id", ""))
                url = hook.get("config", {}).get("url", "")[:50]
                active = "Yes" if hook.get("active") else "No"
                events = ", ".join(hook.get("events", []))[:30]
                lines.append(f"{hook_id:<8} {url:<50} {active:<8} {events:<30}")

            return "\n".join(lines)
        except httpx.HTTPStatusError as exc:
            return f"웹훅 목록 조회 실패: HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"웹훅 목록 조회 중 오류: {exc}"

    # ---- Git CLI 메서드 (subprocess 비동기) ----

    async def _run_git(self, args: list[str], cwd: str | None = None) -> str:
        """Git 명령을 비동기 subprocess로 실행합니다.

        Args:
            args: git 서브커맨드 및 인자 리스트
            cwd: 작업 디렉토리

        Returns:
            명령 실행 결과 문자열
        """
        cmd = ["git"] + args
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode("utf-8", errors="replace").strip()
            error = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                return f"Git 명령 실패 (exit code {proc.returncode}):\n{error or output}"

            return output or "(no output)"
        except FileNotFoundError:
            return "git 명령을 찾을 수 없습니다. git이 설치되어 있는지 확인해주세요."
        except Exception as exc:
            return f"Git 명령 실행 중 오류: {exc}"

    async def git_clone(self, repo_url: str, path: str) -> str:
        """저장소를 클론합니다.

        Args:
            repo_url: 클론할 저장소 URL
            path: 클론 대상 경로 (sandbox 내여야 함)

        Returns:
            클론 결과 메시지
        """
        error = self._validate_git_path(path)
        if error:
            return error
        result = await self._run_git(["clone", repo_url, path])
        return f"git clone {repo_url} -> {path}\n{result}"

    async def git_pull(self, path: str) -> str:
        """최신 변경사항을 가져옵니다.

        Args:
            path: Git 작업 디렉토리 경로 (sandbox 내여야 함)

        Returns:
            pull 결과 메시지
        """
        error = self._validate_git_path(path)
        if error:
            return error
        result = await self._run_git(["pull"], cwd=path)
        return f"git pull ({path})\n{result}"

    async def git_status(self, path: str) -> str:
        """Git 상태를 확인합니다.

        Args:
            path: Git 작업 디렉토리 경로 (sandbox 내여야 함)

        Returns:
            상태 문자열
        """
        error = self._validate_git_path(path)
        if error:
            return error
        result = await self._run_git(["status", "--short"], cwd=path)
        return f"git status ({path})\n{result}"

    async def git_commit_and_push(self, path: str, message: str) -> str:
        """모든 변경사항을 커밋하고 푸시합니다.

        Args:
            path: Git 작업 디렉토리 경로 (sandbox 내여야 함)
            message: 커밋 메시지

        Returns:
            커밋 및 푸시 결과 메시지
        """
        error = self._validate_git_path(path)
        if error:
            return error
        add_result = await self._run_git(["add", "-A"], cwd=path)
        commit_result = await self._run_git(["commit", "-m", message], cwd=path)
        push_result = await self._run_git(["push"], cwd=path)

        return f"git add -A: {add_result}\ngit commit: {commit_result}\ngit push: {push_result}"
