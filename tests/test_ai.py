import pytest

from writing_journal import ai


def test_build_ideas_prompt_includes_focus_and_count():
    prompt = ai.build_ideas_prompt("ENTRY TEXT HERE", focus="grief", n=5)
    assert "grief" in prompt
    assert "5 ideas to write next" in prompt
    assert "ENTRY TEXT HERE" in prompt


def test_build_ideas_prompt_without_focus():
    prompt = ai.build_ideas_prompt("ENTRY TEXT HERE", focus=None, n=8)
    assert "specifically wants" not in prompt


def test_get_client_without_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ai.MissingApiKeyError):
        ai.get_client()


def test_image_block_rejects_unsupported_extension(tmp_path):
    bad = tmp_path / "scan.tiff"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError):
        ai._image_block(bad)


def test_build_idea_extraction_prompt_includes_existing_buckets():
    prompt = ai.build_idea_extraction_prompt("ENTRY TEXT HERE", existing_buckets=["Family", "Craft"], n=5)
    assert "Family, Craft" in prompt
    assert "exactly 5 objects" in prompt
    assert "ENTRY TEXT HERE" in prompt


def test_build_idea_extraction_prompt_without_existing_buckets():
    prompt = ai.build_idea_extraction_prompt("ENTRY TEXT HERE", existing_buckets=None, n=3)
    assert "no buckets yet" in prompt


def test_parse_json_array_handles_plain_json():
    data = ai._parse_json_array('[{"text": "a", "bucket": "Craft"}]')
    assert data == [{"text": "a", "bucket": "Craft"}]


def test_parse_json_array_strips_markdown_fence():
    data = ai._parse_json_array('```json\n[{"text": "a", "bucket": "Craft"}]\n```')
    assert data == [{"text": "a", "bucket": "Craft"}]


def test_parse_json_array_rejects_non_array():
    with pytest.raises(ai.IdeaExtractionError):
        ai._parse_json_array('{"text": "a"}')


def test_parse_json_array_rejects_invalid_json():
    with pytest.raises(ai.IdeaExtractionError):
        ai._parse_json_array("not json at all")
