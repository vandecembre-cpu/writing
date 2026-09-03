from pathlib import Path

import pytest

from writing_journal import storage
from writing_journal.entry import Entry, parse_markdown


def test_init_and_open_project(tmp_path):
    project = storage.init_project(tmp_path, "notebook")
    assert project.exists()
    assert project.entries_dir.is_dir()
    assert project.sources_dir.is_dir()
    assert project.ideas_dir.is_dir()

    reopened = storage.open_project(tmp_path, "notebook")
    assert reopened.path == project.path


def test_init_project_twice_raises(tmp_path):
    storage.init_project(tmp_path, "notebook")
    with pytest.raises(storage.ProjectExistsError):
        storage.init_project(tmp_path, "notebook")


def test_open_missing_project_raises(tmp_path):
    with pytest.raises(storage.ProjectNotFoundError):
        storage.open_project(tmp_path, "nope")


def test_entry_roundtrip(tmp_path):
    project = storage.init_project(tmp_path, "notebook")
    entry = Entry(
        id="20260101-120000",
        title="Test entry",
        date="2026-01-01T12:00:00",
        text="Some transcribed text.\n\nWith a second paragraph.",
        tags=["journal", "test"],
        source_images=["sources/20260101-120000-0.jpg"],
        digitized_with="claude-vision (claude-sonnet-5)",
    )
    path = project.save_entry(entry)
    assert path.exists()

    loaded = parse_markdown(path)
    assert loaded.id == entry.id
    assert loaded.title == entry.title
    assert loaded.tags == entry.tags
    assert loaded.text == entry.text
    assert loaded.source_images == entry.source_images


def test_list_entries_filters_by_tag_and_sorts(tmp_path):
    project = storage.init_project(tmp_path, "notebook")
    project.save_entry(Entry(id="a", title="A", date="2026-01-01T00:00:00", text="first", tags=["x"]))
    project.save_entry(Entry(id="b", title="B", date="2026-02-01T00:00:00", text="second", tags=["y"]))
    project.save_entry(Entry(id="c", title="C", date="2026-03-01T00:00:00", text="third", tags=["x"]))

    all_entries = project.list_entries()
    assert [e.id for e in all_entries] == ["c", "b", "a"]

    x_entries = project.list_entries(tag="x")
    assert [e.id for e in x_entries] == ["c", "a"]


def test_allocate_entry_id_avoids_collision(tmp_path, monkeypatch):
    from datetime import datetime

    project = storage.init_project(tmp_path, "notebook")
    now = datetime(2026, 1, 1, 12, 0, 0)
    first = project.allocate_entry_id(now)
    project.save_entry(Entry(id=first, title="A", date=now.isoformat(), text="a"))
    second = project.allocate_entry_id(now)
    assert second != first


def test_search_finds_text_in_body(tmp_path):
    project = storage.init_project(tmp_path, "notebook")
    project.save_entry(
        Entry(id="a", title="Ocean thoughts", date="2026-01-01T00:00:00", text="I keep thinking about the tide.")
    )
    project.save_entry(Entry(id="b", title="Unrelated", date="2026-01-02T00:00:00", text="Nothing to see here."))

    results = project.search("tide")
    assert [e.id for e, _ in results] == ["a"]


def test_list_projects(tmp_path):
    storage.init_project(tmp_path, "one")
    storage.init_project(tmp_path, "two")
    assert storage.list_projects(tmp_path) == ["one", "two"]
