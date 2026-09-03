# writing

Digitize handwritten pages with Claude's vision, store them as Markdown
entries organized into projects, and generate ideas from your own writing
with the Claude API.

## How it works

- **Digitize**: photograph or scan a page, run `writing add`, and Claude
  transcribes the handwriting (including multi-page entries) into text.
- **Store**: each entry is saved as a Markdown file with YAML front matter
  (title, date, tags, and a link back to the source image) under
  `projects/<name>/entries/`. Everything is plain text, so it's diffable and
  lives happily in this git repo.
- **Generate ideas**: `writing ideas` sends your entries (optionally filtered
  by tag/date/topic) to Claude and gets back recurring themes, connections
  across entries, and a set of concrete idea prompts grounded in what you
  actually wrote.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

export ANTHROPIC_API_KEY=sk-ant-...   # console.anthropic.com
```

## Usage

```bash
# Create a project (a folder of related writing)
writing init journal

# Digitize a photo of a handwritten page (multiple images = one multi-page entry)
writing add photos/page1.jpg photos/page2.jpg --project journal --tags morning

# Add typed text directly (opens $EDITOR, or use --file/stdin)
writing add-text --project journal --title "Note to self"
echo "some thought" | writing add-text --project journal

# Browse
writing projects
writing list --project journal --tag morning
writing show 20260903-012608 --project journal
writing search "garden" --project journal

# Fix an OCR mistake by hand
writing edit 20260903-012608 --project journal

# Add/remove tags after the fact
writing tag 20260903-012608 favorite --project journal
writing tag 20260903-012608 favorite --project journal --remove

# Generate ideas from everything, or a slice of it
writing ideas --project journal
writing ideas --project journal --tag morning --since 2026-01-01 --focus "starting a garden"
```

If you only have one project, `--project` can be omitted; otherwise set it
per-command or export `WRITING_PROJECT`. Ideas reports are saved to
`projects/<name>/ideas/` alongside the entries they came from.

### Project layout

```
projects/<name>/
  project.yaml     # project metadata
  entries/*.md      # one transcribed/typed piece of writing per file
  sources/*.jpg      # original photos, kept next to their transcript
  ideas/*.md          # saved output of `writing ideas`
```

## Development

```bash
pip install -e . pytest
pytest
```

Tests mock all Claude API calls, so they run offline and don't require
`ANTHROPIC_API_KEY`.
