"""Parse profile markdown files into indexable chunks.

Expected format (see scoring/profile/*.md):

    ## chunk: chunk_name

    Free-form chunk content, one or more paragraphs.

    Tags: tag one, tag two, tag three

    ---
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CHUNK_HEADER_RE = re.compile(r"^##\s*chunk:\s*(?P<name>\S+)\s*$", re.MULTILINE)
TAGS_LINE_RE = re.compile(r"^Tags:\s*(?P<tags>.+)$", re.MULTILINE)


@dataclass
class Chunk:
    id: str
    source_file: str
    text: str
    tags: list[str]


def parse_file(path: Path) -> list[Chunk]:
    """Split a single profile markdown file into its `## chunk:` sections."""
    content = path.read_text(encoding="utf-8")

    headers = list(CHUNK_HEADER_RE.finditer(content))
    chunks: list[Chunk] = []

    for i, match in enumerate(headers):
        name = match.group("name")
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        body = content[start:end]

        # Strip a trailing "---" section separator if present.
        body = re.sub(r"\n-{3,}\s*$", "", body).strip()

        tags_match = TAGS_LINE_RE.search(body)
        tags = [t.strip() for t in tags_match.group("tags").split(",")] if tags_match else []

        text = body[: tags_match.start()].strip() if tags_match else body

        chunks.append(
            Chunk(
                id=f"{path.stem}::{name}",
                source_file=path.name,
                text=text,
                tags=tags,
            )
        )

    return chunks


def parse_profile_dir(profile_dir: Path) -> list[Chunk]:
    """Parse every .md file in the profile directory into chunks."""
    chunks: list[Chunk] = []
    for md_file in sorted(profile_dir.glob("*.md")):
        chunks.extend(parse_file(md_file))
    return chunks
