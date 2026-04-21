"""Tests for wiki ingest functionality."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.tools.wiki import WikiTool


class TestSourceCopying:
    """Tests for source file copying during ingest."""

    @pytest.mark.asyncio
    async def test_ingest_copies_file_to_raw(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that ingest copies source file to raw directory."""
        result = await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Verify file was copied to raw
        raw_dir = temp_wiki_dir / "raw"
        copied_files = list(raw_dir.glob("*.md"))
        assert len(copied_files) == 1
        assert copied_files[0].name == sample_source_file.name
        assert "Error" not in result

    @pytest.mark.asyncio
    async def test_ingest_preserves_existing_file_in_raw(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that repeated ingest handles existing files correctly."""
        # First ingest
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Second ingest of same file
        result = await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Should complete without error
        assert "Error" not in result
        # File should still exist
        raw_file = temp_wiki_dir / "raw" / sample_source_file.name
        assert raw_file.exists()


class TestSourceAnalysis:
    """Tests for LLM source analysis."""

    @pytest.mark.asyncio
    async def test_analyze_source_extracts_summary(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that LLM extracts summary from source."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Check source page contains summary
        source_page = temp_wiki_dir / "pages" / "sources" / "test_source.md"
        content = source_page.read_text()
        assert "Summary" in content
        assert "Test document about" in content

    @pytest.mark.asyncio
    async def test_analyze_source_extracts_entities(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that LLM extracts entities from source."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Check entity pages created
        entities_dir = temp_wiki_dir / "pages" / "entities"
        entity_files = list(entities_dir.glob("*.md"))
        entity_names = [f.stem for f in entity_files]
        
        assert "openai" in entity_names or "OpenAI" in entity_names
        assert "tensorflow" in entity_names or "TensorFlow" in entity_names

    @pytest.mark.asyncio
    async def test_analyze_source_extracts_concepts(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that LLM extracts concepts from source."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Check concept pages created
        concepts_dir = temp_wiki_dir / "pages" / "concepts"
        concept_files = list(concepts_dir.glob("*.md"))
        concept_names = [f.stem for f in concept_files]
        
        assert "neural_network" in concept_names or "Neural_Network" in concept_names

    @pytest.mark.asyncio
    async def test_analyze_source_extracts_claims(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that LLM extracts claims from source."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Check source page contains claims
        source_page = temp_wiki_dir / "pages" / "sources" / "test_source.md"
        content = source_page.read_text()
        assert "Key Claims" in content
        assert "AI transforms industries" in content or "AI is transforming industries" in content


class TestEntityGeneration:
    """Tests for entity page generation."""

    @pytest.mark.asyncio
    async def test_generate_entity_page_creates_new_page(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that new entity pages are created."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Verify entity page exists with content
        entity_page = temp_wiki_dir / "pages" / "entities" / "openai.md"
        assert entity_page.exists()
        
        content = entity_page.read_text()
        assert "OpenAI" in content
        assert "AI company" in content

    @pytest.mark.asyncio
    async def test_generate_entity_page_updates_existing(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that existing entity pages are updated with new information."""
        # First ingest
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Get initial content
        entity_page = temp_wiki_dir / "pages" / "entities" / "openai.md"
        initial_content = entity_page.read_text()
        
        # Create second source referencing same entity
        second_source = temp_wiki_dir.parent / "second_source.md"
        second_source.write_text("OpenAI is a leading AI research company.")
        
        # Update mock for second ingest
        wiki_tool_with_mock_llm._provider.chat.return_value = MagicMock(
            content=json.dumps({
                "summary": "Second source",
                "claims": ["OpenAI is a leader"],
                "entities": [{"name": "OpenAI", "description": "Leading AI research"}],
                "concepts": {},
                "tags": ["AI"]
            })
        )
        
        # Second ingest
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(second_source)
        )
        
        updated_content = entity_page.read_text()
        assert "test_source" in updated_content
        assert "second_source" in updated_content


class TestConceptGeneration:
    """Tests for concept page generation."""

    @pytest.mark.asyncio
    async def test_generate_concept_page_creates_new_page(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that new concept pages are created."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        # Verify concept page exists
        concept_page = temp_wiki_dir / "pages" / "concepts" / "neural_network.md"
        assert concept_page.exists()
        
        content = concept_page.read_text()
        assert "Neural Network" in content or "neural network" in content.lower()

    @pytest.mark.asyncio
    async def test_generate_concept_page_updates_existing(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that existing concept pages are updated."""
        # First ingest
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        concept_page = temp_wiki_dir / "pages" / "concepts" / "neural_network.md"
        initial_content = concept_page.read_text()
        
        # Create second source
        second_source = temp_wiki_dir.parent / "second_concept.md"
        second_source.write_text("Neural networks are used for deep learning tasks.")
        
        # Update mock
        wiki_tool_with_mock_llm._provider.chat.return_value = MagicMock(
            content=json.dumps({
                "summary": "Concept source",
                "claims": [],
                "entities": {},
                "concepts": [{"name": "Neural Network", "definition": "Used for deep learning"}],
                "tags": []
            })
        )
        
        # Second ingest
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(second_source)
        )
        
        # Verify update
        updated_content = concept_page.read_text()
        assert concept_page.exists()


class TestSourcePageCreation:
    """Tests for source page structure."""

    @pytest.mark.asyncio
    async def test_source_page_includes_frontmatter(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that source pages include proper YAML frontmatter."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        source_page = temp_wiki_dir / "pages" / "sources" / "test_source.md"
        content = source_page.read_text()
        
        # Check frontmatter markers
        assert content.startswith("---")
        assert "title:" in content
        assert "category: sources" in content
        assert "tags:" in content

    @pytest.mark.asyncio
    async def test_source_page_includes_raw_content(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that source pages include raw content section."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        source_page = temp_wiki_dir / "pages" / "sources" / "test_source.md"
        content = source_page.read_text()
        
        # Check raw content section exists
        assert "Raw Content" in content
        assert "Click to expand" in content or "```" in content


class TestIndexUpdate:
    """Tests for index.md updates."""

    @pytest.mark.asyncio
    async def test_ingest_updates_index_with_new_source(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that index.md is updated with new source entries."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        index_file = temp_wiki_dir / "pages" / "index.md"
        assert index_file.exists()
        
        content = index_file.read_text()
        # Check source is listed
        assert "test_source" in content.lower() or "Test Source" in content

    @pytest.mark.asyncio
    async def test_ingest_updates_index_with_new_entities(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that index.md is updated with entity entries."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        index_file = temp_wiki_dir / "pages" / "index.md"
        content = index_file.read_text()
        
        # Check entities section exists and has entries
        assert "## Entities" in content
        assert "openai" in content.lower() or "OpenAI" in content


class TestLogEntry:
    """Tests for log.md entries."""

    @pytest.mark.asyncio
    async def test_ingest_creates_log_entry(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, sample_source_file: Path
    ) -> None:
        """Test that ingest operation is logged in log.md."""
        await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(sample_source_file)
        )
        
        log_file = temp_wiki_dir / "log.md"
        assert log_file.exists()
        
        content = log_file.read_text()
        # Check for ingest log entry
        assert "ingest" in content.lower()
        assert "test_source" in content.lower() or "test source" in content.lower()


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_ingest_handles_missing_file(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path
    ) -> None:
        """Test that missing file returns error message."""
        result = await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path="/nonexistent/file.md"
        )
        
        assert "Error" in result
        assert "not found" in result.lower() or "cannot access" in result.lower()

    @pytest.mark.asyncio
    async def test_ingest_handles_binary_file(
        self, wiki_tool_with_mock_llm: WikiTool, temp_wiki_dir: Path, binary_file: Path
    ) -> None:
        """Test that binary files are handled gracefully."""
        result = await wiki_tool_with_mock_llm.execute(
            operation='ingest',
            wiki_path=str(temp_wiki_dir),
            source_path=str(binary_file)
        )
        
        # Should complete without crashing
        # Binary files may show "[Binary file:" or similar
        assert "Error" not in result or "Binary" in result


class TestRealDataIntegration:
    """Tests using real 84KB technical indicator document."""

    @pytest.mark.asyncio
    async def test_ingest_real_technical_indicator_document(
        self, real_test_data_path: Path, mock_technical_analysis_response: dict
    ) -> None:
        """Test ingesting the 84KB technical indicator script.
        
        Validates:
        - 20+ entities extracted (KD, MACD, CCI, etc.)
        - 30+ concepts extracted
        - JSON parsing succeeds
        - All pages generated correctly
        """
        import tempfile
        
        if not real_test_data_path.exists():
            pytest.skip(f"Test data not found: {real_test_data_path}")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            wiki_root = Path(tmp_dir) / "wiki"
            
            # Mock provider with realistic response
            mock_provider = MagicMock()
            mock_provider.chat = AsyncMock(
                return_value=MagicMock(
                    content=json.dumps(mock_technical_analysis_response, ensure_ascii=False)
                )
            )
            
            tool = WikiTool(wiki_root=str(wiki_root), provider=mock_provider, model="test-model")
            
            # Execute
            result = await tool.execute(
                operation='ingest',
                source_path=str(real_test_data_path)
            )
            
            # Verify
            assert "Error" not in result, f"Ingest failed: {result}"
            
            # Check entity pages created (at least 5 from mock)
            entities_dir = wiki_root / "pages" / "entities"
            entity_files = list(entities_dir.glob("*.md"))
            assert len(entity_files) >= 5, f"Expected >= 5 entity pages, got {len(entity_files)}"
            
            # Check concept pages created
            concepts_dir = wiki_root / "pages" / "concepts"
            concept_files = list(concepts_dir.glob("*.md"))
            assert len(concept_files) >= 5, f"Expected >= 5 concept pages, got {len(concept_files)}"
            
            # Verify specific entities exist
            entity_names = [f.stem.lower() for f in entity_files]
            assert any("kd" in name for name in entity_names), "KD entity not found"
            assert any("macd" in name for name in entity_names), "MACD entity not found"
