import io
import contextlib

import pytest

from writing_journal import ai, cli, storage


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.main(argv)
    return out.getvalue()


@pytest.fixture(autouse=True)
def projects_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITING_PROJECTS_DIR", str(tmp_path))
    monkeypatch.delenv("WRITING_PROJECT", raising=False)
    return tmp_path


def test_init_creates_project(projects_dir):
    out = run(["init", "notebook"])
    assert "Created project 'notebook'" in out
    assert storage.Project(projects_dir, "notebook").exists()


def test_add_digitizes_image_and_saves_entry(projects_dir, monkeypatch, tmp_path):
    run(["init", "notebook"])
    image = tmp_path / "page1.jpg"
    image.write_bytes(b"fake-jpeg-bytes")

    monkeypatch.setattr(ai, "transcribe_images", lambda paths, model=None: "Dear diary,\nToday was strange.")

    out = run(["add", str(image), "--project", "notebook", "--tags", "journal, odd"])
    assert "Saved entry" in out

    project = storage.open_project(projects_dir, "notebook")
    entries = project.list_entries()
    assert len(entries) == 1
    assert entries[0].tags == ["journal", "odd"]
    assert "Today was strange." in entries[0].text
    assert entries[0].source_images
    saved_source = project.path / entries[0].source_images[0]
    assert saved_source.exists()


def test_add_text_from_file(projects_dir, tmp_path):
    run(["init", "notebook"])
    text_file = tmp_path / "note.txt"
    text_file.write_text("A typed thought.\nSecond line.")

    out = run(["add-text", "--project", "notebook", "--file", str(text_file), "--title", "A note"])
    assert "Saved entry" in out

    project = storage.open_project(projects_dir, "notebook")
    entries = project.list_entries()
    assert len(entries) == 1
    assert entries[0].title == "A note"
    assert entries[0].digitized_with == "typed"


def test_list_search_and_tag(projects_dir, monkeypatch, tmp_path):
    run(["init", "notebook"])
    image = tmp_path / "page1.jpg"
    image.write_bytes(b"fake")
    monkeypatch.setattr(ai, "transcribe_images", lambda paths, model=None: "Thinking about the ocean today.")
    run(["add", str(image), "--project", "notebook"])

    project = storage.open_project(projects_dir, "notebook")
    entry_id = project.list_entries()[0].id

    listed = run(["list", "--project", "notebook"])
    assert entry_id in listed

    searched = run(["search", "ocean", "--project", "notebook"])
    assert entry_id in searched

    run(["tag", entry_id, "sea,mood", "--project", "notebook"])
    tagged = project.load_entry(entry_id)
    assert tagged.tags == ["mood", "sea"]


def test_ideas_command_generates_and_saves_report(projects_dir, tmp_path, monkeypatch):
    run(["init", "notebook"])
    text_file = tmp_path / "note.txt"
    text_file.write_text("A typed thought about starting over.")
    run(["add-text", "--project", "notebook", "--file", str(text_file)])

    monkeypatch.setattr(
        ai, "generate_ideas", lambda entries_text, focus=None, n=8, model=None: "## Recurring themes\n- starting over"
    )

    out = run(["ideas", "--project", "notebook", "--no-save"])
    assert "Recurring themes" in out


def test_resolve_project_requires_disambiguation_with_multiple(projects_dir, capsys):
    run(["init", "one"])
    run(["init", "two"])
    with pytest.raises(SystemExit):
        run(["list"])
    err = capsys.readouterr().err
    assert "Multiple projects exist" in err


def test_add_missing_api_key_reports_clearly(projects_dir, tmp_path, monkeypatch, capsys):
    run(["init", "notebook"])
    image = tmp_path / "page1.jpg"
    image.write_bytes(b"fake")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(SystemExit):
        run(["add", str(image), "--project", "notebook"])
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err
