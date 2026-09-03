"""Thin wrapper around the Claude API: handwriting transcription + idea generation."""

from __future__ import annotations

import base64
import os
from pathlib import Path

DEFAULT_MODEL = os.environ.get("WRITING_JOURNAL_MODEL", "claude-sonnet-5")

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class MissingApiKeyError(RuntimeError):
    def __init__(self):
        super().__init__(
            "ANTHROPIC_API_KEY is not set. Get a key from https://console.anthropic.com/ "
            "and export it, e.g.:\n\n  export ANTHROPIC_API_KEY=sk-ant-...\n"
        )


def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingApiKeyError()
    import anthropic

    return anthropic.Anthropic()


def _image_block(path: Path) -> dict:
    media_type = _MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(
            f"Unsupported image type '{path.suffix}' for {path}. "
            f"Supported: {', '.join(sorted(_MEDIA_TYPES))}"
        )
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


TRANSCRIBE_PROMPT = (
    "You are transcribing photos of handwritten pages for a personal writing archive. "
    "Transcribe the handwriting exactly as written: preserve line breaks, paragraph breaks, "
    "spelling, and punctuation, including crossed-out or corrected text (mark strikethroughs "
    "as [struck: ...]). If a word or phrase is illegible, write [illegible] in its place rather "
    "than guessing. If the pages are numbered or clearly sequential, transcribe them in order "
    "with a blank line between pages. Output only the transcription — no preamble, no commentary, "
    "no markdown formatting, no commentary about the handwriting style."
)


def transcribe_images(image_paths: list[Path], model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    content = [_image_block(p) for p in image_paths]
    content.append({"type": "text", "text": TRANSCRIBE_PROMPT})
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


IDEAS_SYSTEM_PROMPT = (
    "You are a sharp, generous writing collaborator helping a writer mine their own archive "
    "of journal entries, notes, and drafts for new ideas. You read what they've actually written "
    "closely and specifically — quoting or referencing real lines and moments rather than speaking "
    "generically. You never invent facts about the writer's life beyond what's in the text."
)


def build_ideas_prompt(entries_text: str, focus: str | None, n: int) -> str:
    focus_line = f"\nThe writer specifically wants ideas related to: {focus}\n" if focus else ""
    return f"""Below are entries from a writer's personal archive, most recent first.
{focus_line}
Read across all of them and produce a Markdown report with these sections:

## Recurring themes
3-6 bullet points naming patterns, preoccupations, images, or tensions that recur across
multiple entries. Quote a short phrase from the text for each.

## Connections worth noticing
2-4 bullet points linking two or more entries that resonate, contradict, or build on each
other in a way the writer may not have noticed.

## {n} ideas to write next
A numbered list of {n} concrete, specific idea prompts (essays, poems, scenes, projects —
whatever fits the material) that grow directly out of this writing. Each should be one or two
sentences: a hook plus why it's there in the text. Avoid generic advice; ground every idea in
something specific from the entries.

--- ENTRIES ---

{entries_text}
"""


def generate_ideas(entries_text: str, focus: str | None = None, n: int = 8, model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    prompt = build_ideas_prompt(entries_text, focus, n)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=IDEAS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
