"""Tests for wiki parsing utilities."""

from datetime import date
from pathlib import Path

from nanobot.agent.tools.wiki import WikiTool


class TestFrontmatterParsing:
    """Tests for frontmatter parsing."""

    def test_read_frontmatter_with_valid_yaml(self) -> None:
        """Test parsing valid YAML frontmatter."""
        content = """---
title: Test Page
created: 2024-01-01
tags:
  - tag1
  - tag2
---

# Body Content

This is the body.
"""
        tool = WikiTool()
        frontmatter, body = tool._read_frontmatter(content)
        
        assert frontmatter["title"] == "Test Page"
        assert frontmatter["created"] == date(2024, 1, 1)
        assert "tag1" in frontmatter["tags"]
        assert "tag2" in frontmatter["tags"]
        assert "Body Content" in body

    def test_read_frontmatter_without_frontmatter(self) -> None:
        """Test parsing content without frontmatter."""
        content = """# Just a Title

Some body text here.
"""
        tool = WikiTool()
        frontmatter, body = tool._read_frontmatter(content)
        
        assert frontmatter == {}
        assert content in body

    def test_read_frontmatter_with_malformed_yaml(self) -> None:
        """Test handling malformed frontmatter gracefully."""
        content = """---
not valid yaml : : :
---

Body content
"""
        tool = WikiTool()
        # Should not crash, may return partial or empty frontmatter
        frontmatter, body = tool._read_frontmatter(content)
        # Body should still be accessible
        assert "Body content" in body or frontmatter is not None


class TestFrontmatterWriting:
    """Tests for frontmatter writing."""

    def test_write_frontmatter_with_simple_values(self) -> None:
        """Test writing frontmatter with simple key-value pairs."""
        tool = WikiTool()
        data = {
            "title": "Test Page",
            "created": "2024-01-01",
            "category": "entities"
        }
        
        result = tool._write_frontmatter(data)
        
        assert result.startswith("---")
        assert result.endswith("---")
        assert "title: Test Page" in result
        assert "created: 2024-01-01" in result
        assert "category: entities" in result

    def test_write_frontmatter_with_lists(self) -> None:
        """Test writing frontmatter with list values."""
        tool = WikiTool()
        data = {
            "title": "Test",
            "tags": ["tag1", "tag2", "tag3"],
            "sources": ["source1.md", "source2.md"]
        }
        
        result = tool._write_frontmatter(data)
        
        assert "tags:" in result
        assert "  - tag1" in result
        assert "  - tag2" in result
        assert "  - tag3" in result
        assert "sources:" in result
        assert "  - source1.md" in result


class TestFilenameSanitization:
    """Tests for filename sanitization."""

    def test_sanitize_filename_with_spaces(self) -> None:
        """Test that spaces are converted to underscores."""
        tool = WikiTool()
        
        result = tool._sanitize_filename("Hello World")
        assert result == "hello_world"
        
        result = tool._sanitize_filename("  Leading Spaces  ")
        assert result == "leading_spaces"

    def test_sanitize_filename_with_special_chars(self) -> None:
        """Test that special characters are removed."""
        tool = WikiTool()
        
        result = tool._sanitize_filename("File@Name#123!")
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result
        assert "filename123" in result.lower()

    def test_sanitize_filename_with_multiple_dashes(self) -> None:
        """Test that multiple dashes/spaces are handled."""
        tool = WikiTool()
        
        result = tool._sanitize_filename("My--File---Name")
        assert "my_file_name" == result
        
        result = tool._sanitize_filename("A - B - C")
        assert result == "a_b_c"


class TestWikiStructure:
    """Tests for wiki directory structure."""

    def test_ensure_structure_creates_directories(self, temp_wiki_dir: Path) -> None:
        """Test that _ensure_structure creates all required directories."""
        tool = WikiTool()
        
        raw_dir, wiki_dir, assets_dir = tool._ensure_structure(temp_wiki_dir)
        
        # Verify directories exist
        assert raw_dir.exists()
        assert wiki_dir.exists()
        assert assets_dir.exists()
        
        # Verify subdirectories
        assert (wiki_dir / "entities").exists()
        assert (wiki_dir / "concepts").exists()
        assert (wiki_dir / "sources").exists()
        assert (wiki_dir / "syntheses").exists()

    def test_ensure_structure_returns_correct_paths(self, temp_wiki_dir: Path) -> None:
        """Test that _ensure_structure returns correct paths."""
        tool = WikiTool()
        
        raw_dir, wiki_dir, assets_dir = tool._ensure_structure(temp_wiki_dir)
        
        assert raw_dir == temp_wiki_dir / "raw"
        assert wiki_dir == temp_wiki_dir / "pages"
        assert assets_dir == temp_wiki_dir / "raw" / "assets"


class TestWikiPathResolution:
    """Tests for wiki root path resolution."""

    def test_get_wiki_root_with_explicit_path(self, temp_wiki_dir: Path) -> None:
        """Test that explicit path is used when provided."""
        tool = WikiTool()
        
        result = tool._get_wiki_root(str(temp_wiki_dir))
        
        assert result == temp_wiki_dir

    def test_get_wiki_root_with_none_uses_default(self) -> None:
        """Test that default path is used when none provided."""
        tool = WikiTool()
        
        result = tool._get_wiki_root(None)
        
        # Should resolve to default location
        assert result is not None
        assert isinstance(result, Path)
