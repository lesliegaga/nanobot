"""Security tests for WikiTool path validation and size limits."""
from __future__ import annotations

import pytest
from pathlib import Path

from nanobot.agent.tools.wiki import WikiTool


class TestValidateSourcePath:
    def test_valid_path_within_wiki_root(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        source_file = wiki_root / "source.txt"
        source_file.write_text("test content")

        tool = WikiTool(wiki_root=wiki_root)
        result = tool._validate_source_path(str(source_file), wiki_root)

        assert result == source_file.resolve()

    def test_valid_path_in_allowed_directories(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        source_file = allowed_dir / "source.txt"
        source_file.write_text("test content")

        tool = WikiTool(wiki_root=wiki_root)
        result = tool._validate_source_path(
            str(source_file), wiki_root, allowed_paths=[str(allowed_dir)]
        )

        assert result == source_file.resolve()

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret")

        tool = WikiTool(wiki_root=wiki_root)
        traversal_path = str(wiki_root / ".." / "secret.txt")

        with pytest.raises(ValueError, match="Access denied"):
            tool._validate_source_path(traversal_path, wiki_root)

    def test_absolute_path_outside_blocked(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()

        tool = WikiTool(wiki_root=wiki_root)

        with pytest.raises(ValueError, match="Access denied"):
            tool._validate_source_path("/etc/passwd", wiki_root)

    def test_home_directory_path_blocked(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()

        tool = WikiTool(wiki_root=wiki_root)

        with pytest.raises(ValueError, match="Access denied"):
            tool._validate_source_path("~/.bashrc", wiki_root)

    def test_nested_path_in_allowed_dir(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        nested_dir = wiki_root / "sub" / "dir"
        nested_dir.mkdir(parents=True)
        source_file = nested_dir / "source.txt"
        source_file.write_text("test")

        tool = WikiTool(wiki_root=wiki_root)
        result = tool._validate_source_path(str(source_file), wiki_root)

        assert result == source_file.resolve()


class TestValidateFileSize:
    def test_small_file_allowed(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        test_file = tmp_path / "small.txt"
        test_file.write_text("small content")

        tool = WikiTool(wiki_root=wiki_root)
        tool._validate_file_size(test_file, max_size_mb=50)

    def test_exact_size_limit_allowed(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        test_file = tmp_path / "exact.txt"
        test_file.write_bytes(b"x" * (50 * 1024 * 1024))

        tool = WikiTool(wiki_root=wiki_root)
        tool._validate_file_size(test_file, max_size_mb=50)

    def test_oversized_file_blocked(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        test_file = tmp_path / "large.txt"
        test_file.write_bytes(b"x" * (51 * 1024 * 1024))

        tool = WikiTool(wiki_root=wiki_root)

        with pytest.raises(ValueError, match="File too large"):
            tool._validate_file_size(test_file, max_size_mb=50)

    def test_nonexistent_file_raises_error(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        nonexistent = tmp_path / "does_not_exist.txt"

        tool = WikiTool(wiki_root=wiki_root)

        with pytest.raises(ValueError, match="Cannot access file"):
            tool._validate_file_size(nonexistent, max_size_mb=50)

    def test_custom_size_limit(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        test_file = tmp_path / "medium.txt"
        test_file.write_bytes(b"x" * (2 * 1024 * 1024))

        tool = WikiTool(wiki_root=wiki_root)

        with pytest.raises(ValueError, match="File too large"):
            tool._validate_file_size(test_file, max_size_mb=1)


class TestIngestSourceSecurity:
    @pytest.mark.asyncio
    async def test_ingest_blocks_path_traversal(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret data")

        tool = WikiTool(wiki_root=wiki_root)
        traversal_path = str(wiki_root / ".." / "secret.txt")

        result = await tool._ingest_source(wiki_root, traversal_path)

        assert "Error:" in result
        assert "Access denied" in result

    @pytest.mark.asyncio
    async def test_ingest_blocks_oversized_file(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        large_file = wiki_root / "large.txt"
        large_file.write_bytes(b"x" * (51 * 1024 * 1024))

        tool = WikiTool(wiki_root=wiki_root)
        result = await tool._ingest_source(wiki_root, str(large_file))

        assert "Error:" in result
        assert "File too large" in result

    @pytest.mark.asyncio
    async def test_ingest_allows_valid_file(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        valid_file = wiki_root / "valid.txt"
        valid_file.write_text("This is valid content for ingestion")

        tool = WikiTool(wiki_root=wiki_root)
        result = await tool._ingest_source(wiki_root, str(valid_file), create_summary=False)

        assert "Error:" not in result
        assert "Source copied" in result

    @pytest.mark.asyncio
    async def test_ingest_preserves_file_in_raw(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir()
        valid_file = wiki_root / "document.txt"
        valid_file.write_text("Document content")

        tool = WikiTool(wiki_root=wiki_root)
        await tool._ingest_source(wiki_root, str(valid_file), create_summary=False)

        raw_file = wiki_root / "raw" / "document.txt"
        assert raw_file.exists()
        assert raw_file.read_text() == "Document content"
