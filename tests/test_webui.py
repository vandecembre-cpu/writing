import io

import pytest

from writing_journal import ai, storage, webui


@pytest.fixture(autouse=True)
def projects_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITING_PROJECTS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def client():
    webui.app.config["TESTING"] = True
    return webui.app.test_client()


def test_index_lists_projects_and_creates_one(client, projects_dir):
    resp = client.get("/")
    assert b"No projects yet" in resp.data

    resp = client.post("/projects", data={"name": "journal"}, follow_redirects=True)
    assert resp.status_code == 200
    assert storage.Project(projects_dir, "journal").exists()
    assert b"journal" in resp.data


def test_creating_duplicate_project_shows_error(client, projects_dir):
    client.post("/projects", data={"name": "journal"})
    resp = client.post("/projects", data={"name": "journal"}, follow_redirects=True)
    assert b"already exists" in resp.data


def test_add_text_entry_and_view_it(client, projects_dir):
    client.post("/projects", data={"name": "journal"})
    resp = client.post(
        "/p/journal/entries/text",
        data={"text": "A typed thought.", "title": "My note", "tags": "a, b"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    project = storage.open_project(projects_dir, "journal")
    entries = project.list_entries()
    assert len(entries) == 1
    assert entries[0].title == "My note"
    assert entries[0].tags == ["a", "b"]

    entry_resp = client.get(f"/p/journal/entries/{entries[0].id}")
    assert b"A typed thought." in entry_resp.data


def test_update_entry(client, projects_dir):
    client.post("/projects", data={"name": "journal"})
    client.post("/p/journal/entries/text", data={"text": "Original text."})
    project = storage.open_project(projects_dir, "journal")
    entry_id = project.list_entries()[0].id

    client.post(
        f"/p/journal/entries/{entry_id}",
        data={"title": "New title", "text": "Edited text.", "tags": "x"},
    )
    updated = project.load_entry(entry_id)
    assert updated.title == "New title"
    assert updated.text == "Edited text."
    assert updated.tags == ["x"]


def test_digitize_entry_without_api_key_shows_error(client, projects_dir, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client.post("/projects", data={"name": "journal"})
    resp = client.post(
        "/p/journal/entries/digitize",
        data={"images": (io.BytesIO(b"fake-jpeg"), "page1.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"ANTHROPIC_API_KEY" in resp.data
    project = storage.open_project(projects_dir, "journal")
    assert project.list_entries() == []


def test_digitize_entry_saves_transcription(client, projects_dir, monkeypatch):
    monkeypatch.setattr(ai, "transcribe_images", lambda paths, model=None: "Transcribed text.")
    client.post("/projects", data={"name": "journal"})
    resp = client.post(
        "/p/journal/entries/digitize",
        data={"images": (io.BytesIO(b"fake-jpeg"), "page1.jpg"), "tags": "scan"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    project = storage.open_project(projects_dir, "journal")
    entries = project.list_entries()
    assert len(entries) == 1
    assert entries[0].text == "Transcribed text."
    assert entries[0].tags == ["scan"]
    assert entries[0].source_images


def test_idea_add_bucket_and_status(client, projects_dir):
    client.post("/projects", data={"name": "journal"})
    client.post(
        "/p/journal/ideas",
        data={"text": "A stray idea.", "bucket": "Fragments", "tags": "x"},
    )
    project = storage.open_project(projects_dir, "journal")
    ideas = project.list_ideas(status=None)
    assert len(ideas) == 1
    idea_id = ideas[0].id

    resp = client.get("/p/journal")
    assert b"Fragments" in resp.data
    assert b"A stray idea." in resp.data

    client.post(f"/p/journal/ideas/{idea_id}/bucket", data={"bucket": "Renewal"})
    assert project.load_idea(idea_id).bucket == "Renewal"

    client.post(f"/p/journal/ideas/{idea_id}/status", data={"status": "used"})
    assert project.load_idea(idea_id).status == "used"

    # default project page (status=open) should no longer show it
    resp = client.get("/p/journal")
    assert b"No ideas match" in resp.data
    resp = client.get("/p/journal?status=all")
    assert b"Renewal" in resp.data


def test_generate_ideas_route_sorts_into_buckets(client, projects_dir, monkeypatch):
    client.post("/projects", data={"name": "journal"})
    client.post("/p/journal/entries/text", data={"text": "A thought about starting over."})
    project = storage.open_project(projects_dir, "journal")
    entry_id = project.list_entries()[0].id

    monkeypatch.setattr(ai, "generate_ideas", lambda entries_text, focus=None, n=8, model=None: "## Themes")
    monkeypatch.setattr(
        ai,
        "extract_ideas",
        lambda entries_text, existing_buckets=None, focus=None, n=8, model=None: [
            {"text": "Write about starting over.", "bucket": "Fresh Starts", "source_entries": [entry_id]}
        ],
    )

    resp = client.post("/p/journal/ideas/generate", data={"count": "8"}, follow_redirects=True)
    assert resp.status_code == 200
    ideas = project.list_ideas()
    assert len(ideas) == 1
    assert ideas[0].bucket == "Fresh Starts"


def test_unknown_project_is_404(client):
    resp = client.get("/p/nope")
    assert resp.status_code == 404
