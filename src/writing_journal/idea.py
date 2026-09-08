"""Idea data model and Markdown+front-matter (de)serialization.

An Idea is a single, bucketed nugget pulled from the writer's own entries
(or jotted down directly) and kept around to revisit for future pieces —
the building block of the idea repository under ``projects/<name>/ideas/items/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

FRONT_MATTER_DELIM = "---"

DEFAULT_STATUS = "open"
STATUSES = ("open", "used", "archived")


@dataclass
class Idea:
    id: str
    text: str
    bucket: str
    date: str  # ISO 8601 timestamp, when the idea was captured
    tags: list[str] = field(default_factory=list)
    source_entries: list[str] = field(default_factory=list)
    status: str = DEFAULT_STATUS
    origin: str = "ai"  # "ai" (extracted from writing) or "manual"

    def filename(self) -> str:
        return f"{self.id}.md"

    def front_matter(self) -> dict:
        return {
            "id": self.id,
            "bucket": self.bucket,
            "date": self.date,
            "tags": self.tags,
            "source_entries": self.source_entries,
            "status": self.status,
            "origin": self.origin,
        }

    def to_markdown(self) -> str:
        fm = yaml.safe_dump(self.front_matter(), sort_keys=False, allow_unicode=True).strip()
        return f"{FRONT_MATTER_DELIM}\n{fm}\n{FRONT_MATTER_DELIM}\n\n{self.text.strip()}\n"


def parse_markdown(path: Path) -> Idea:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith(FRONT_MATTER_DELIM):
        raise ValueError(f"{path} is missing YAML front matter")
    _, fm_raw, body = raw.split(FRONT_MATTER_DELIM, 2)
    meta = yaml.safe_load(fm_raw) or {}
    return Idea(
        id=meta.get("id", path.stem),
        text=body.strip(),
        bucket=meta.get("bucket") or "uncategorized",
        date=meta.get("date", ""),
        tags=meta.get("tags") or [],
        source_entries=meta.get("source_entries") or [],
        status=meta.get("status") or DEFAULT_STATUS,
        origin=meta.get("origin") or "ai",
    )


def new_idea_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"idea-{now.strftime('%Y%m%d-%H%M%S')}"
