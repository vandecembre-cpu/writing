"""A minimal local web UI: digitize handwriting, browse entries, and manage
the bucketed idea repository from a browser instead of the CLI.

Run with `writing-ui`. Binds to localhost only — this is a personal tool for
one writer on one machine, not a multi-user service.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, send_from_directory, url_for

from . import actions, ai, storage
from .idea import STATUSES, Idea

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB, generous for a few page photos

BASE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 860px; margin: 2rem auto;
         padding: 0 1rem; line-height: 1.5; }
  h1 { font-size: 1.4rem; }
  h1 a { text-decoration: none; color: inherit; }
  h2 { font-size: 1.1rem; margin-top: 2.5rem; border-bottom: 1px solid #8884; padding-bottom: 0.3rem; }
  h3 { font-size: 1rem; margin-bottom: 0.3rem; }
  nav { margin-bottom: 1.5rem; opacity: 0.75; font-size: 0.9rem; }
  .msg { padding: 0.6rem 1rem; border-radius: 6px; margin-bottom: 1rem; }
  .msg.ok { background: #2e7d3222; }
  .msg.error { background: #c6282822; }
  .card { border: 1px solid #8884; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
  .row { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
  .meta { opacity: 0.65; font-size: 0.85rem; }
  .tag { display: inline-block; background: #8884; border-radius: 10px; padding: 0.05rem 0.6rem;
         font-size: 0.8rem; margin-right: 0.2rem; }
  textarea { width: 100%; min-height: 8rem; font-family: inherit; font-size: 1rem; box-sizing: border-box; }
  input[type=text], input[type=search] { font-size: 1rem; padding: 0.3rem; }
  form.inline { display: inline; }
  button, input[type=submit] { cursor: pointer; padding: 0.35rem 0.8rem; }
  ul.plain { list-style: none; padding: 0; }
  ul.plain li { margin-bottom: 0.4rem; }
  .idea-bucket { margin-top: 1.2rem; }
  .idea-bucket h3 { opacity: 0.8; }
  .used { opacity: 0.55; text-decoration: line-through; }
  .archived { opacity: 0.4; }
  details summary { cursor: pointer; }
  .api-warning { color: #b45309; font-size: 0.85rem; }
</style>
</head>
<body>
{{ body|safe }}
</body>
</html>
"""

INDEX = """
<h1>Writing</h1>
{% if not api_key_set %}
<p class="api-warning">ANTHROPIC_API_KEY is not set — digitizing photos and generating ideas won't work
until it is exported in the environment this server runs in.</p>
{% endif %}
{% if msg %}<div class="msg {{ 'error' if error else 'ok' }}">{{ msg }}</div>{% endif %}

<div class="card">
  <form method="post" action="{{ url_for('create_project') }}" class="row">
    <input type="text" name="name" placeholder="new project name" required>
    <button type="submit">Create project</button>
  </form>
</div>

<ul class="plain">
{% for p in projects %}
  <li><a href="{{ url_for('project_page', name=p.name) }}"><strong>{{ p.name }}</strong></a>
    <span class="meta">— {{ p.entries }} entr{{ 'y' if p.entries == 1 else 'ies' }},
    {{ p.ideas }} open idea{{ '' if p.ideas == 1 else 's' }}</span></li>
{% else %}
  <li class="meta">No projects yet. Create one above.</li>
{% endfor %}
</ul>
"""

PROJECT = """
<nav><a href="{{ url_for('index') }}">&larr; all projects</a></nav>
<h1>{{ project.name }}</h1>
{% if msg %}<div class="msg {{ 'error' if error else 'ok' }}">{{ msg }}</div>{% endif %}

<h2>Add writing</h2>
<div class="card">
  <h3>Digitize a photo</h3>
  <form method="post" enctype="multipart/form-data"
        action="{{ url_for('digitize_entry', name=project.name) }}">
    <input type="file" name="images" accept="image/*" multiple required><br><br>
    <input type="text" name="title" placeholder="title (optional, first line used otherwise)"><br><br>
    <input type="text" name="tags" placeholder="tags, comma-separated"><br><br>
    <button type="submit">Transcribe &amp; save</button>
  </form>
</div>
<div class="card">
  <h3>Type an entry</h3>
  <form method="post" action="{{ url_for('add_text_entry', name=project.name) }}">
    <textarea name="text" placeholder="Write here..." required></textarea><br><br>
    <input type="text" name="title" placeholder="title (optional)"><br><br>
    <input type="text" name="tags" placeholder="tags, comma-separated"><br><br>
    <button type="submit">Save entry</button>
  </form>
</div>

<h2>Entries ({{ entries|length }})</h2>
<form method="get" class="row">
  <input type="text" name="tag" placeholder="filter by tag" value="{{ tag_filter or '' }}">
  <button type="submit">Filter</button>
  {% if tag_filter %}<a href="{{ url_for('project_page', name=project.name) }}">clear</a>{% endif %}
</form>
<ul class="plain">
{% for e in entries %}
  <li><a href="{{ url_for('entry_page', name=project.name, entry_id=e.id) }}">{{ e.title }}</a>
    <span class="meta">{{ e.date }}{% if e.tags %} — {% for t in e.tags %}<span class="tag">{{ t }}</span>{% endfor %}{% endif %}</span></li>
{% else %}
  <li class="meta">No entries yet.</li>
{% endfor %}
</ul>

<h2>Ideas</h2>
<div class="card">
  <form method="post" action="{{ url_for('generate_ideas_route', name=project.name) }}">
    <div class="row">
      <input type="text" name="focus" placeholder="focus this batch on... (optional)">
      <input type="text" name="count" value="8" size="3" title="how many ideas">
      <button type="submit">Generate ideas from your writing</button>
    </div>
  </form>
</div>

<div class="row">
  <form method="get" class="row">
    <input type="text" name="bucket" placeholder="filter by bucket" value="{{ bucket_filter or '' }}"
           list="bucket-options">
    <datalist id="bucket-options">
      {% for b in buckets %}<option value="{{ b }}">{% endfor %}
    </datalist>
    <select name="status">
      {% for s in ['open', 'used', 'archived', 'all'] %}
        <option value="{{ s }}" {{ 'selected' if s == status_filter else '' }}>{{ s }}</option>
      {% endfor %}
    </select>
    <button type="submit">Filter</button>
  </form>
</div>

<details class="card">
  <summary>Add an idea by hand</summary>
  <form method="post" action="{{ url_for('add_idea', name=project.name) }}">
    <textarea name="text" placeholder="The idea itself..." required style="min-height:3rem"></textarea><br><br>
    <input type="text" name="bucket" placeholder="bucket" required list="bucket-options"><br><br>
    <input type="text" name="tags" placeholder="tags, comma-separated"><br><br>
    <button type="submit">Save idea</button>
  </form>
</details>

{% for bucket, items in ideas_by_bucket %}
<div class="idea-bucket">
  <h3>{{ bucket }} ({{ items|length }})</h3>
  <ul class="plain">
  {% for i in items %}
    <li class="{{ i.status }}">
      {{ i.text }}
      {% for t in i.tags %}<span class="tag">{{ t }}</span>{% endfor %}
      <div class="row meta">
        <form method="post" class="inline" action="{{ url_for('idea_bucket_route', name=project.name, idea_id=i.id) }}">
          <input type="text" name="bucket" value="{{ i.bucket }}" size="14" list="bucket-options">
          <button type="submit">move</button>
        </form>
        <form method="post" class="inline" action="{{ url_for('idea_status_route', name=project.name, idea_id=i.id) }}">
          <select name="status" onchange="this.form.submit()">
            {% for s in statuses %}<option value="{{ s }}" {{ 'selected' if s == i.status else '' }}>{{ s }}</option>{% endfor %}
          </select>
        </form>
        {% if i.source_entries %}<span>from: {{ i.source_entries|join(', ') }}</span>{% endif %}
      </div>
    </li>
  {% endfor %}
  </ul>
</div>
{% else %}
<p class="meta">No ideas match. Generate some above, or add one by hand.</p>
{% endfor %}

{% if reports %}
<h2>Saved reports</h2>
<ul class="plain">
{% for r in reports %}
  <li><a href="{{ url_for('report_page', name=project.name, filename=r) }}">{{ r }}</a></li>
{% endfor %}
</ul>
{% endif %}
"""

ENTRY = """
<nav><a href="{{ url_for('project_page', name=project.name) }}">&larr; {{ project.name }}</a></nav>
<h1>{{ entry.title }}</h1>
{% if msg %}<div class="msg {{ 'error' if error else 'ok' }}">{{ msg }}</div>{% endif %}
<p class="meta">{{ entry.date }} — {{ entry.digitized_with }}</p>

{% if entry.source_images %}
<div class="row">
  {% for src in entry.source_images %}
    <a href="{{ url_for('source_image', name=project.name, filename=src.split('/', 1)[1]) }}">
      <img src="{{ url_for('source_image', name=project.name, filename=src.split('/', 1)[1]) }}"
           alt="source page" style="max-height: 180px; border: 1px solid #8884; border-radius: 4px;">
    </a>
  {% endfor %}
</div>
{% endif %}

<form method="post" action="{{ url_for('update_entry', name=project.name, entry_id=entry.id) }}">
  <input type="text" name="title" value="{{ entry.title }}" style="width:100%"><br><br>
  <textarea name="text" style="min-height: 16rem">{{ entry.text }}</textarea><br><br>
  <input type="text" name="tags" value="{{ entry.tags|join(', ') }}" placeholder="tags, comma-separated"
         style="width:100%"><br><br>
  <button type="submit">Save changes</button>
</form>
"""

REPORT = """
<nav><a href="{{ url_for('project_page', name=project.name) }}">&larr; {{ project.name }}</a></nav>
<h1>{{ filename }}</h1>
<pre style="white-space: pre-wrap;">{{ text }}</pre>
"""


def render(template: str, **ctx) -> str:
    return render_template_string(template, **ctx)


def _project_or_404(name: str) -> storage.Project:
    try:
        return storage.open_project(storage.default_projects_root(), name)
    except storage.ProjectNotFoundError:
        abort(404, f"No such project '{name}'")


def _back_to_project(name: str, msg: str, error: bool = False):
    return redirect(url_for("project_page", name=name, msg=msg, error="1" if error else None))


@app.route("/")
def index():
    root = storage.default_projects_root()
    rows = []
    for name in storage.list_projects(root):
        project = storage.Project(root, name)
        rows.append(
            {
                "name": name,
                "entries": len(project.list_entries()),
                "ideas": sum(project.list_buckets().values()),
            }
        )
    body = render(
        INDEX,
        projects=rows,
        api_key_set=bool(os.environ.get("ANTHROPIC_API_KEY")),
        msg=request.args.get("msg"),
        error=request.args.get("error"),
    )
    return render(BASE, title="Writing", body=body)


@app.route("/projects", methods=["POST"])
def create_project():
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("index", msg="Project name can't be empty.", error="1"))
    try:
        storage.init_project(storage.default_projects_root(), name)
    except storage.ProjectExistsError:
        return redirect(url_for("index", msg=f"Project '{name}' already exists.", error="1"))
    return redirect(url_for("project_page", name=name))


@app.route("/p/<name>")
def project_page(name: str):
    project = _project_or_404(name)
    tag_filter = request.args.get("tag") or None
    bucket_filter = request.args.get("bucket") or None
    status_filter = request.args.get("status", "open")

    entries = project.list_entries(tag=tag_filter)
    status = None if status_filter == "all" else status_filter
    ideas = project.list_ideas(bucket=bucket_filter, status=status)
    ideas.sort(key=lambda i: i.bucket.casefold())

    ideas_by_bucket: list[tuple[str, list]] = []
    for i in ideas:
        if ideas_by_bucket and ideas_by_bucket[-1][0] == i.bucket:
            ideas_by_bucket[-1][1].append(i)
        else:
            ideas_by_bucket.append((i.bucket, [i]))

    reports = sorted((p.name for p in project.ideas_reports_dir.glob("*.md")), reverse=True) if project.ideas_reports_dir.is_dir() else []

    body = render(
        PROJECT,
        project=project,
        entries=entries,
        tag_filter=tag_filter,
        bucket_filter=bucket_filter,
        status_filter=status_filter,
        buckets=sorted(project.list_buckets(status=None)),
        ideas_by_bucket=ideas_by_bucket,
        statuses=STATUSES,
        reports=reports,
        msg=request.args.get("msg"),
        error=request.args.get("error"),
    )
    return render(BASE, title=f"Writing — {project.name}", body=body)


@app.route("/p/<name>/entries/text", methods=["POST"])
def add_text_entry(name: str):
    project = _project_or_404(name)
    try:
        entry = actions.add_text_entry(
            project,
            request.form.get("text", ""),
            title=request.form.get("title") or None,
            tags=actions.parse_tags(request.form.get("tags")),
        )
    except ValueError as e:
        return _back_to_project(name, str(e), error=True)
    return _back_to_project(name, f"Saved entry '{entry.title}'.")


@app.route("/p/<name>/entries/digitize", methods=["POST"])
def digitize_entry(name: str):
    project = _project_or_404(name)
    files = [f for f in request.files.getlist("images") if f.filename]
    if not files:
        return _back_to_project(name, "Choose at least one photo.", error=True)

    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for f in files:
            dest = Path(tmp) / Path(f.filename).name
            f.save(dest)
            paths.append(dest)
        try:
            entry = actions.add_digitized_entry(
                project,
                paths,
                title=request.form.get("title") or None,
                tags=actions.parse_tags(request.form.get("tags")),
            )
        except ai.MissingApiKeyError as e:
            return _back_to_project(name, str(e), error=True)
        except ValueError as e:
            return _back_to_project(name, str(e), error=True)

    return _back_to_project(name, f"Transcribed and saved entry '{entry.title}'.")


@app.route("/p/<name>/entries/<entry_id>")
def entry_page(name: str, entry_id: str):
    project = _project_or_404(name)
    try:
        entry = project.load_entry(entry_id)
    except storage.EntryNotFoundError:
        abort(404)
    body = render(
        ENTRY,
        project=project,
        entry=entry,
        msg=request.args.get("msg"),
        error=request.args.get("error"),
    )
    return render(BASE, title=entry.title, body=body)


@app.route("/p/<name>/entries/<entry_id>", methods=["POST"])
def update_entry(name: str, entry_id: str):
    project = _project_or_404(name)
    try:
        entry = project.load_entry(entry_id)
    except storage.EntryNotFoundError:
        abort(404)
    entry.title = request.form.get("title", entry.title).strip() or entry.title
    entry.text = request.form.get("text", entry.text)
    entry.tags = actions.parse_tags(request.form.get("tags"))
    project.save_entry(entry)
    return redirect(url_for("entry_page", name=name, entry_id=entry_id, msg="Saved."))


@app.route("/p/<name>/sources/<path:filename>")
def source_image(name: str, filename: str):
    project = _project_or_404(name)
    return send_from_directory(project.sources_dir, filename)


@app.route("/p/<name>/ideas/generate", methods=["POST"])
def generate_ideas_route(name: str):
    project = _project_or_404(name)
    entries = project.list_entries()
    try:
        count = max(1, int(request.form.get("count", 8)))
    except ValueError:
        count = 8
    try:
        result = actions.run_ideas_pipeline(
            project, entries, focus=request.form.get("focus") or None, n=count
        )
    except (ai.MissingApiKeyError, ValueError) as e:
        return _back_to_project(name, str(e), error=True)

    if result.saved_counts:
        summary = ", ".join(f"{b} ({n})" for b, n in sorted(result.saved_counts.items()))
        msg = f"Added {sum(result.saved_counts.values())} ideas: {summary}."
    elif result.extraction_error:
        msg = f"Report saved, but sorting into buckets failed: {result.extraction_error}"
    else:
        msg = "Report saved."
    return _back_to_project(name, msg, error=bool(result.extraction_error and not result.saved_counts))


@app.route("/p/<name>/reports/<filename>")
def report_page(name: str, filename: str):
    project = _project_or_404(name)
    path = project.ideas_reports_dir / filename
    if not path.is_file():
        abort(404)
    body = render(REPORT, project=project, filename=filename, text=path.read_text(encoding="utf-8"))
    return render(BASE, title=filename, body=body)


@app.route("/p/<name>/ideas", methods=["POST"])
def add_idea(name: str):
    project = _project_or_404(name)
    text = request.form.get("text", "").strip()
    bucket = request.form.get("bucket", "").strip()
    if not text or not bucket:
        return _back_to_project(name, "An idea needs both text and a bucket.", error=True)
    idea = Idea(
        id=project.allocate_idea_id(),
        text=text,
        bucket=bucket,
        date=datetime.now().isoformat(timespec="seconds"),
        tags=actions.parse_tags(request.form.get("tags")),
        status="open",
        origin="manual",
    )
    project.save_idea(idea)
    return _back_to_project(name, f"Saved idea in '{bucket}'.")


@app.route("/p/<name>/ideas/<idea_id>/bucket", methods=["POST"])
def idea_bucket_route(name: str, idea_id: str):
    project = _project_or_404(name)
    try:
        idea = project.load_idea(idea_id)
    except storage.IdeaNotFoundError:
        abort(404)
    bucket = request.form.get("bucket", "").strip()
    if bucket:
        idea.bucket = bucket
        project.save_idea(idea)
    return _back_to_project(name, f"Moved to '{idea.bucket}'.")


@app.route("/p/<name>/ideas/<idea_id>/status", methods=["POST"])
def idea_status_route(name: str, idea_id: str):
    project = _project_or_404(name)
    try:
        idea = project.load_idea(idea_id)
    except storage.IdeaNotFoundError:
        abort(404)
    status = request.form.get("status", "")
    if status in STATUSES:
        idea.status = status
        project.save_idea(idea)
    return _back_to_project(name, f"Marked {status}.")


def main():
    port = int(os.environ.get("WRITING_UI_PORT", "5050"))
    print(f"Writing UI running at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
