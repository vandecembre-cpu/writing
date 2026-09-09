"""Business logic shared by the CLI and the web UI.

Keeping entry/idea creation and the ideas pipeline here means `writing add`,
`writing ideas`, and their web equivalents can't drift apart.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import ai
from .entry import Entry
from .idea import Idea
from .storage import Project


def parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def add_digitized_entry(
    project: Project,
    image_paths: list[Path],
    *,
    title: str | None = None,
    tags: list[str] | None = None,
    model: str = ai.DEFAULT_MODEL,
) -> Entry:
    text = ai.transcribe_images(image_paths, model=model)
    if not text:
        raise ValueError("Transcription came back empty; nothing saved.")

    now = datetime.now()
    entry_id = project.allocate_entry_id(now)

    project.sources_dir.mkdir(parents=True, exist_ok=True)
    saved_sources = []
    for i, src in enumerate(image_paths):
        dest_name = f"{entry_id}-{i}{src.suffix.lower()}"
        dest = project.sources_dir / dest_name
        shutil.copy2(src, dest)
        saved_sources.append(str(dest.relative_to(project.path)))

    entry = Entry(
        id=entry_id,
        title=title or text.strip().splitlines()[0][:80],
        date=now.isoformat(timespec="seconds"),
        text=text,
        tags=tags or [],
        source_images=saved_sources,
        digitized_with=f"claude-vision ({model})",
    )
    project.save_entry(entry)
    return entry


def add_text_entry(
    project: Project,
    text: str,
    *,
    title: str | None = None,
    tags: list[str] | None = None,
) -> Entry:
    text = text.strip()
    if not text:
        raise ValueError("No text entered; nothing saved.")

    now = datetime.now()
    entry = Entry(
        id=project.allocate_entry_id(now),
        title=title or text.splitlines()[0][:80],
        date=now.isoformat(timespec="seconds"),
        text=text,
        tags=tags or [],
        digitized_with="typed",
    )
    project.save_entry(entry)
    return entry


@dataclass
class IdeasResult:
    report: str
    report_path: Path | None
    saved_counts: dict[str, int] = field(default_factory=dict)
    extraction_error: str | None = None


def run_ideas_pipeline(
    project: Project,
    entries: list[Entry],
    *,
    focus: str | None = None,
    n: int = 8,
    model: str = ai.DEFAULT_MODEL,
    save_report: bool = True,
    save_buckets: bool = True,
) -> IdeasResult:
    if not entries:
        raise ValueError("No entries to generate ideas from.")

    ordered = list(reversed(entries))  # chronological order reads better for the model
    blocks = []
    for e in ordered:
        tags = f" [{', '.join(e.tags)}]" if e.tags else ""
        blocks.append(f"### {e.id} — {e.date} — {e.title}{tags}\n\n{e.text}")
    entries_text = "\n\n---\n\n".join(blocks)

    report = ai.generate_ideas(entries_text, focus=focus, n=n, model=model)

    report_path = None
    if save_report:
        project.ideas_reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = project.ideas_reports_dir / f"{stamp}.md"
        header = f"<!-- generated {datetime.now().isoformat(timespec='seconds')}"
        if focus:
            header += f", focus: {focus}"
        header += " -->\n\n"
        report_path.write_text(header + report + "\n", encoding="utf-8")

    saved_counts: dict[str, int] = {}
    extraction_error = None
    if save_buckets:
        existing_buckets = sorted(project.list_buckets(status=None))
        try:
            items = ai.extract_ideas(entries_text, existing_buckets=existing_buckets, focus=focus, n=n, model=model)
        except ai.IdeaExtractionError as e:
            extraction_error = str(e)
            items = []

        now = datetime.now()
        for item in items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            bucket = str(item.get("bucket") or "").strip() or "uncategorized"
            idea = Idea(
                id=project.allocate_idea_id(now),
                text=text,
                bucket=bucket,
                date=now.isoformat(timespec="seconds"),
                tags=[str(t).strip() for t in item.get("tags") or [] if str(t).strip()],
                source_entries=[str(s).strip() for s in item.get("source_entries") or [] if str(s).strip()],
                status="open",
                origin="ai",
            )
            project.save_idea(idea)
            saved_counts[bucket] = saved_counts.get(bucket, 0) + 1

    return IdeasResult(
        report=report,
        report_path=report_path,
        saved_counts=saved_counts,
        extraction_error=extraction_error,
    )
