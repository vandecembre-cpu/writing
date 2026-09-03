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
