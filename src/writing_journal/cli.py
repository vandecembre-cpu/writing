from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from . import ai, storage
from .entry import Entry


def _resolve_project(args) -> storage.Project:
    root = storage.default_projects_root()
    name = args.project or os.environ.get("WRITING_PROJECT")
    if not name:
        available = storage.list_projects(root)
        if len(available) == 1:
            name = available[0]
        elif not available:
            print(
                f"No projects found under {root}. Create one with: writing init <name>",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(
                "Multiple projects exist; specify one with --project or set WRITING_PROJECT.\n"
                f"Available: {', '.join(available)}",
                file=sys.stderr,
            )
            sys.exit(1)
    try:
        return storage.open_project(root, name)
    except storage.ProjectNotFoundError:
        print(f"No such project '{name}' under {root}.", file=sys.stderr)
        sys.exit(1)


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def cmd_init(args):
    root = storage.default_projects_root()
    try:
        project = storage.init_project(root, args.name)
    except storage.ProjectExistsError:
        print(f"Project '{args.name}' already exists at {root / args.name}", file=sys.stderr)
        sys.exit(1)
    print(f"Created project '{args.name}' at {project.path}")


def cmd_projects(args):
    root = storage.default_projects_root()
    projects = storage.list_projects(root)
    if not projects:
        print(f"No projects yet under {root}. Create one with: writing init <name>")
        return
    for name in projects:
        project = storage.Project(root, name)
        count = len(list(project.entries_dir.glob("*.md"))) if project.entries_dir.is_dir() else 0
        print(f"{name}\t{count} entr{'y' if count == 1 else 'ies'}")


def cmd_add(args):
    project = _resolve_project(args)
    image_paths = [Path(p).expanduser().resolve() for p in args.images]
    for p in image_paths:
        if not p.exists():
            print(f"Image not found: {p}", file=sys.stderr)
            sys.exit(1)

    print(f"Transcribing {len(image_paths)} image(s) with {ai.DEFAULT_MODEL}...", file=sys.stderr)
    try:
        text = ai.transcribe_images(image_paths, model=args.model)
    except ai.MissingApiKeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not text:
        print("Transcription came back empty; nothing saved.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    entry_id = project.allocate_entry_id(now)

    project.sources_dir.mkdir(parents=True, exist_ok=True)
    saved_sources = []
    for i, src in enumerate(image_paths):
        dest_name = f"{entry_id}-{i}{src.suffix.lower()}"
        dest = project.sources_dir / dest_name
        shutil.copy2(src, dest)
        saved_sources.append(str(dest.relative_to(project.path)))

    title = args.title or text.strip().splitlines()[0][:80]
    entry = Entry(
        id=entry_id,
        title=title,
        date=now.isoformat(timespec="seconds"),
        text=text,
        tags=_parse_tags(args.tags),
        source_images=saved_sources,
        digitized_with=f"claude-vision ({args.model})",
    )
    path = project.save_entry(entry)
    print(f"Saved entry {entry_id} -> {path}")


def cmd_add_text(args):
    project = _resolve_project(args)

    if args.file:
        text = Path(args.file).expanduser().read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        editor = os.environ.get("EDITOR", "nano")
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tf:
            tmp_path = tf.name
        try:
            subprocess.run([editor, tmp_path], check=True)
            text = Path(tmp_path).read_text(encoding="utf-8")
        finally:
            os.unlink(tmp_path)

    text = text.strip()
    if not text:
        print("No text entered; nothing saved.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    entry_id = project.allocate_entry_id(now)
    title = args.title or text.splitlines()[0][:80]
    entry = Entry(
        id=entry_id,
        title=title,
        date=now.isoformat(timespec="seconds"),
        text=text,
        tags=_parse_tags(args.tags),
        digitized_with="typed",
    )
    path = project.save_entry(entry)
    print(f"Saved entry {entry_id} -> {path}")


def cmd_list(args):
    project = _resolve_project(args)
    entries = project.list_entries(tag=args.tag, since=args.since)
    if not entries:
        print("No entries match.")
        return
    for e in entries:
        tags = f" [{', '.join(e.tags)}]" if e.tags else ""
        print(f"{e.id}  {e.date}  {e.title}{tags}")


def cmd_show(args):
    project = _resolve_project(args)
    try:
        entry = project.load_entry(args.id)
    except storage.EntryNotFoundError:
        print(f"No entry '{args.id}' in project '{project.name}'.", file=sys.stderr)
        sys.exit(1)
    print(f"# {entry.title}")
    print(f"{entry.date}  [{', '.join(entry.tags) or 'no tags'}]")
    if entry.source_images:
        print(f"source: {', '.join(entry.source_images)}")
    print()
    print(entry.text)


def cmd_edit(args):
    project = _resolve_project(args)
    path = project.entry_path(args.id)
    if not path.exists():
        print(f"No entry '{args.id}' in project '{project.name}'.", file=sys.stderr)
        sys.exit(1)
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(path)], check=True)


def cmd_tag(args):
    project = _resolve_project(args)
    try:
        entry = project.load_entry(args.id)
    except storage.EntryNotFoundError:
        print(f"No entry '{args.id}' in project '{project.name}'.", file=sys.stderr)
        sys.exit(1)
    new_tags = _parse_tags(args.tags)
    if args.remove:
        entry.tags = [t for t in entry.tags if t not in new_tags]
    else:
        entry.tags = sorted(set(entry.tags) | set(new_tags))
    project.save_entry(entry)
    print(f"{entry.id} tags: {', '.join(entry.tags) or '(none)'}")


def cmd_search(args):
    project = _resolve_project(args)
    results = project.search(args.query, tag=args.tag)
    if not results:
        print("No matches.")
        return
    for entry, snippet in results:
        print(f"{entry.id}  {entry.title}")
        print(f"    {snippet}")


def cmd_ideas(args):
    project = _resolve_project(args)
    entries = project.list_entries(tag=args.tag, since=args.since)
    if args.limit:
        entries = entries[: args.limit]
    if not entries:
        print("No entries to generate ideas from.", file=sys.stderr)
        sys.exit(1)

    entries = list(reversed(entries))  # chronological order reads better for the model
    blocks = []
    for e in entries:
        tags = f" [{', '.join(e.tags)}]" if e.tags else ""
        blocks.append(f"### {e.date} — {e.title}{tags}\n\n{e.text}")
    entries_text = "\n\n---\n\n".join(blocks)

    print(
        f"Generating ideas from {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} "
        f"with {ai.DEFAULT_MODEL}...",
        file=sys.stderr,
    )
    try:
        report = ai.generate_ideas(entries_text, focus=args.focus, n=args.count, model=args.model)
    except ai.MissingApiKeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(report)

    if not args.no_save:
        project.ideas_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = project.ideas_dir / f"{stamp}.md"
        header = f"<!-- generated {datetime.now().isoformat(timespec='seconds')}"
        if args.focus:
            header += f", focus: {args.focus}"
        header += " -->\n\n"
        out_path.write_text(header + report + "\n", encoding="utf-8")
        print(f"\nSaved to {out_path}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="writing", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_project_arg(p):
        p.add_argument("--project", "-p", help="Project name (default: env WRITING_PROJECT, or the only project)")

    p_init = sub.add_parser("init", help="Create a new writing project")
    p_init.add_argument("name")
    p_init.set_defaults(func=cmd_init)

    p_projects = sub.add_parser("projects", help="List projects")
    p_projects.set_defaults(func=cmd_projects)

    p_add = sub.add_parser("add", help="Digitize photo(s) of handwriting into a new entry")
    p_add.add_argument("images", nargs="+", help="Path(s) to photo/scan image(s), one entry (multi-page ok)")
    p_add.add_argument("--title")
    p_add.add_argument("--tags", help="Comma-separated tags")
    p_add.add_argument("--model", default=ai.DEFAULT_MODEL)
    add_project_arg(p_add)
    p_add.set_defaults(func=cmd_add)

    p_add_text = sub.add_parser("add-text", help="Add a typed entry ($EDITOR, --file, or stdin)")
    p_add_text.add_argument("--title")
    p_add_text.add_argument("--tags", help="Comma-separated tags")
    p_add_text.add_argument("--file", help="Read entry text from this file instead of an editor")
    add_project_arg(p_add_text)
    p_add_text.set_defaults(func=cmd_add_text)

    p_list = sub.add_parser("list", help="List entries in a project")
    p_list.add_argument("--tag")
    p_list.add_argument("--since", help="ISO date, e.g. 2026-01-01")
    add_project_arg(p_list)
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Print one entry")
    p_show.add_argument("id")
    add_project_arg(p_show)
    p_show.set_defaults(func=cmd_show)

    p_edit = sub.add_parser("edit", help="Open an entry in $EDITOR (fix OCR mistakes, etc.)")
    p_edit.add_argument("id")
    add_project_arg(p_edit)
    p_edit.set_defaults(func=cmd_edit)

    p_tag = sub.add_parser("tag", help="Add or remove tags on an entry")
    p_tag.add_argument("id")
    p_tag.add_argument("tags", help="Comma-separated tags")
    p_tag.add_argument("--remove", action="store_true")
    add_project_arg(p_tag)
    p_tag.set_defaults(func=cmd_tag)

    p_search = sub.add_parser("search", help="Keyword search across entries")
    p_search.add_argument("query")
    p_search.add_argument("--tag")
    add_project_arg(p_search)
    p_search.set_defaults(func=cmd_search)

    p_ideas = sub.add_parser("ideas", help="Generate ideas from your writing with Claude")
    p_ideas.add_argument("--tag")
    p_ideas.add_argument("--since", help="ISO date, e.g. 2026-01-01")
    p_ideas.add_argument("--limit", type=int, help="Only use the N most recent matching entries")
    p_ideas.add_argument("--focus", help="Steer the ideas toward a topic/theme")
    p_ideas.add_argument("--count", type=int, default=8, help="How many ideas to generate (default 8)")
    p_ideas.add_argument("--model", default=ai.DEFAULT_MODEL)
    p_ideas.add_argument("--no-save", action="store_true", help="Don't save the report under ideas/")
    add_project_arg(p_ideas)
    p_ideas.set_defaults(func=cmd_ideas)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
