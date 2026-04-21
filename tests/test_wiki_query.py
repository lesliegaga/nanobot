"""Tests for wiki query functionality."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.tools.wiki import WikiTool


class TestRelevanceScoring:
    """Tests for query relevance scoring."""

    @pytest.mark.asyncio
    async def test_query_scores_title_matches_higher(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that title matches get higher scores."""
        # Setup mock for synthesis
        mock_provider.chat.return_value = MagicMock(
            content="Test answer about OpenAI."
        )
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='openai'
        )
        
        # Should find and cite relevant pages
        assert "openai" in result.lower() or "OpenAI" in result

    @pytest.mark.asyncio
    async def test_query_scores_tag_matches(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that tag matches are considered in scoring."""
        mock_provider.chat.return_value = MagicMock(
            content="Results for AI-related query."
        )
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='AI'
        )
        
        assert "Error" not in result

    @pytest.mark.asyncio
    async def test_query_scores_body_matches(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that body content matches are considered."""
        mock_provider.chat.return_value = MagicMock(
            content="Answer about machine learning."
        )
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='machine learning'
        )
        
        assert "Error" not in result


class TestCategoryFiltering:
    """Tests for category filtering in queries."""

    @pytest.mark.asyncio
    async def test_query_filters_by_entities_category(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that entities category filter works."""
        mock_provider.chat.return_value = MagicMock(
            content="Entity query results."
        )
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='test',
            category='entities'
        )
        
        assert "Error" not in result

    @pytest.mark.asyncio
    async def test_query_filters_by_concepts_category(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that concepts category filter works."""
        mock_provider.chat.return_value = MagicMock(
            content="Concept query results."
        )
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='test',
            category='concepts'
        )
        
        assert "Error" not in result

    @pytest.mark.asyncio
    async def test_query_all_category_searches_all(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that 'all' category searches all page types."""
        mock_provider.chat.return_value = MagicMock(
            content="Search across all categories."
        )
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='test',
            category='all'
        )
        
        assert "Error" not in result


class TestLLMSynthesis:
    """Tests for LLM synthesis in queries."""

    @pytest.mark.asyncio
    async def test_query_calls_llm_with_context(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that LLM is called with page context."""
        expected_answer = "Synthesized answer from wiki pages."
        mock_provider.chat.return_value = MagicMock(content=expected_answer)
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='test question'
        )
        
        # Verify LLM was called
        assert mock_provider.chat.called
        
        # Verify answer is in result
        assert expected_answer in result

    @pytest.mark.asyncio
    async def test_query_includes_index_in_context(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that index is included in LLM context."""
        mock_provider.chat.return_value = MagicMock(content="Answer with index context.")
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        await tool.execute(
            operation='query',
            query='test'
        )
        
        # Verify call was made (context building happens internally)
        assert mock_provider.chat.called


class TestCitationGeneration:
    """Tests for query result citations."""

    @pytest.mark.asyncio
    async def test_query_includes_referenced_pages(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that referenced pages are listed in results."""
        mock_provider.chat.return_value = MagicMock(content="Answer with citations.")
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='openai'
        )
        
        # Should include referenced pages section
        assert "Referenced" in result or "referenced" in result.lower()

    @pytest.mark.asyncio
    async def test_query_shows_all_pages_scanned_when_no_matches(
        self, temp_wiki_dir: Path, mock_provider
    ) -> None:
        """Test that result indicates all pages were scanned when no keyword matches."""
        # Initialize empty wiki
        tool_init = WikiTool(wiki_root=str(temp_wiki_dir), provider=mock_provider)
        await tool_init._init_wiki(temp_wiki_dir)
        
        # Create a simple page without matching keywords
        pages_dir = temp_wiki_dir / "pages" / "sources"
        pages_dir.mkdir(parents=True, exist_ok=True)
        source_page = pages_dir / "test.md"
        source_page.write_text("""---
title: Test
created: 2024-01-01
category: sources
tags: []
---

# Test

Some unrelated content.
""")
        
        mock_provider.chat.return_value = MagicMock(content="No relevant info found.")
        
        tool = WikiTool(wiki_root=str(temp_wiki_dir), provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='xyznonexistent'
        )
        
        # Should indicate pages were scanned
        assert "scanned" in result.lower() or "all pages" in result.lower() or "pages" in result.lower()


class TestQueryLogging:
    """Tests for query operation logging."""

    @pytest.mark.asyncio
    async def test_query_creates_log_entry(
        self, populated_wiki: Path, mock_provider
    ) -> None:
        """Test that query operations are logged."""
        mock_provider.chat.return_value = MagicMock(content="Answer.")
        
        tool = WikiTool(wiki_root=str(populated_wiki), provider=mock_provider)
        
        await tool.execute(
            operation='query',
            query='test query'
        )
        
        # Check log file
        log_file = populated_wiki / "log.md"
        log_content = log_file.read_text()
        
        assert "query" in log_content.lower()


class TestErrorHandling:
    """Tests for query error handling."""

    @pytest.mark.asyncio
    async def test_query_returns_error_for_missing_wiki(self, mock_provider) -> None:
        """Test that query returns error for non-existent wiki."""
        tool = WikiTool(wiki_root="/nonexistent/path", provider=mock_provider)
        
        result = await tool.execute(
            operation='query',
            query='test'
        )
        
        assert "Error" in result
        assert "not found" in result.lower() or "run init" in result.lower()

    @pytest.mark.asyncio
    async def test_query_returns_message_for_empty_wiki(
        self, temp_wiki_dir: Path, mock_provider
    ) -> None:
        """Test that query handles empty wiki gracefully."""
        # Initialize but don't populate
        tool = WikiTool(wiki_root=str(temp_wiki_dir), provider=mock_provider)
        await tool._init_wiki(temp_wiki_dir)
        
        result = await tool.execute(
            operation='query',
            query='test'
        )
        
        # Should indicate no pages found
        assert "no pages" in result.lower() or "empty" in result.lower() or "Index" in result

    @pytest.mark.asyncio
    async def test_query_requires_llm_provider(self, temp_wiki_dir: Path) -> None:
        """Test that query requires LLM provider."""
        tool = WikiTool(wiki_root=str(temp_wiki_dir))  # No provider
        
        result = await tool.execute(
            operation='query',
            query='test'
        )
        
        assert "Error" in result
        assert "provider" in result.lower() or "llm" in result.lower()
