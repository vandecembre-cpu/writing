"""Project layout and entry storage on disk.

A "project" is a directory:

    projects/<name>/
        project.yaml        # project metadata
        entries/*.md         # one digitized/typed piece of writing per file
        sources/*.jpg        # original photos/scans, kept alongside the transcript
        ideas/*.md            # saved output of `writing ideas`
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import yaml

from .entry import Entry, new_entry_id, parse_markdown
from .idea import Idea, new_idea_id
from .idea import parse_markdown as parse_idea_markdown


def default_projects_root() -> Path:
    env = os.environ.get("WRITING_PROJECTS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd() / "projects"


class ProjectNotFoundError(Exception):
    pass


class ProjectExistsError(Exception):
    pass


class EntryNotFoundError(Exception):
    pass


class IdeaNotFoundError(Exception):
    pass


class Project:
    def __init__(self, root: Path, name: str):
        self.root = root
        self.name = name
        self.path = root / name

    @property
    def entries_dir(self) -> Path:
        return self.path / "entries"

    @property
    def sources_dir(self) -> Path:
        return self.path / "sources"

    @property
    def ideas_dir(self) -> Path:
        return self.path / "ideas"

    @property
    def ideas_reports_dir(self) -> Path:
        """Freeform synthesis reports from `writing ideas` (themes, connections)."""
        return self.ideas_dir / "reports"

    @property
    def ideas_items_dir(self) -> Path:
        """The bucketed idea repository: one file per idea, filed under a category."""
        return self.ideas_dir / "items"

    @property
    def meta_path(self) -> Path:
        return self.path / "project.yaml"

    def exists(self) -> bool:
        return self.path.is_dir()

    def load_meta(self) -> dict:
        if not self.meta_path.exists():
            return {}
        return yaml.safe_load(self.meta_path.read_text(encoding="utf-8")) or {}

    def save_meta(self, meta: dict) -> None:
        self.meta_path.write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")

    def list_entries(self, tag: str | None = None, since: str | None = None) -> list[Entry]:
        entries = []
        if not self.entries_dir.is_dir():
            return entries
        for path in sorted(self.entries_dir.glob("*.md")):
            entry = parse_markdown(path)
            if tag and tag not in entry.tags:
                continue
            if since and entry.date < since:
                continue
            entries.append(entry)
        entries.sort(key=lambda e: e.date, reverse=True)
        return entries

    def load_entry(self, entry_id: str) -> Entry:
        path = self.entries_dir / f"{entry_id}.md"
        if not path.exists():
            raise EntryNotFoundError(entry_id)
        return parse_markdown(path)

    def entry_path(self, entry_id: str) -> Path:
        return self.entries_dir / f"{entry_id}.md"

    def save_entry(self, entry: Entry) -> Path:
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        path = self.entry_path(entry.id)
        path.write_text(entry.to_markdown(), encoding="utf-8")
        return path

    def allocate_entry_id(self, now: datetime | None = None) -> str:
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        base = new_entry_id(now)
        candidate = base
        suffix = 1
        while (self.entries_dir / f"{candidate}.md").exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def idea_path(self, idea_id: str) -> Path:
        return self.ideas_items_dir / f"{idea_id}.md"

    def save_idea(self, idea: Idea) -> Path:
        self.ideas_items_dir.mkdir(parents=True, exist_ok=True)
        path = self.idea_path(idea.id)
        path.write_text(idea.to_markdown(), encoding="utf-8")
        return path

    def load_idea(self, idea_id: str) -> Idea:
        path = self.idea_path(idea_id)
        if not path.exists():
            raise IdeaNotFoundError(idea_id)
        return parse_idea_markdown(path)

    def allocate_idea_id(self, now: datetime | None = None) -> str:
        self.ideas_items_dir.mkdir(parents=True, exist_ok=True)
        base = new_idea_id(now)
        candidate = base
        suffix = 1
        while (self.ideas_items_dir / f"{candidate}.md").exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def list_ideas(
        self,
        bucket: str | None = None,
        tag: str | None = None,
        status: str | None = None,
    ) -> list[Idea]:
        ideas = []
        if not self.ideas_items_dir.is_dir():
            return ideas
        for path in sorted(self.ideas_items_dir.glob("*.md")):
            idea = parse_idea_markdown(path)
            if bucket and idea.bucket.strip().casefold() != bucket.strip().casefold():
                continue
            if tag and tag not in idea.tags:
                continue
            if status and idea.status != status:
                continue
            ideas.append(idea)
        ideas.sort(key=lambda i: i.date, reverse=True)
        return ideas

    def list_buckets(self, status: str | None = "open") -> dict[str, int]:
        """Bucket name -> idea count, i.e. an index into the idea repository."""
        counts: dict[str, int] = {}
        for idea in self.list_ideas(status=status):
            counts[idea.bucket] = counts.get(idea.bucket, 0) + 1
        return counts

    def search(self, query: str, tag: str | None = None) -> list[tuple[Entry, str]]:
        query_lower = query.lower()
        results = []
        for entry in self.list_entries(tag=tag):
            haystack = f"{entry.title}\n{entry.text}"
            if query_lower in haystack.lower():
                results.append((entry, _snippet(entry.text, query_lower)))
        return results


def _snippet(text: str, query_lower: str, context: int = 40) -> str:
    idx = text.lower().find(query_lower)
    if idx == -1:
        return text[: context * 2].strip()
    start = max(0, idx - context)
    end = min(len(text), idx + len(query_lower) + context)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def list_projects(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "project.yaml").exists())


def init_project(root: Path, name: str) -> Project:
    project = Project(root, name)
    if project.exists():
        raise ProjectExistsError(name)
    project.entries_dir.mkdir(parents=True)
    project.sources_dir.mkdir(parents=True)
    project.ideas_reports_dir.mkdir(parents=True)
    project.ideas_items_dir.mkdir(parents=True)
    project.save_meta({"name": name, "created": datetime.now().isoformat(timespec="seconds")})
    return project


def open_project(root: Path, name: str) -> Project:
    project = Project(root, name)
    if not project.exists():
        raise ProjectNotFoundError(name)
    return project
