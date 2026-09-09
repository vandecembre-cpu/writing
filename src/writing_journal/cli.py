from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from . import actions, ai, storage
from .idea import STATUSES, Idea


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
        entry = actions.add_digitized_entry(
            project, image_paths, title=args.title, tags=actions.parse_tags(args.tags), model=args.model
        )
    except (ai.MissingApiKeyError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"Saved entry {entry.id} -> {project.entry_path(entry.id)}")


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

    try:
        entry = actions.add_text_entry(project, text, title=args.title, tags=actions.parse_tags(args.tags))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(f"Saved entry {entry.id} -> {project.entry_path(entry.id)}")


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
    new_tags = actions.parse_tags(args.tags)
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

    print(
        f"Generating ideas from {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} "
        f"with {ai.DEFAULT_MODEL}...",
        file=sys.stderr,
    )
    try:
        result = actions.run_ideas_pipeline(
            project,
            entries,
            focus=args.focus,
            n=args.count,
            model=args.model,
            save_report=not args.no_save,
            save_buckets=not args.no_bucket,
        )
    except ai.MissingApiKeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(result.report)

    if result.report_path:
        print(f"\nSaved report to {result.report_path}", file=sys.stderr)

    if result.extraction_error:
        print(f"Couldn't sort ideas into buckets: {result.extraction_error}", file=sys.stderr)

    if result.saved_counts:
        summary = ", ".join(f"{b} ({n})" for b, n in sorted(result.saved_counts.items()))
        print(
            f"\nAdded {sum(result.saved_counts.values())} ideas to the bucket repository: {summary}",
            file=sys.stderr,
        )


def cmd_idea_add(args):
    project = _resolve_project(args)
    now = datetime.now()
    idea = Idea(
        id=project.allocate_idea_id(now),
        text=args.text.strip(),
        bucket=args.bucket.strip(),
        date=now.isoformat(timespec="seconds"),
        tags=actions.parse_tags(args.tags),
        source_entries=actions.parse_tags(args.source),
        status="open",
        origin="manual",
    )
    project.save_idea(idea)
    print(f"Saved idea {idea.id} -> [{idea.bucket}] {idea.text}")


def cmd_idea_list(args):
    project = _resolve_project(args)
    status = None if args.status == "all" else args.status
    ideas = project.list_ideas(bucket=args.bucket, tag=args.tag, status=status)
    if not ideas:
        print("No ideas match.")
        return
    ideas.sort(key=lambda i: i.bucket.casefold())  # stable: keeps newest-first within each bucket
    current_bucket = None
    for i in ideas:
        if i.bucket != current_bucket:
            current_bucket = i.bucket
            print(f"\n== {current_bucket} ==")
        tags = f" [{', '.join(i.tags)}]" if i.tags else ""
        flag = "" if i.status == "open" else f" ({i.status})"
        print(f"{i.id}  {i.text}{tags}{flag}")


def cmd_idea_show(args):
    project = _resolve_project(args)
    try:
        i = project.load_idea(args.id)
    except storage.IdeaNotFoundError:
        print(f"No idea '{args.id}' in project '{project.name}'.", file=sys.stderr)
        sys.exit(1)
    print(f"[{i.bucket}]  {i.status}  ({i.origin})")
    print(f"{i.date}  [{', '.join(i.tags) or 'no tags'}]")
    if i.source_entries:
        print(f"source entries: {', '.join(i.source_entries)}")
    print()
    print(i.text)


def cmd_idea_bucket(args):
    project = _resolve_project(args)
    try:
        i = project.load_idea(args.id)
    except storage.IdeaNotFoundError:
        print(f"No idea '{args.id}' in project '{project.name}'.", file=sys.stderr)
        sys.exit(1)
    i.bucket = args.bucket.strip()
    project.save_idea(i)
    print(f"{i.id} bucket: {i.bucket}")


def cmd_idea_status(args):
    project = _resolve_project(args)
    try:
        i = project.load_idea(args.id)
    except storage.IdeaNotFoundError:
        print(f"No idea '{args.id}' in project '{project.name}'.", file=sys.stderr)
        sys.exit(1)
    i.status = args.status
    project.save_idea(i)
    print(f"{i.id} status: {i.status}")


def cmd_buckets(args):
    project = _resolve_project(args)
    counts = project.list_buckets(status=None if args.all else "open")
    if not counts:
        print("No ideas yet. Run 'writing ideas' or 'writing idea-add' to start filling the repository.")
        return
    for bucket, count in sorted(counts.items(), key=lambda kv: kv[0].casefold()):
        print(f"{bucket}\t{count}")


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
    p_ideas.add_argument("--no-save", action="store_true", help="Don't save the report under ideas/reports/")
    p_ideas.add_argument(
        "--no-bucket", action="store_true", help="Don't extract individual ideas into the bucket repository"
    )
    add_project_arg(p_ideas)
    p_ideas.set_defaults(func=cmd_ideas)

    p_idea_add = sub.add_parser("idea-add", help="Add an idea to the bucketed idea repository by hand")
    p_idea_add.add_argument("text", help="The idea itself")
    p_idea_add.add_argument("--bucket", required=True, help="Category to file this idea under")
    p_idea_add.add_argument("--tags", help="Comma-separated tags")
    p_idea_add.add_argument("--source", help="Comma-separated entry id(s) this idea draws on")
    add_project_arg(p_idea_add)
    p_idea_add.set_defaults(func=cmd_idea_add)

    p_idea_list = sub.add_parser("idea-list", help="Browse the bucketed idea repository")
    p_idea_list.add_argument("--bucket")
    p_idea_list.add_argument("--tag")
    p_idea_list.add_argument("--status", choices=["open", "used", "archived", "all"], default="open")
    add_project_arg(p_idea_list)
    p_idea_list.set_defaults(func=cmd_idea_list)

    p_idea_show = sub.add_parser("idea-show", help="Show one idea, with its source entries")
    p_idea_show.add_argument("id")
    add_project_arg(p_idea_show)
    p_idea_show.set_defaults(func=cmd_idea_show)

    p_idea_bucket = sub.add_parser("idea-bucket", help="Recategorize an idea into a different bucket")
    p_idea_bucket.add_argument("id")
    p_idea_bucket.add_argument("bucket")
    add_project_arg(p_idea_bucket)
    p_idea_bucket.set_defaults(func=cmd_idea_bucket)

    p_idea_status = sub.add_parser("idea-status", help="Mark an idea open/used/archived")
    p_idea_status.add_argument("id")
    p_idea_status.add_argument("status", choices=list(STATUSES))
    add_project_arg(p_idea_status)
    p_idea_status.set_defaults(func=cmd_idea_status)

    p_buckets = sub.add_parser("buckets", help="List idea buckets and how many open ideas are in each")
    p_buckets.add_argument("--all", action="store_true", help="Include used/archived ideas in the counts")
    add_project_arg(p_buckets)
    p_buckets.set_defaults(func=cmd_buckets)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
