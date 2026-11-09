"""FileOps 모듈 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from kube_agent.file_ops import FileOps


class TestFileOpsSandbox:
    """FileOps 샌드박스 보안 검증."""

    def test_disallowed_path_blocked(self, mock_file_ops: FileOps) -> None:
        """허용되지 않은 디렉토리 접근 시 보안 오류를 반환해야 합니다."""
        result = mock_file_ops.read_file("/etc/passwd")
        assert "보안 제한" in result

        result = mock_file_ops.write_file("C:\\Windows\\system32\\calc.exe", "evil")
        assert "보안 제한" in result

    def test_allowed_path_allowed(self, mock_file_ops: FileOps, tmp_path: Path) -> None:
        """허용된 디렉토리 내 파일 쓰기/읽기가 정상 동작해야 합니다."""
        target_file = tmp_path / "hello.txt"
        write_res = mock_file_ops.write_file(str(target_file), "hello world", create_dirs=True)
        assert "생성 완료" in write_res

        read_res = mock_file_ops.read_file(str(target_file))
        assert "hello world" in read_res

    def test_list_directory(self, mock_file_ops: FileOps, tmp_path: Path) -> None:
        """디렉토리 목록 조회가 정상 동작해야 합니다."""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file1.txt").write_text("1", encoding="utf-8")
        (tmp_path / "subdir" / "file2.txt").write_text("2", encoding="utf-8")

        res = mock_file_ops.list_directory(str(tmp_path), recursive=True)
        assert "file1.txt" in res
        assert "subdir" in res
        assert "file2.txt" in res

    def test_nonexistent_file_read(self, mock_file_ops: FileOps, tmp_path: Path) -> None:
        """존재하지 않는 파일 읽기 시 적절한 오류를 반환해야 합니다."""
        res = mock_file_ops.read_file(str(tmp_path / "missing.txt"))
        assert "존재하지 않습니다" in res

