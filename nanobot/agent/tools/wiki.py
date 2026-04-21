"""LLM Wiki tool for building personal knowledge bases.

This module implements the LLM Wiki pattern from docs/llm-wiki.md:
- Three-layer architecture: Raw sources -> Wiki -> Schema
- Three core operations: ingest, query, lint
- Two special files: index.md (content catalog) and log.md (chronological log)
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from nanobot.agent.tools.base import Tool

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider


# JSON Schema for source analysis
SOURCE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 paragraph comprehensive summary of the key points"
        },
        "claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of key claims or findings from the source"
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["name", "description"]
            },
            "description": "List of significant entities mentioned in the source"
        },
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "definition": {"type": "string"}
                },
                "required": ["name", "definition"]
            },
            "description": "List of key concepts discussed in the source"
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of relevant topic tags"
        }
    },
    "required": ["summary", "claims", "entities", "concepts", "tags"]
}

# JSON Prompt template for source analysis
SOURCE_ANALYSIS_JSON_PROMPT = """Analyze the source document and respond ONLY with valid JSON.

Response format:
{
    "summary": "2-3 paragraph comprehensive summary of the key points",
    "claims": ["claim 1", "claim 2", ...],
    "entities": [
        {"name": "Entity Name", "description": "Brief description of what/who this is"}
    ],
    "concepts": [
        {"name": "Concept Name", "definition": "Brief definition or explanation"}
    ],
    "tags": ["tag1", "tag2", ...]
}

IMPORTANT: Respond ONLY with the JSON object, no other text."""


class WikiTool(Tool):
    """Tool for managing LLM Wiki knowledge bases.

    The wiki is a persistent, compounding knowledge base where:
    - Raw sources are immutable source documents
    - Wiki pages are LLM-generated markdown files
    - Schema defines conventions and workflows
    """

    # Configuration constants
    MAX_CONTENT_LENGTH = 30000  # Source content truncation length
    MAX_QUERY_PAGES = 15  # Max pages to include in query context
    STALE_THRESHOLD_DAYS = 90  # Days before a page is considered stale
    MAX_SOURCE_SIZE = 50 * 1024 * 1024  # 50MB file size limit
    LLM_TIMEOUT_SECONDS = 120  # LLM call timeout
    MAX_ANALYSIS_TOKENS = 4096  # Max tokens for LLM analysis

    # Content truncation limits
    QUERY_CONTENT_TRUNCATE = 3000  # Page content truncate for queries
    INDEX_PREVIEW_LENGTH = 2000  # Index content preview on error
    INDEX_CONTEXT_LENGTH = 2000  # Index context for LLM queries
    RAW_CONTENT_DISPLAY_LIMIT = 50000  # Raw content display limit in pages
    CONTRADICTION_ANALYSIS_LIMIT = 10  # Max pages for contradiction analysis
    CONTRADICTION_SUMMARY_LENGTH = 1000  # Summary length for contradiction check
    CONTRADICTION_MAX_TOKENS = 2048  # Max tokens for contradiction detection
    QUALITY_ANALYSIS_LENGTH = 5000  # Content length for quality analysis
    QUALITY_MAX_TOKENS = 1024  # Max tokens for quality analysis
    QUERY_LOG_TRUNCATE_LENGTH = 80  # Query log entry truncate length

    def __init__(
        self,
        wiki_root: str | Path | None = None,
        provider: "LLMProvider | None" = None,
        model: str | None = None,
    ):
        """Initialize the wiki tool.

        Args:
            wiki_root: Root directory for the wiki. If None, uses workspace/wiki.
            provider: LLM provider for generating content. Required for all
                      operations except init and list_sources.
            model: Model name to use for generation.
        """
        self._wiki_root = Path(wiki_root) if wiki_root else None
        self._provider = provider
        self._model = model

    def _require_llm(self) -> None:
        """Raise if LLM provider is not configured."""
        if not self._provider:
            raise RuntimeError(
                "Wiki tool requires an LLM provider. "
                "Please configure an LLM provider with a valid API key in your nanobot config."
            )

    @property
    def name(self) -> str:
        return "wiki"

    @property
    def description(self) -> str:
        return (
            "Manage an LLM-powered personal knowledge base (wiki). "
            "Supports ingesting sources, querying wiki content, and linting for issues. "
            "The wiki maintains an index.md (content catalog) and log.md (chronological log)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["ingest", "query", "lint", "init", "list_sources"],
                    "description": (
                        "Operation to perform: 'ingest' (add source to wiki), "
                        "'query' (search wiki content), 'lint' (health check), "
                        "'init' (create wiki structure), 'list_sources' (list raw sources)"
                    ),
                },
                "wiki_path": {
                    "type": "string",
                    "description": "Path to wiki root directory. Defaults to workspace/wiki",
                },
                "source_path": {
                    "type": "string",
                    "description": "For ingest: path to source file or directory to ingest",
                },
                "query": {
                    "type": "string",
                    "description": "For query: search query or question",
                },
                "category": {
                    "type": "string",
                    "enum": ["entities", "concepts", "sources", "syntheses", "all"],
                    "description": "Category filter for query/list operations",
                },
                "create_summary": {
                    "type": "boolean",
                    "description": "For ingest: whether to create a summary page (default: true)",
                },
                "check_type": {
                    "type": "string",
                    "enum": ["orphans", "contradictions", "stale", "missing_links", "quality", "all"],
                    "description": "For lint: specific check to run",
                },
            },
            "required": ["operation"],
        }

    def _get_wiki_root(self, wiki_path: str | None, workspace: str | Path | None = None) -> Path:
        """Resolve wiki root directory."""
        if wiki_path:
            return Path(wiki_path).expanduser().resolve()
        if self._wiki_root:
            return self._wiki_root
        if workspace:
            return Path(workspace).expanduser().resolve() / "wiki"
        return Path.home() / ".nanobot" / "workspace" / "wiki"

    def _ensure_structure(self, wiki_root: Path) -> tuple[Path, Path, Path]:
        """Ensure wiki directory structure exists.

        Returns:
            Tuple of (raw_dir, wiki_pages_dir, assets_dir)
        """
        raw_dir = wiki_root / "raw"
        wiki_pages_dir = wiki_root / "pages"  # Use 'pages' to avoid confusion with wiki_root name
        assets_dir = raw_dir / "assets"

        raw_dir.mkdir(parents=True, exist_ok=True)
        wiki_pages_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Ensure page subdirectories exist for ingestion without prior init
        for subdir in ("entities", "concepts", "sources", "syntheses"):
            (wiki_pages_dir / subdir).mkdir(parents=True, exist_ok=True)

        return raw_dir, wiki_pages_dir, assets_dir

    def _get_index_path(self, wiki_root: Path) -> Path:
        """Get path to index.md."""
        return wiki_root / "pages" / "index.md"

    def _get_log_path(self, wiki_root: Path) -> Path:
        """Get path to log.md."""
        return wiki_root / "log.md"

    def _read_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter from markdown content.

        Returns:
            Tuple of (frontmatter dict, remaining content)
        """
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        frontmatter_text = parts[1].strip()
        body = parts[2].strip()

        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError:
            frontmatter = {}

        return frontmatter, body

    def _write_frontmatter(self, data: dict[str, Any]) -> str:
        """Generate YAML frontmatter string."""
        lines = ["---"]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)

    def _sanitize_filename(self, name: str) -> str:
        """Convert a string to a safe filename."""
        # Replace spaces with underscores and remove unsafe characters
        safe = re.sub(r'[^\w\s-]', '', name).strip()
        safe = re.sub(r'[-\s]+', '_', safe)
        return safe.lower()

    def _validate_source_path(
        self,
        source_path: str,
        wiki_root: Path,
        allowed_paths: list[Path] | None = None
    ) -> Path:
        """Validate that source path is within allowed directories.

        Args:
            source_path: Path to the source file
            wiki_root: Root directory of the wiki
            allowed_paths: Additional allowed paths beyond wiki_root

        Returns:
            Resolved Path object

        Raises:
            ValueError: If path is outside allowed directories
        """
        source_file = Path(source_path).expanduser().resolve()

        # Check if within wiki_root
        if source_file.is_relative_to(wiki_root):
            return source_file

        # Check additional allowed paths
        if allowed_paths:
            for allowed in allowed_paths:
                allowed_path = Path(allowed).expanduser().resolve()
                if source_file.is_relative_to(allowed_path):
                    return source_file

        import tempfile
        temp_dirs = [Path(tempfile.gettempdir()).resolve()]
        try:
            temp_dirs.append(Path(os.environ.get("TMPDIR", "/tmp")).resolve())
        except Exception:
            pass
        
        original_path = Path(source_path)
        has_traversal = ".." in original_path.parts
        
        for temp_dir in temp_dirs:
            try:
                if not has_traversal and source_file.is_relative_to(temp_dir):
                    return source_file
            except Exception:
                continue
        
        try:
            project_root = Path(__file__).parent.parent.parent.parent.resolve()
            if not has_traversal and source_file.is_relative_to(project_root):
                return source_file
        except Exception:
            pass

        raise ValueError(f"Access denied: {source_path}")

    def _validate_file_size(
        self,
        source_file: Path,
        max_size_mb: int | None = None
    ) -> None:
        """Validate file size is within limit.

        Args:
            source_file: Path to the file to check
            max_size_mb: Maximum allowed size in megabytes (defaults to 50MB)

        Raises:
            ValueError: If file exceeds size limit or file cannot be accessed
        """
        max_size_bytes = (max_size_mb or 50) * 1024 * 1024

        if not source_file.exists():
            raise ValueError(f"Cannot access file: {source_file}")

        if source_file.stat().st_size > max_size_bytes:
            raise ValueError(f"File too large: {source_file.name}")

    def _extract_page_summary(self, frontmatter: dict[str, Any], body: str, max_length: int = 200) -> str:
        """Extract a summary from page frontmatter or body.

        Args:
            frontmatter: Page frontmatter dictionary
            body: Page body content
            max_length: Maximum length of summary (default 200)

        Returns:
            Truncated summary string
        """
        # Try to get summary from frontmatter first
        summary = frontmatter.get("summary", "").strip()

        # If no summary in frontmatter, extract from body
        if not summary and body:
            # Remove markdown headers and get first paragraph
            lines = body.split("\n")
            for line in lines:
                line = line.strip()
                # Skip empty lines and markdown headers
                if line and not line.startswith("#") and not line.startswith("---"):
                    summary = line
                    break

        # Truncate if needed
        if len(summary) > max_length:
            summary = summary[:max_length].rsplit(" ", 1)[0] + "..."

        return summary if summary else "-"

    def _extract_page_type(self, frontmatter: dict[str, Any], default_category: str) -> str:
        """Extract type information from frontmatter."""
        # Check for explicit type field
        page_type = frontmatter.get("type", "")
        if page_type:
            return page_type

        # Infer from category
        return default_category[:-1] if default_category.endswith("s") else default_category

    def _extract_definition(self, body: str) -> str:
        """Extract definition/first paragraph from page body."""
        if not body:
            return "-"

        lines = body.split("\n")
        for line in lines:
            line = line.strip()
            # Skip empty lines, headers, and frontmatter markers
            if line and not line.startswith("#") and not line.startswith("---"):
                # Look for definition pattern
                if ":" in line and len(line) < 200:
                    return line.split(":", 1)[1].strip()[:100]
                elif len(line) < 100:
                    return line[:100]

        return "-"

    def _count_entity_sources(self, wiki_root: Path, entity_name: str) -> int:
        """Count how many sources mention a specific entity.

        Args:
            wiki_root: Root path of the wiki
            entity_name: Name of the entity to search for

        Returns:
            Number of sources mentioning the entity
        """
        sources_dir = wiki_root / "pages" / "sources"
        if not sources_dir.exists():
            return 0

        count = 0
        entity_link = f"[[{entity_name}]]"

        for source_file in sources_dir.glob("*.md"):
            try:
                content = source_file.read_text(encoding="utf-8")
                if entity_link in content or entity_name in content:
                    count += 1
            except Exception:
                continue

        return count

    def _log_entry(self, wiki_root: Path, entry_type: str, description: str) -> None:
        """Prepend an entry to the chronological log (newest first)."""
        log_path = self._get_log_path(wiki_root)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"## [{timestamp}] {entry_type} | {description}\n"

        if log_path.exists():
            content = log_path.read_text(encoding="utf-8")
        else:
            content = "# Wiki Log\n\nChronological record of all wiki operations.\n"

        # Find where to insert (after the first non-empty, non-header line)
        lines = content.split("\n")
        insert_pos = len(lines)
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith("#"):
                insert_pos = i
                break

        new_lines = lines[:insert_pos] + ["", entry] + lines[insert_pos:]
        log_path.write_text("\n".join(new_lines), encoding="utf-8")

    async def _init_wiki(self, wiki_root: Path) -> str:
        """Initialize wiki directory structure."""
        raw_dir, wiki_dir, assets_dir = self._ensure_structure(wiki_root)

        # Create AGENTS.md schema
        agents_md = wiki_root / "AGENTS.md"
        if not agents_md.exists():
            schema_content = """# Wiki Schema

This document defines the structure and conventions for this LLM Wiki.

## Directory Structure

```
wiki_root/
├── raw/              # Original source documents (immutable)
│   └── assets/       # Images and attachments
├── pages/            # LLM-generated pages
│   ├── index.md      # Content catalog
│   ├── entities/     # Entity pages (people, organizations, etc.)
│   ├── concepts/     # Concept pages (ideas, theories, etc.)
│   ├── sources/      # Source summaries
│   └── syntheses/    # Synthesis and analysis pages
└── log.md            # Chronological operation log
```

## Page Conventions

### Frontmatter
All wiki pages should include YAML frontmatter:
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
category: entities | concepts | sources | syntheses
tags: [tag1, tag2]
sources: [source1, source2]  # For entity/concept pages
---
```

### Cross-References
- Use `[[Page Name]]` for internal wiki links
- Use `[descriptive text](path/to/file.md)` for explicit links
- Backlinks should be maintained automatically

### Source Pages
- One page per ingested source
- Include source metadata (author, date, URL if applicable)
- Extract key claims and entities

### Entity/Concept Pages
- Aggregate information from multiple sources
- Include contradictions section when sources disagree
- Link to all relevant source pages

## Workflows

### Ingesting a Source
1. Copy source to `raw/` (or note its location)
2. Read and analyze the source
3. Create/update source page in `pages/sources/`
4. Extract entities and concepts
5. Create/update entity/concept pages
6. Update index.md
7. Log the operation

### Answering a Question
1. Search index.md for relevant pages
2. Read relevant entity/concept/source pages
3. Synthesize answer with citations
4. File valuable analysis back to wiki

### Linting
Periodically run checks for:
- Orphan pages (no inbound links)
- Stale claims (superseded by newer sources)
- Missing cross-references
- Contradictions between pages
"""
            agents_md.write_text(schema_content, encoding="utf-8")

        # Create initial index.md
        index_path = self._get_index_path(wiki_root)
        if not index_path.exists():
            index_content = """# Wiki Index

Content catalog for the LLM Wiki.

## Sources

| Source | Summary | Date | Tags |
|--------|---------|------|------|

## Entities

| Entity | Type | Sources | Last Updated |
|--------|------|---------|--------------|

## Concepts

| Concept | Definition | Sources | Last Updated |
|---------|------------|---------|--------------|

## Syntheses

| Synthesis | Description | Sources | Last Updated |
|-----------|-------------|---------|--------------|

---

*This index is maintained automatically. Last updated: never*
"""
            index_path.write_text(index_content, encoding="utf-8")

        # Create initial log.md
        log_path = self._get_log_path(wiki_root)
        if not log_path.exists():
            log_content = """# Wiki Log

Chronological record of all wiki operations.

## [{}] init | Wiki initialized

Created wiki structure at {}
""".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), wiki_root)
            log_path.write_text(log_content, encoding="utf-8")

        # Create subdirectories
        for subdir in ["entities", "concepts", "sources", "syntheses"]:
            (wiki_dir / subdir).mkdir(exist_ok=True)

        return (
            f"Wiki initialized at {wiki_root}\n"
            f"  - Raw sources: {raw_dir}\n"
            f"  - Wiki pages: {wiki_dir}\n"
            f"  - Schema: {agents_md}\n"
            f"  - Index: {index_path}\n"
            f"  - Log: {log_path}"
        )

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Call LLM to generate content.

        Raises RuntimeError if provider is not configured.
        Returns error message if timeout occurs.
        """
        self._require_llm()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            async with asyncio.timeout(self.LLM_TIMEOUT_SECONDS):
                response = await self._provider.chat(
                    messages=messages,
                    model=self._model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            return response.content or ""
        except asyncio.TimeoutError:
            return f"Error: LLM call timed out after {self.LLM_TIMEOUT_SECONDS} seconds"

    async def _call_llm_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Call LLM and parse response as JSON with retry mechanism.

        This method is designed for structured JSON output with automatic
        retry on parse failures.

        Args:
            system_prompt: System prompt instructing LLM to return JSON.
            user_prompt: User prompt with the actual request.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            max_retries: Maximum number of retry attempts on parse failure.

        Returns:
            Parsed JSON as dictionary.

        Raises:
            RuntimeError: If provider is not configured.
            ValueError: If JSON parsing fails after all retries.
        """
        self._require_llm()

        last_error: Exception | None = None
        content = ""

        for attempt in range(1, max_retries + 1):
            try:
                async with asyncio.timeout(self.LLM_TIMEOUT_SECONDS):
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                    response = await self._provider.chat(
                        messages=messages,
                        model=self._model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                content = response.content or ""

                # Try to parse JSON
                result = self._parse_json_response(content)
                return result

            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(
                    f"JSON parse error on attempt {attempt}/{max_retries}: {e}. "
                    f"Response preview: {content[:200]}..."
                )
                if attempt < max_retries:
                    user_prompt = (
                        f"{user_prompt}\n\n"
                        "IMPORTANT: Your previous response was not valid JSON. "
                        "Please respond ONLY with a valid JSON object, no markdown formatting, "
                        "no explanations, just the JSON."
                    )
                continue

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error on attempt {attempt}/{max_retries}: {e}")
                if attempt < max_retries:
                    continue
                raise

        error_msg = f"Failed to parse JSON response after {max_retries} attempts. Last error: {last_error}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Parse JSON from LLM response with multiple fallback strategies.

        Attempts multiple strategies to extract valid JSON:
        1. Direct JSON parse
        2. Extract JSON from markdown code blocks
        3. Extract JSON between first { and last }

        Args:
            content: Raw response content from LLM.

        Returns:
            Parsed JSON dictionary.

        Raises:
            json.JSONDecodeError: If all parsing strategies fail.
        """
        content = content.strip()

        # Strategy 1: Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown code block
        patterns = [
            r'```json\s*\n(.*?)\n```',
            r'```\s*\n(.*?)\n```',
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    continue

        # Strategy 3: Extract between first { and last }
        try:
            start = content.index('{')
            end = content.rindex('}')
            if start < end:
                return json.loads(content[start:end+1])
        except (ValueError, json.JSONDecodeError):
            pass

        raise json.JSONDecodeError(
            f"Could not extract valid JSON from response. Content preview: {content[:200]}...",
            content,
            0
        )

    async def _analyze_source_with_llm(self, content: str, source_name: str) -> dict[str, Any]:
        """Use LLM to analyze source content and extract structured information.

        This method uses JSON structured output for reliable parsing.
        On parse failure, returns empty lists/dicts and logs the error.

        Returns:
            Dict with summary, claims, entities, concepts, tags.
            Entities and concepts are returned as dicts for backward compatibility.
        """
        truncated_content = content[:self.MAX_CONTENT_LENGTH] if len(content) > self.MAX_CONTENT_LENGTH else content
        user_prompt = f"Source: {source_name}\n\nContent:\n{truncated_content}\n\nPlease analyze this source and extract the structured information as JSON."

        try:
            result = await self._call_llm_json(
                SOURCE_ANALYSIS_JSON_PROMPT,
                user_prompt,
                temperature=0.3,
                max_tokens=self.MAX_ANALYSIS_TOKENS,
                max_retries=3
            )

            # Validate and normalize the result to legacy format (dicts for entities/concepts)
            normalized: dict[str, Any] = {
                "summary": result.get("summary", ""),
                "claims": result.get("claims", []) if isinstance(result.get("claims"), list) else [],
                "entities": {},
                "concepts": {},
                "tags": result.get("tags", []) if isinstance(result.get("tags"), list) else [],
            }

            # Convert entities list to dict for backward compatibility
            entities_list = result.get("entities", [])
            if isinstance(entities_list, list):
                for entity in entities_list:
                    if isinstance(entity, dict) and "name" in entity:
                        normalized["entities"][entity["name"]] = entity.get("description", "")

            # Convert concepts list to dict for backward compatibility
            concepts_list = result.get("concepts", [])
            if isinstance(concepts_list, list):
                for concept in concepts_list:
                    if isinstance(concept, dict) and "name" in concept:
                        normalized["concepts"][concept["name"]] = concept.get("definition", "")

            return normalized

        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Failed to analyze source '{source_name}' with JSON: {e}. Returning empty analysis.")
            # Return empty analysis on failure instead of raising
            return {
                "summary": "",
                "claims": [],
                "entities": {},
                "concepts": {},
                "tags": [],
            }

    async def _generate_entity_page(
        self,
        wiki_root: Path,
        entity_name: str,
        entity_desc: str,
        source_name: str,
    ) -> Path | None:
        """Generate or update an entity page using LLM with content synthesis."""
        wiki_dir = wiki_root / "pages"
        entity_file = wiki_dir / "entities" / f"{self._sanitize_filename(entity_name)}.md"

        today = datetime.now().strftime("%Y-%m-%d")

        if entity_file.exists():
            existing_content = entity_file.read_text(encoding="utf-8")
            frontmatter, body = self._read_frontmatter(existing_content)

            sources = frontmatter.get("sources", [])
            if source_name not in sources:
                sources.append(source_name)

            frontmatter["sources"] = sources
            frontmatter["updated"] = today

            system_prompt = """You are a knowledge base writer. Update an entity page by synthesizing existing content with new information.

Rules:
1. Maintain the overall structure: Overview, Key Details, Sources
2. Integrate new information naturally into existing sections
3. Highlight any contradictions or different perspectives
4. Keep the tone encyclopedic and neutral
5. Use proper markdown formatting

Return the complete updated page content (without frontmatter)."""

            user_prompt = f"""Entity: {entity_name}

Existing page content:
{body[:3000]}

New information from source '{source_name}':
{entity_desc}

Please re-synthesize the entity page, integrating the new information.
"""

            try:
                synthesized_content = await self._call_llm(
                    system_prompt, user_prompt, temperature=0.3, max_tokens=2048
                )

                if synthesized_content.startswith("---"):
                    parts = synthesized_content.split("---", 2)
                    if len(parts) >= 3:
                        synthesized_content = parts[2].strip()

                updated_content = self._write_frontmatter(frontmatter) + "\n\n" + synthesized_content
            except Exception as e:
                logger.warning(f"LLM synthesis failed for {entity_name}, falling back to append: {e}")
                new_section = f"\n\n## From: {source_name}\n\n{entity_desc}\n"
                updated_content = self._write_frontmatter(frontmatter) + "\n" + body + new_section
        else:
            system_prompt = """You are a knowledge base writer. Create a comprehensive entity page.

Write a well-structured markdown page about this entity. Include:
1. Overview/Definition
2. Key characteristics or details
3. Significance or importance
4. Related information

Format with proper markdown headers."""

            user_prompt = f"Entity: {entity_name}\nDescription from source: {entity_desc}\nSource: {source_name}\n\nWrite a comprehensive entity page."

            generated_content = await self._call_llm(system_prompt, user_prompt, temperature=0.4)

            frontmatter = {
                "title": entity_name,
                "created": today,
                "updated": today,
                "category": "entities",
                "tags": [],
                "sources": [source_name],
            }

            updated_content = f"""{self._write_frontmatter(frontmatter)}

# {entity_name}

{generated_content}

---

*Entity extracted from: [[{source_name}]]*
"""

        entity_file.write_text(updated_content, encoding="utf-8")
        await self._update_backlinks(wiki_root, entity_name)
        return entity_file

    async def _generate_concept_page(
        self,
        wiki_root: Path,
        concept_name: str,
        concept_desc: str,
        source_name: str,
    ) -> Path | None:
        """Generate or update a concept page using LLM with content synthesis."""
        wiki_dir = wiki_root / "pages"
        concept_file = wiki_dir / "concepts" / f"{self._sanitize_filename(concept_name)}.md"

        today = datetime.now().strftime("%Y-%m-%d")

        if concept_file.exists():
            # Update existing concept page with LLM synthesis
            existing_content = concept_file.read_text(encoding="utf-8")
            frontmatter, body = self._read_frontmatter(existing_content)

            sources = frontmatter.get("sources", [])
            if source_name not in sources:
                sources.append(source_name)

            frontmatter["sources"] = sources
            frontmatter["updated"] = today

            # Use LLM to re-synthesize content
            system_prompt = """You are a knowledge base writer. Update a concept page by synthesizing existing content with new information.

Rules:
1. Maintain structure: Definition, Key Aspects, Examples, Related Concepts
2. Integrate new information naturally
3. Highlight different interpretations or applications
4. Keep definitions clear and precise
5. Use proper markdown formatting

Return the complete updated page content (without frontmatter)."""

            user_prompt = f"""Concept: {concept_name}

Existing page content:
{body[:3000]}

New information from source '{source_name}':
{concept_desc}

Please re-synthesize the concept page, integrating the new information.
"""

            try:
                synthesized_content = await self._call_llm(
                    system_prompt, user_prompt, temperature=0.3, max_tokens=2048
                )

                if synthesized_content.startswith("---"):
                    parts = synthesized_content.split("---", 2)
                    if len(parts) >= 3:
                        synthesized_content = parts[2].strip()

                updated_content = self._write_frontmatter(frontmatter) + "\n\n" + synthesized_content
            except Exception as e:
                logger.warning(f"LLM synthesis failed for {concept_name}, falling back to append: {e}")
                new_section = f"\n\n## Perspective from: {source_name}\n\n{concept_desc}\n"
                updated_content = self._write_frontmatter(frontmatter) + "\n" + body + new_section
        else:
            # Create new concept page with LLM
            system_prompt = """You are a knowledge base writer. Create a comprehensive concept page.

Write a well-structured markdown page explaining this concept. Include:
1. Definition
2. Key aspects or components
3. Examples or applications
4. Related concepts

Format with proper markdown headers."""

            user_prompt = f"Concept: {concept_name}\nDescription from source: {concept_desc}\nSource: {source_name}\n\nWrite a comprehensive concept page."

            generated_content = await self._call_llm(system_prompt, user_prompt, temperature=0.4)

            frontmatter = {
                "title": concept_name,
                "created": today,
                "updated": today,
                "category": "concepts",
                "tags": [],
                "sources": [source_name],
            }

            updated_content = f"""{self._write_frontmatter(frontmatter)}

# {concept_name}

{generated_content}

---

*Concept extracted from: [[{source_name}]]*
"""

        concept_file.write_text(updated_content, encoding="utf-8")

        # Update backlinks
        await self._update_backlinks(wiki_root, concept_name)

        return concept_file

    async def _ingest_source(
        self,
        wiki_root: Path,
        source_path: str,
        create_summary: bool = True,
    ) -> str:
        """Ingest a source file into the wiki."""
        raw_dir, wiki_dir, assets_dir = self._ensure_structure(wiki_root)

        source_file = Path(source_path).expanduser().resolve()

        if not source_file.exists():
            return f"Error: Source not found: {source_path}"

        # Validate source path is within allowed directories
        try:
            source_file = self._validate_source_path(source_path, wiki_root)
        except ValueError as e:
            return f"Error: {e}"

        # Validate file size
        try:
            self._validate_file_size(source_file, max_size_mb=50)
        except ValueError as e:
            return f"Error: {e}"

        # Copy to raw directory if not already there
        if not str(source_file).startswith(str(raw_dir)):
            dest_file = raw_dir / source_file.name
            import shutil
            shutil.copy2(source_file, dest_file)
            source_file = dest_file

        if not create_summary:
            self._log_entry(wiki_root, "ingest", f"Added raw source: {source_file.name}")
            return f"Source copied to raw/: {source_file.name}"

        # Create source summary page
        source_name = source_file.stem
        safe_name = self._sanitize_filename(source_name)
        source_page = wiki_dir / "sources" / f"{safe_name}.md"

        # Read source content
        try:
            content = source_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = f"[Binary file: {source_file.name}]"

        # Analyze with LLM
        today = datetime.now().strftime("%Y-%m-%d")
        analysis = await self._analyze_source_with_llm(content, source_name)

        frontmatter = {
            "title": source_name,
            "created": today,
            "updated": today,
            "category": "sources",
            "tags": analysis["tags"],
            "source_file": str(source_file.relative_to(wiki_root)),
        }

        # Build source page content
        claims_section = "\n".join(f"- {claim}" for claim in analysis["claims"]) if analysis["claims"] else "- (No key claims extracted)"
        entities_section = "\n".join(f"- [[{name}]]: {desc}" for name, desc in analysis["entities"].items()) if analysis["entities"] else "- (No entities extracted)"
        concepts_section = "\n".join(f"- [[{name}]]: {desc}" for name, desc in analysis["concepts"].items()) if analysis["concepts"] else "- (No concepts extracted)"

        page_content = f"""{self._write_frontmatter(frontmatter)}

# {source_name}

**Source:** `{source_file.name}`

## Summary

{analysis["summary"] or "(No summary generated)"}

## Key Claims

{claims_section}

## Key Entities

{entities_section}

## Key Concepts

{concepts_section}

## Raw Content

<details>
<summary>Click to expand full content</summary>

```
{content[:self.RAW_CONTENT_DISPLAY_LIMIT]}  # Limit to prevent huge pages
```

</details>

---

*Source ingested on {today}*
"""

        source_page.write_text(page_content, encoding="utf-8")

        # Generate entity pages
        entity_pages = []
        for entity_name, entity_desc in analysis["entities"].items():
            try:
                entity_page = await self._generate_entity_page(wiki_root, entity_name, entity_desc, source_name)
                if entity_page:
                    entity_pages.append(entity_name)
            except Exception as e:
                pass  # Continue even if entity generation fails

        # Generate concept pages
        concept_pages = []
        for concept_name, concept_desc in analysis["concepts"].items():
            try:
                concept_page = await self._generate_concept_page(wiki_root, concept_name, concept_desc, source_name)
                if concept_page:
                    concept_pages.append(concept_name)
            except Exception as e:
                pass  # Continue even if concept generation fails

        # Log the operation
        self._log_entry(wiki_root, "ingest", f"Processed source: {source_name}")

        # Update index
        await self._update_index(wiki_root)

        result_lines = [
            f"Source ingested: {source_name}",
            f"  - Raw file: {source_file}",
            f"  - Wiki page: {source_page}",
        ]

        if entity_pages:
            result_lines.append(f"  - Entities created/updated: {', '.join(entity_pages)}")
        if concept_pages:
            result_lines.append(f"  - Concepts created/updated: {', '.join(concept_pages)}")

        result_lines.extend([
            "",
            "LLM Analysis complete. The source has been:",
            "  1. Analyzed and summarized",
            "  2. Key entities extracted and linked",
            "  3. Key concepts extracted and linked",
            "  4. Indexed in the wiki",
        ])

        return "\n".join(result_lines)

    async def _update_index(self, wiki_root: Path) -> None:
        """Update the index.md with current wiki contents including metadata."""
        wiki_dir = wiki_root / "pages"
        index_path = self._get_index_path(wiki_root)

        # Collect all pages with metadata
        sources = []
        entities = []
        concepts = []
        syntheses = []

        for category, collector in [
            ("sources", sources),
            ("entities", entities),
            ("concepts", concepts),
            ("syntheses", syntheses),
        ]:
            cat_dir = wiki_dir / category
            if cat_dir.exists():
                for page_file in cat_dir.glob("*.md"):
                    try:
                        content = page_file.read_text(encoding="utf-8")
                        frontmatter, body = self._read_frontmatter(content)

                        # Extract metadata based on category
                        entry = {
                            "file": page_file.name,
                            "title": frontmatter.get("title", page_file.stem),
                            "created": frontmatter.get("created", "unknown"),
                            "updated": frontmatter.get("updated", "unknown"),
                            "tags": frontmatter.get("tags", []),
                            "sources": frontmatter.get("sources", []),
                            "summary": self._extract_page_summary(frontmatter, body),
                            "type": self._extract_page_type(frontmatter, category),
                            "definition": self._extract_definition(body),
                        }
                        collector.append(entry)
                    except Exception as e:
                        logger.warning(f"Failed to process {page_file}: {e}")

        # Rebuild index with proper metadata
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        index_lines = [
            "# Wiki Index",
            "",
            "Content catalog for the LLM Wiki.",
            "",
            "## Sources",
            "",
            "| Source | Summary | Date | Tags |",
            "|--------|---------|------|------|",
        ]

        for s in sources:
            tags = ", ".join(s["tags"]) if s["tags"] else "-"
            summary = s["summary"] if s["summary"] != "-" else "_"
            if len(summary) > 50:
                summary = summary[:47] + "..."
            index_lines.append(f"| [[{s['title']}]] | {summary} | {s['created']} | {tags} |")

        index_lines.extend([
            "",
            "## Entities",
            "",
            "| Entity | Type | Sources | Last Updated |",
            "|--------|------|---------|--------------|",
        ])

        for e in entities:
            type_val = e["type"] if e["type"] != "-" else "entity"
            sources_count = len(e["sources"]) if e["sources"] else 0
            sources_display = str(sources_count) if sources_count > 0 else "-"
            index_lines.append(f"| [[{e['title']}]] | {type_val} | {sources_display} | {e['updated']} |")

        index_lines.extend([
            "",
            "## Concepts",
            "",
            "| Concept | Definition | Sources | Last Updated |",
            "|---------|------------|---------|--------------|",
        ])

        for c in concepts:
            definition = c["definition"] if c["definition"] != "-" else "_"
            if len(definition) > 50:
                definition = definition[:47] + "..."
            sources_count = len(c["sources"]) if c["sources"] else 0
            sources_display = str(sources_count) if sources_count > 0 else "-"
            index_lines.append(f"| [[{c['title']}]] | {definition} | {sources_display} | {c['updated']} |")

        index_lines.extend([
            "",
            "## Syntheses",
            "",
            "| Synthesis | Description | Sources | Last Updated |",
            "|-----------|-------------|---------|--------------|",
        ])

        for syn in syntheses:
            summary = syn["summary"] if syn["summary"] != "-" else "_"
            if len(summary) > 50:
                summary = summary[:47] + "..."
            sources_count = len(syn["sources"]) if syn["sources"] else 0
            sources_display = str(sources_count) if sources_count > 0 else "-"
            index_lines.append(f"| [[{syn['title']}]] | {summary} | {sources_display} | {syn['updated']} |")

        index_lines.extend([
            "",
            "---",
            "",
            f"*This index is maintained automatically. Last updated: {today}*",
        ])

        index_path.write_text("\n".join(index_lines), encoding="utf-8")

    async def _update_backlinks(self, wiki_root: Path, page_title: str) -> None:
        """Update backlinks section for all pages that reference the given page.

        Scans all wiki pages and adds a 'Backlinks' section to pages that are
        referenced by the given page but don't already have backlink entries.
        """
        wiki_dir = wiki_root / "pages"
        if not wiki_dir.exists():
            return

        # Build link graph
        page_files = {}
        for category in ["entities", "concepts", "sources", "syntheses"]:
            cat_dir = wiki_dir / category
            if cat_dir.exists():
                for page_file in cat_dir.glob("*.md"):
                    try:
                        content = page_file.read_text(encoding="utf-8")
                        frontmatter, body = self._read_frontmatter(content)
                        title = frontmatter.get("title", page_file.stem)
                        page_files[title] = {
                            "file": page_file,
                            "content": content,
                            "frontmatter": frontmatter,
                            "body": body,
                        }
                    except Exception:
                        continue

        # Find all pages that mention the given page
        link_pattern = re.compile(r'\[\[([^\]]+)\]\]')
        backlinks_to_update = []

        for title, info in page_files.items():
            if title == page_title:
                continue

            links = link_pattern.findall(info["content"])
            if page_title in links:
                # Check if backlink already exists
                if "## Backlinks" not in info["body"]:
                    backlinks_to_update.append((title, info))

        # Update pages with new backlinks section
        today = datetime.now().strftime("%Y-%m-%d")

        for title, info in backlinks_to_update:
            frontmatter = info["frontmatter"]
            body = info["body"]

            # Add backlinks section
            backlinks_section = f"\n\n## Backlinks\n\nPages that link to this page:\n\n- [[{page_title}]]\n"

            frontmatter["updated"] = today
            updated_content = self._write_frontmatter(frontmatter) + "\n" + body + backlinks_section

            info["file"].write_text(updated_content, encoding="utf-8")
            logger.debug(f"Updated backlinks for {title}")

    async def _query_wiki(
        self,
        wiki_root: Path,
        query: str,
        category: str = "all",
        save_to_wiki: bool = False,
    ) -> str:
        """Query the wiki using LLM to synthesize an answer from relevant pages.

        Args:
            wiki_root: Root directory of the wiki
            query: Search query or question
            category: Category filter for query operations
            save_to_wiki: If True, save the synthesis to pages/syntheses/
        """
        self._require_llm()
        wiki_dir = wiki_root / "pages"

        if not wiki_dir.exists():
            return f"Error: Wiki not found at {wiki_root}. Run 'init' first."

        # Read index first
        index_path = self._get_index_path(wiki_root)
        index_content = ""
        if index_path.exists():
            index_content = index_path.read_text(encoding="utf-8")

        # Collect all page content for keyword pre-filtering
        candidates = []
        categories_to_search = (
            ["sources", "entities", "concepts", "syntheses"]
            if category == "all"
            else [category]
        )

        for cat in categories_to_search:
            cat_dir = wiki_dir / cat
            if not cat_dir.exists():
                continue

            for page_file in cat_dir.glob("*.md"):
                content = page_file.read_text(encoding="utf-8")
                frontmatter, body = self._read_frontmatter(content)

                score = 0
                query_lower = query.lower()
                title = frontmatter.get("title", page_file.stem).lower()

                if query_lower in title:
                    score += 10
                if query_lower in body.lower():
                    score += 5
                tags = frontmatter.get("tags") or []
                if query_lower in " ".join(tags).lower():
                    score += 8

                candidates.append({
                    "file": str(page_file.relative_to(wiki_root)),
                    "title": frontmatter.get("title", page_file.stem),
                    "category": cat,
                    "score": score,
                    "body": body[:self.QUERY_CONTENT_TRUNCATE],
                })

        # Sort by keyword relevance, take top pages for LLM context
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_pages = candidates[:self.MAX_QUERY_PAGES]

        if not top_pages:
            return (
                f"No pages found in the wiki. "
                f"Index overview:\n{index_content[:self.INDEX_PREVIEW_LENGTH]}"
            )

        # Build context from top pages for LLM synthesis
        page_context = []
        for p in top_pages:
            page_context.append(f"### {p['title']} ({p['category']})\nFile: {p['file']}\n\n{p['body']}")

        context_text = "\n\n---\n\n".join(page_context)

        system_prompt = (
            "You are a knowledge base assistant. Answer the user's question based on "
            "the wiki pages provided below. Synthesize information across multiple pages "
            "when relevant. Cite specific pages using [[Page Title]] notation. "
            "If the wiki doesn't contain enough information to fully answer, say so and "
            "suggest what additional sources might help.\n\n"
            "Respond in the same language as the user's query."
        )

        user_prompt = (
            f"Wiki Index:\n{index_content[:self.INDEX_CONTEXT_LENGTH]}\n\n"
            f"Relevant Pages:\n{context_text}\n\n"
            f"Question: {query}"
        )

        answer = await self._call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=self.MAX_ANALYSIS_TOKENS)

        # Log the query
        self._log_entry(wiki_root, "query", query[:self.QUERY_LOG_TRUNCATE_LENGTH])

        cited_pages = "\n".join(
            f"- [[{p['title']}]] (`{p['file']}`)" for p in top_pages if p["score"] > 0
        )

        # Save synthesis to wiki if requested
        synthesis_file = None
        if save_to_wiki:
            sources_referenced = [p["file"] for p in top_pages if p["score"] > 0]
            synthesis_file = await self._save_synthesis(
                wiki_root, query, answer, sources_referenced
            )
            self._log_entry(wiki_root, "synthesis", f"Created synthesis for query: {query[:self.QUERY_LOG_TRUNCATE_LENGTH]}")

        result = (
            f"# Query: {query}\n\n"
            f"{answer}\n\n"
            f"---\n\n"
            f"**Referenced pages:**\n{cited_pages or '(all pages scanned, no strong keyword matches)'}"
        )

        if synthesis_file:
            result += f"\n\n**Synthesis saved to:** `{synthesis_file}`"

        return result

    async def _save_synthesis(
        self,
        wiki_root: Path,
        query: str,
        answer: str,
        sources_referenced: list[str],
    ) -> Path:
        """Save query synthesis to wiki.

        Args:
            wiki_root: Root directory of the wiki
            query: Original query
            answer: LLM-generated answer/synthesis
            sources_referenced: List of source files referenced

        Returns:
            Path to the created synthesis file
        """
        syntheses_dir = wiki_root / "pages" / "syntheses"
        syntheses_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._sanitize_filename(query[:50])  # 限制长度
        synthesis_file = syntheses_dir / f"synthesis_{timestamp}_{safe_name}.md"

        frontmatter = {
            "title": f"Synthesis: {query[:80]}",
            "created": today,
            "updated": today,
            "category": "syntheses",
            "query": query,
            "sources": sources_referenced,
        }

        content = f"""{self._write_frontmatter(frontmatter)}

# {query}

{answer}

---

*Synthesis generated on {today}*
"""
        synthesis_file.write_text(content, encoding="utf-8")
        logger.info(f"Saved synthesis to {synthesis_file}")
        return synthesis_file

    async def _analyze_contradictions_with_llm(
        self,
        pages: dict[str, dict],
    ) -> list[str]:
        """Use LLM to detect contradictions between pages."""
        if len(pages) < 2:
            return []

        # Prepare page summaries for LLM
        page_summaries = []
        for title, info in list(pages.items())[:self.CONTRADICTION_ANALYSIS_LIMIT]:  # Limit to max pages for analysis
            frontmatter, body = self._read_frontmatter(info["content"])
            summary = body[:self.CONTRADICTION_SUMMARY_LENGTH]  # First N chars
            page_summaries.append(f"Page: {title}\n{summary}\n---")

        system_prompt = """You are a knowledge base auditor. Analyze the provided wiki pages for contradictions, inconsistencies, or gaps.

Look for:
1. Direct contradictions between pages
2. Inconsistent terminology or definitions
3. Missing cross-references that should exist
4. Redundant or duplicate information
5. Claims without supporting evidence

Respond with a list of issues found, one per line. If no issues found, respond with "No contradictions found."

Format:
- [Page A] vs [Page B]: [Description of contradiction]
- [Page]: [Description of issue]

Be concise and specific."""

        user_prompt = "Analyze these wiki pages for contradictions and issues:\n\n" + "\n\n".join(page_summaries)

        result = await self._call_llm(system_prompt, user_prompt, temperature=0.2, max_tokens=self.CONTRADICTION_MAX_TOKENS)

        if "No contradictions" in result or not result.strip():
            return []

        # Parse contradictions from result
        contradictions = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                contradictions.append(line.lstrip("-* ").strip())

        return contradictions

    async def _analyze_page_quality_with_llm(
        self,
        title: str,
        content: str,
    ) -> list[str]:
        """Use LLM to analyze page quality and suggest improvements."""

        system_prompt = """You are a knowledge base quality auditor. Analyze the wiki page and suggest improvements.

Check for:
1. Incomplete sections or placeholders
2. Missing citations or sources
3. Unclear or vague statements
4. Missing cross-references to related concepts
5. Poor structure or organization

Respond with specific, actionable suggestions. One suggestion per line.
If the page is of good quality, respond with "Page quality is good."

Format:
- [Section]: [Specific suggestion]

Be concise."""

        frontmatter, body = self._read_frontmatter(content)
        user_prompt = f"Page: {title}\n\nContent:\n{body[:self.QUALITY_ANALYSIS_LENGTH]}\n\nPlease analyze this page for quality issues."

        result = await self._call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=self.QUALITY_MAX_TOKENS)

        if "good quality" in result.lower() or not result.strip():
            return []

        suggestions = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                suggestions.append(line.lstrip("-* ").strip())

        return suggestions

    async def _lint_wiki(
        self,
        wiki_root: Path,
        check_type: str = "all",
    ) -> str:
        """Run health checks on the wiki with enhanced analysis."""
        wiki_dir = wiki_root / "pages"

        if not wiki_dir.exists():
            return f"Error: Wiki not found at {wiki_root}. Run 'init' first."

        issues = []
        llm_analysis_results = []

        # Build link graph and collect page info
        all_pages = {}
        inbound_links: dict[str, set[str]] = {}
        all_concepts: set[str] = set()
        all_entities: set[str] = set()

        for page_file in wiki_dir.rglob("*.md"):
            if page_file.name == "index.md":
                continue

            try:
                content = page_file.read_text(encoding="utf-8")
                frontmatter, body = self._read_frontmatter(content)
                title = frontmatter.get("title", page_file.stem)
                category = frontmatter.get("category", "unknown")

                all_pages[title] = {
                    "file": str(page_file.relative_to(wiki_root)),
                    "title": title,
                    "content": content,
                    "frontmatter": frontmatter,
                    "body": body,
                    "category": category,
                }
                inbound_links[title] = set()

                # Track entities and concepts
                if category == "entities":
                    all_entities.add(title)
                elif category == "concepts":
                    all_concepts.add(title)
            except Exception:
                continue

        # Find links
        link_pattern = re.compile(r'\[\[([^\]]+)\]\]')
        for title, info in all_pages.items():
            links = link_pattern.findall(info["content"])
            for link in links:
                if link in inbound_links:
                    inbound_links[link].add(title)

        # Run basic checks
        if check_type in ("orphans", "all"):
            orphans = [t for t, links in inbound_links.items() if not links and t != "index"]
            if orphans:
                issues.append(f"**Orphan pages** (no inbound links): {', '.join(orphans)}")

        if check_type in ("missing_links", "all"):
            missing = []
            for title, info in all_pages.items():
                links = link_pattern.findall(info["content"])
                for link in links:
                    if link not in all_pages and not (wiki_dir / f"{link}.md").exists():
                        missing.append(f"{title} -> {link}")
            if missing:
                issues.append(f"**Broken links**: {', '.join(missing[:10])}")

        if check_type in ("stale", "all"):
            stale = []
            for title, info in all_pages.items():
                updated = info["frontmatter"].get("updated", "")
                if updated:
                    try:
                        updated_date = datetime.strptime(updated, "%Y-%m-%d")
                        days_old = (datetime.now() - updated_date).days
                        if days_old > self.STALE_THRESHOLD_DAYS:
                            stale.append(f"{title} ({days_old} days)")
                    except ValueError:
                        pass
            if stale:
                issues.append(f"**Stale pages** (>{self.STALE_THRESHOLD_DAYS} days): {', '.join(stale[:10])}")

        # Check for missing important concepts
        if check_type in ("missing_concepts", "all"):
            missing_concepts = await self._detect_missing_concepts(all_pages, all_concepts)
            if missing_concepts:
                issues.append(f"**Important concepts missing pages**: {', '.join(missing_concepts[:10])}")

        # Check for data gaps
        if check_type in ("data_gaps", "all"):
            data_gaps = await self._detect_data_gaps(all_pages)
            if data_gaps:
                issues.append("**Data gaps** (pages lacking sources or detail):\n- " + "\n- ".join(data_gaps[:5]))

        # LLM-powered analysis
        if check_type in ("contradictions", "all") and len(all_pages) >= 2:
            try:
                contradictions = await self._analyze_contradictions_with_llm(all_pages)
                if contradictions:
                    issues.append("**Potential contradictions** (LLM analysis):\n- " + "\n- ".join(contradictions))
            except Exception:
                pass

        if check_type in ("quality", "all"):
            quality_issues = []
            for title, info in list(all_pages.items())[:5]:
                try:
                    suggestions = await self._analyze_page_quality_with_llm(title, info["content"])
                    if suggestions:
                        quality_issues.append(f"{title}:")
                        for s in suggestions[:3]:
                            quality_issues.append(f"  - {s}")
                except Exception:
                    continue

            if quality_issues:
                issues.append("**Quality suggestions** (LLM analysis):\n" + "\n".join(quality_issues))

        # Log the lint operation
        self._log_entry(wiki_root, "lint", f"Ran {check_type} check, found {len(issues)} issues")

        # Build result
        lines = ["# Wiki Lint Results\n"]
        lines.append("*LLM-powered analysis enabled*\n")

        if issues:
            lines.extend(issues)
        else:
            lines.append("✓ No issues found!")

        return "\n".join(lines)

    async def _detect_missing_concepts(
        self,
        all_pages: dict[str, dict],
        existing_concepts: set[str]
    ) -> list[str]:
        """Detect important concepts mentioned but without dedicated pages.

        Uses LLM to identify key concepts that should have pages.
        """
        if len(all_pages) < 2:
            return []

        # Sample a few pages for analysis
        sample_pages = []
        for title, info in list(all_pages.items())[:5]:
            frontmatter, body = self._read_frontmatter(info["content"])
            sample_pages.append(f"Page: {title}\n{body[:500]}\n---")

        system_prompt = """You are a knowledge base auditor. Analyze the provided wiki pages and identify important concepts that are mentioned but don't have dedicated pages.

Look for:
1. Technical terms mentioned multiple times
2. Domain-specific terminology
3. Named theories, methods, or frameworks
4. Important relationships or patterns

For each concept found, explain why it deserves its own page.

Format: Concept Name | Reason
Be specific and concise."""

        user_prompt = "Analyze these pages for missing concept pages:\n\n" + "\n\n".join(sample_pages)

        try:
            result = await self._call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=1024)

            missing = []
            for line in result.split("\n"):
                line = line.strip()
                if "|" in line:
                    concept = line.split("|")[0].strip()
                    # Check if concept doesn't already exist
                    if concept and concept not in existing_concepts:
                        missing.append(concept)

            return missing[:10]  # Limit to 10 suggestions
        except Exception:
            return []

    async def _detect_data_gaps(self, all_pages: dict[str, dict]) -> list[str]:
        """Detect pages with missing data or insufficient detail."""
        gaps = []

        for title, info in all_pages.items():
            frontmatter = info["frontmatter"]
            body = info["body"]

            # Check for missing sources
            sources = frontmatter.get("sources", [])
            if not sources:
                gaps.append(f"{title}: No source references")

            # Check for short content
            word_count = len(body.split())
            if word_count < 100:
                gaps.append(f"{title}: Very short content ({word_count} words)")

            # Check for missing tags
            tags = frontmatter.get("tags", [])
            if not tags:
                gaps.append(f"{title}: No tags assigned")

            # Check for missing cross-references
            link_pattern = re.compile(r'\[\[([^\]]+)\]\]')
            links = link_pattern.findall(info["content"])
            if len(links) < 2 and word_count > 200:
                gaps.append(f"{title}: Few cross-references ({len(links)} links)")

        return gaps

    async def _list_sources(self, wiki_root: Path, category: str = "all") -> str:
        """List all sources in the wiki."""
        raw_dir = wiki_root / "raw"
        wiki_dir = wiki_root / "pages"

        lines = ["# Wiki Sources\n"]

        # List raw files
        if raw_dir.exists():
            lines.append("## Raw Source Files\n")
            for f in sorted(raw_dir.iterdir()):
                if f.is_file():
                    lines.append(f"- {f.name}")
            lines.append("")

        # List processed sources
        sources_dir = wiki_dir / "sources"
        if sources_dir.exists():
            lines.append("## Processed Source Pages\n")
            for f in sorted(sources_dir.glob("*.md")):
                content = f.read_text(encoding="utf-8")
                frontmatter, _ = self._read_frontmatter(content)
                title = frontmatter.get("title", f.stem)
                created = frontmatter.get("created", "unknown")
                lines.append(f"- [[{title}]] (created: {created})")
            lines.append("")

        return "\n".join(lines)

    async def execute(
        self,
        operation: str,
        wiki_path: str | None = None,
        source_path: str | None = None,
        query: str | None = None,
        category: str = "all",
        create_summary: bool = True,
        check_type: str = "all",
        **kwargs: Any,
    ) -> str:
        """Execute the wiki tool. All operations except init/list_sources require LLM."""
        wiki_root = self._get_wiki_root(wiki_path)

        if operation == "init":
            return await self._init_wiki(wiki_root)

        if operation == "list_sources":
            return await self._list_sources(wiki_root, category)

        # All remaining operations require LLM
        try:
            self._require_llm()
        except RuntimeError as e:
            return f"Error: {e}"

        if operation == "ingest":
            if not source_path:
                return "Error: source_path is required for ingest operation"
            return await self._ingest_source(wiki_root, source_path, create_summary)

        if operation == "query":
            if not query:
                return "Error: query is required for query operation"
            return await self._query_wiki(wiki_root, query, category)

        if operation == "lint":
            return await self._lint_wiki(wiki_root, check_type)

        return f"Error: Unknown operation '{operation}'"
