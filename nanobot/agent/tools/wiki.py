"""LLM Wiki tool for building personal knowledge bases.

This module implements the LLM Wiki pattern from docs/llm-wiki.md:
- Three-layer architecture: Raw sources -> Wiki -> Schema
- Three core operations: ingest, query, lint
- Two special files: index.md (content catalog) and log.md (chronological log)
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider


class WikiTool(Tool):
    """Tool for managing LLM Wiki knowledge bases.

    The wiki is a persistent, compounding knowledge base where:
    - Raw sources are immutable source documents
    - Wiki pages are LLM-generated markdown files
    - Schema defines conventions and workflows
    """

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

        frontmatter: dict[str, Any] = {}
        for line in frontmatter_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip()

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
        """
        self._require_llm()
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
        return response.content or ""

    async def _analyze_source_with_llm(self, content: str, source_name: str) -> dict[str, Any]:
        """Use LLM to analyze source content and extract structured information.

        Returns:
            Dict with summary, claims, entities, concepts, tags
        """
        system_prompt = """You are a knowledge extraction assistant. Analyze the provided source document and extract structured information.

Respond in this exact format:

SUMMARY:
[2-3 paragraph comprehensive summary of the key points]

CLAIMS:
- [First key claim or finding]
- [Second key claim or finding]
- [Additional claims...]

ENTITIES:
- [Entity name]: [Brief description of what/who this is]
- [Another entity]: [Description]

CONCEPTS:
- [Concept name]: [Brief definition or explanation]
- [Another concept]: [Definition]

TAGS:
[comma, separated, list, of, relevant, tags]

Be thorough but concise. Extract all significant information."""

        # Truncate content if too long
        truncated_content = content[:30000] if len(content) > 30000 else content
        user_prompt = f"Source: {source_name}\n\nContent:\n{truncated_content}\n\nPlease analyze this source and extract the structured information."

        result = await self._call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=4096)

        # Parse the result
        parsed = {
            "summary": "",
            "claims": [],
            "entities": {},
            "concepts": {},
            "tags": [],
        }

        current_section = None
        for line in result.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("SUMMARY:"):
                current_section = "summary"
                continue
            elif line.startswith("CLAIMS:"):
                current_section = "claims"
                continue
            elif line.startswith("ENTITIES:"):
                current_section = "entities"
                continue
            elif line.startswith("CONCEPTS:"):
                current_section = "concepts"
                continue
            elif line.startswith("TAGS:"):
                current_section = "tags"
                continue

            if current_section == "summary":
                parsed["summary"] += line + "\n"
            elif current_section == "claims" and line.startswith("-"):
                parsed["claims"].append(line[1:].strip())
            elif current_section == "entities" and line.startswith("-"):
                if ":" in line:
                    name, desc = line[1:].split(":", 1)
                    parsed["entities"][name.strip()] = desc.strip()
            elif current_section == "concepts" and line.startswith("-"):
                if ":" in line:
                    name, desc = line[1:].split(":", 1)
                    parsed["concepts"][name.strip()] = desc.strip()
            elif current_section == "tags":
                tags = [t.strip() for t in line.replace(",", " ").split() if t.strip()]
                parsed["tags"].extend(tags)

        parsed["summary"] = parsed["summary"].strip()
        return parsed

    async def _generate_entity_page(
        self,
        wiki_root: Path,
        entity_name: str,
        entity_desc: str,
        source_name: str,
    ) -> Path | None:
        """Generate or update an entity page using LLM."""
        wiki_dir = wiki_root / "pages"
        entity_file = wiki_dir / "entities" / f"{self._sanitize_filename(entity_name)}.md"

        today = datetime.now().strftime("%Y-%m-%d")

        if entity_file.exists():
            # Update existing entity page
            existing_content = entity_file.read_text(encoding="utf-8")
            frontmatter, body = self._read_frontmatter(existing_content)

            # Add new source reference
            sources = frontmatter.get("sources", [])
            if source_name not in sources:
                sources.append(source_name)

            frontmatter["sources"] = sources
            frontmatter["updated"] = today

            # Add new information section
            new_section = f"\n\n## From: {source_name}\n\n{entity_desc}\n"
            updated_content = self._write_frontmatter(frontmatter) + "\n" + body + new_section
        else:
            # Create new entity page with LLM
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
        return entity_file

    async def _generate_concept_page(
        self,
        wiki_root: Path,
        concept_name: str,
        concept_desc: str,
        source_name: str,
    ) -> Path | None:
        """Generate or update a concept page using LLM."""
        wiki_dir = wiki_root / "pages"
        concept_file = wiki_dir / "concepts" / f"{self._sanitize_filename(concept_name)}.md"

        today = datetime.now().strftime("%Y-%m-%d")

        if concept_file.exists():
            # Update existing concept page
            existing_content = concept_file.read_text(encoding="utf-8")
            frontmatter, body = self._read_frontmatter(existing_content)

            sources = frontmatter.get("sources", [])
            if source_name not in sources:
                sources.append(source_name)

            frontmatter["sources"] = sources
            frontmatter["updated"] = today

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
{content[:50000]}  # Limit to prevent huge pages
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
        """Update the index.md with current wiki contents."""
        wiki_dir = wiki_root / "pages"
        index_path = self._get_index_path(wiki_root)

        # Collect all pages
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
                    content = page_file.read_text(encoding="utf-8")
                    frontmatter, body = self._read_frontmatter(content)
                    collector.append({
                        "file": page_file.name,
                        "title": frontmatter.get("title", page_file.stem),
                        "created": frontmatter.get("created", "unknown"),
                        "updated": frontmatter.get("updated", "unknown"),
                        "tags": frontmatter.get("tags", []),
                    })

        # Rebuild index
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
            index_lines.append(f"| [[{s['title']}]] | - | {s['created']} | {tags} |")

        index_lines.extend([
            "",
            "## Entities",
            "",
            "| Entity | Type | Sources | Last Updated |",
            "|--------|------|---------|--------------|",
        ])

        for e in entities:
            index_lines.append(f"| [[{e['title']}]] | - | - | {e['updated']} |")

        index_lines.extend([
            "",
            "## Concepts",
            "",
            "| Concept | Definition | Sources | Last Updated |",
            "|---------|------------|---------|--------------|",
        ])

        for c in concepts:
            index_lines.append(f"| [[{c['title']}]] | - | - | {c['updated']} |")

        index_lines.extend([
            "",
            "## Syntheses",
            "",
            "| Synthesis | Description | Sources | Last Updated |",
            "|-----------|-------------|---------|--------------|",
        ])

        for syn in syntheses:
            index_lines.append(f"| [[{syn['title']}]] | - | - | {syn['updated']} |")

        index_lines.extend([
            "",
            "---",
            "",
            f"*This index is maintained automatically. Last updated: {today}*",
        ])

        index_path.write_text("\n".join(index_lines), encoding="utf-8")

    async def _query_wiki(
        self,
        wiki_root: Path,
        query: str,
        category: str = "all",
    ) -> str:
        """Query the wiki using LLM to synthesize an answer from relevant pages."""
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
                if query_lower in " ".join(frontmatter.get("tags", [])).lower():
                    score += 8

                candidates.append({
                    "file": str(page_file.relative_to(wiki_root)),
                    "title": frontmatter.get("title", page_file.stem),
                    "category": cat,
                    "score": score,
                    "body": body[:3000],
                })

        # Sort by keyword relevance, take top pages for LLM context
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_pages = candidates[:15]

        if not top_pages:
            return (
                f"No pages found in the wiki. "
                f"Index overview:\n{index_content[:2000]}"
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
            f"Wiki Index:\n{index_content[:2000]}\n\n"
            f"Relevant Pages:\n{context_text}\n\n"
            f"Question: {query}"
        )

        answer = await self._call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=4096)

        # Log the query
        self._log_entry(wiki_root, "query", query[:80])

        cited_pages = "\n".join(
            f"- [[{p['title']}]] (`{p['file']}`)" for p in top_pages if p["score"] > 0
        )

        return (
            f"# Query: {query}\n\n"
            f"{answer}\n\n"
            f"---\n\n"
            f"**Referenced pages:**\n{cited_pages or '(all pages scanned, no strong keyword matches)'}"
        )

    async def _analyze_contradictions_with_llm(
        self,
        pages: dict[str, dict],
    ) -> list[str]:
        """Use LLM to detect contradictions between pages."""
        if len(pages) < 2:
            return []

        # Prepare page summaries for LLM
        page_summaries = []
        for title, info in list(pages.items())[:10]:  # Limit to 10 pages for analysis
            frontmatter, body = self._read_frontmatter(info["content"])
            summary = body[:1000]  # First 1000 chars
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

        result = await self._call_llm(system_prompt, user_prompt, temperature=0.2, max_tokens=2048)

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
        user_prompt = f"Page: {title}\n\nContent:\n{body[:5000]}\n\nPlease analyze this page for quality issues."

        result = await self._call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=1024)

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
        """Run health checks on the wiki."""
        wiki_dir = wiki_root / "pages"

        if not wiki_dir.exists():
            return f"Error: Wiki not found at {wiki_root}. Run 'init' first."

        issues = []
        llm_analysis_results = []

        # Build link graph
        all_pages = {}
        inbound_links: dict[str, set[str]] = {}

        for page_file in wiki_dir.rglob("*.md"):
            if page_file.name == "index.md":
                continue

            try:
                content = page_file.read_text(encoding="utf-8")
                frontmatter, body = self._read_frontmatter(content)
                title = frontmatter.get("title", page_file.stem)

                all_pages[title] = {
                    "file": str(page_file.relative_to(wiki_root)),
                    "title": title,
                    "content": content,
                    "frontmatter": frontmatter,
                }
                inbound_links[title] = set()
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
                        if days_old > 90:
                            stale.append(f"{title} ({days_old} days)")
                    except ValueError:
                        pass
            if stale:
                issues.append(f"**Stale pages** (>90 days): {', '.join(stale[:10])}")

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
