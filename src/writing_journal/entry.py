"""Entry data model and Markdown+front-matter (de)serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

FRONT_MATTER_DELIM = "---"


@dataclass
class Entry:
    id: str
    title: str
    date: str  # ISO 8601 timestamp
    text: str
    tags: list[str] = field(default_factory=list)
    source_images: list[str] = field(default_factory=list)
    digitized_with: str | None = None

    def filename(self) -> str:
        return f"{self.id}.md"

    def front_matter(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date,
            "tags": self.tags,
            "source_images": self.source_images,
            "digitized_with": self.digitized_with,
        }

    def to_markdown(self) -> str:
        fm = yaml.safe_dump(self.front_matter(), sort_keys=False, allow_unicode=True).strip()
        return f"{FRONT_MATTER_DELIM}\n{fm}\n{FRONT_MATTER_DELIM}\n\n{self.text.strip()}\n"


def parse_markdown(path: Path) -> Entry:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith(FRONT_MATTER_DELIM):
        raise ValueError(f"{path} is missing YAML front matter")
    _, fm_raw, body = raw.split(FRONT_MATTER_DELIM, 2)
    meta = yaml.safe_load(fm_raw) or {}
    return Entry(
        id=meta.get("id", path.stem),
        title=meta.get("title", path.stem),
        date=meta.get("date", ""),
        text=body.strip(),
        tags=meta.get("tags") or [],
        source_images=meta.get("source_images") or [],
        digitized_with=meta.get("digitized_with"),
    )


def new_entry_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("%Y%m%d-%H%M%S")
