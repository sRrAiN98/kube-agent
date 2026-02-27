"""Local filesystem operations for kube-agent.

Git clone 후 로컬 파일을 조회하고 편집하기 위한 파일 조작 기능을 제공합니다.
보안을 위해 허용된 디렉토리(sandbox) 내에서만 동작합니다.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 파일 읽기 최대 크기 (1MB)
_MAX_READ_SIZE = 1_048_576
# 파일 쓰기 최대 크기 (1MB)
_MAX_WRITE_SIZE = 1_048_576
# 디렉토리 목록 최대 항목 수
_MAX_LIST_ENTRIES = 500
# 허용된 sandbox 디렉토리 목록
_SANDBOX_DIRS = ("/tmp", "/home/agent")


class FileOps:
    """로컬 파일시스템 조작 클래스.

    Git clone 이후 저장소 파일을 읽고 수정하기 위한 기능을 제공합니다.
    보안을 위해 sandbox 디렉토리 내에서만 동작하며, 심볼릭 링크를
    통한 경로 탈출을 방지합니다.
    """

    def _validate_path(self, path: str) -> str | None:
        """경로가 sandbox 내에 있는지 검증합니다.

        Args:
            path: 검증할 파일/디렉토리 경로

        Returns:
            검증 통과 시 None, 실패 시 오류 메시지 문자열
        """
        try:
            resolved = str(Path(path).resolve())
        except (OSError, ValueError) as exc:
            return f"경로를 확인할 수 없습니다: {exc}"

        for sandbox in _SANDBOX_DIRS:
            if resolved.startswith(sandbox):
                return None

        return f"보안 제한: '{path}'에 접근할 수 없습니다. 허용된 디렉토리: {', '.join(_SANDBOX_DIRS)}"

    def list_directory(self, path: str, recursive: bool = False) -> str:
        """디렉토리 내 파일 및 하위 디렉토리 목록을 반환합니다.

        Args:
            path: 디렉토리 경로
            recursive: True이면 하위 디렉토리까지 재귀적으로 탐색

        Returns:
            파일 목록 문자열 (디렉토리는 '/' 접미사 표시)
        """
        error = self._validate_path(path)
        if error:
            return error

        target = Path(path)
        if not target.exists():
            return f"디렉토리가 존재하지 않습니다: {path}"
        if not target.is_dir():
            return f"디렉토리가 아닙니다: {path}"

        try:
            entries: list[str] = []
            if recursive:
                for item in sorted(target.rglob("*")):
                    if len(entries) >= _MAX_LIST_ENTRIES:
                        entries.append(f"... ({_MAX_LIST_ENTRIES}개 항목 제한 도달)")
                        break
                    rel = item.relative_to(target)
                    suffix = "/" if item.is_dir() else ""
                    entries.append(f"  {rel}{suffix}")
            else:
                for item in sorted(target.iterdir()):
                    if len(entries) >= _MAX_LIST_ENTRIES:
                        entries.append(f"... ({_MAX_LIST_ENTRIES}개 항목 제한 도달)")
                        break
                    suffix = "/" if item.is_dir() else ""
                    entries.append(f"  {item.name}{suffix}")

            if not entries:
                return f"디렉토리가 비어있습니다: {path}"

            header = f"Directory: {path} ({len(entries)} entries)"
            if recursive:
                header += " [recursive]"
            return header + "\n" + "\n".join(entries)

        except PermissionError:
            return f"디렉토리 읽기 권한이 없습니다: {path}"
        except Exception as exc:
            return f"디렉토리 목록 조회 중 오류: {exc}"

    def read_file(self, path: str) -> str:
        """파일 내용을 읽어 반환합니다.

        Args:
            path: 파일 경로

        Returns:
            파일 내용 문자열. 바이너리 파일이면 오류 메시지 반환.
        """
        error = self._validate_path(path)
        if error:
            return error

        target = Path(path)
        if not target.exists():
            return f"파일이 존재하지 않습니다: {path}"
        if not target.is_file():
            return f"파일이 아닙니다 (디렉토리일 수 있음): {path}"

        try:
            size = target.stat().st_size
            if size > _MAX_READ_SIZE:
                return f"파일이 너무 큽니다: {size:,} bytes (최대 {_MAX_READ_SIZE:,} bytes). 파일 경로: {path}"

            content = target.read_text(encoding="utf-8")
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            header = f"--- {path} ({line_count} lines, {size:,} bytes) ---"
            return header + "\n" + content

        except UnicodeDecodeError:
            return f"바이너리 파일이라 읽을 수 없습니다: {path}"
        except PermissionError:
            return f"파일 읽기 권한이 없습니다: {path}"
        except Exception as exc:
            return f"파일 읽기 중 오류: {exc}"

    def write_file(self, path: str, content: str, create_dirs: bool = False) -> str:
        """파일에 내용을 씁니다 (덮어쓰기).

        Args:
            path: 파일 경로
            content: 쓸 내용
            create_dirs: True이면 부모 디렉토리를 자동 생성

        Returns:
            성공/실패 메시지
        """
        error = self._validate_path(path)
        if error:
            return error

        encoded_size = len(content.encode("utf-8"))
        if encoded_size > _MAX_WRITE_SIZE:
            return f"쓰기 내용이 너무 큽니다: {encoded_size:,} bytes (최대 {_MAX_WRITE_SIZE:,} bytes)"

        target = Path(path)

        try:
            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
            elif not target.parent.exists():
                return f"부모 디렉토리가 존재하지 않습니다: {target.parent}"

            existed = target.exists()
            target.write_text(content, encoding="utf-8")

            size = target.stat().st_size
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            action = "수정" if existed else "생성"
            return f"파일 {action} 완료: {path} ({line_count} lines, {size:,} bytes)"

        except PermissionError:
            return f"파일 쓰기 권한이 없습니다: {path}"
        except Exception as exc:
            return f"파일 쓰기 중 오류: {exc}"
