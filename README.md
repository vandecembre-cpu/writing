# writing

Digitize handwritten pages with Claude's vision, store them as Markdown
entries organized into projects, and build a bucketed repository of ideas
mined from your own writing with the Claude API.

## How it works

- **Digitize**: photograph or scan a page, run `writing add`, and Claude
  transcribes the handwriting (including multi-page entries) into text.
- **Store**: each entry is saved as a Markdown file with YAML front matter
  (title, date, tags, and a link back to the source image) under
  `projects/<name>/entries/`. Everything is plain text, so it's diffable and
  lives happily in this git repo.
- **Generate ideas**: `writing ideas` sends your entries (optionally filtered
  by tag/date/topic) to Claude and gets back two things:
  - a freeform synthesis report — recurring themes and connections across
    entries — saved under `projects/<name>/ideas/reports/`.
  - a set of individual, concrete idea strings, each filed into a **bucket**
    (a category like "Family", "Craft Notes", "Place & Memory") and saved as
    its own entry under `projects/<name>/ideas/items/`. This is the
    repository you come back to later: `writing buckets` to see what's in
    it, `writing idea-list` to browse it, `writing idea-status` to mark an
    idea used once you've written it up.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

export ANTHROPIC_API_KEY=sk-ant-...   # console.anthropic.com
```

## Web UI

```bash
writing-ui
# -> Writing UI running at http://127.0.0.1:5050
```

Open that URL in a browser to create projects, digitize photos, type entries,
edit them, generate ideas, and browse/recategorize the bucket repository —
everything below, without the command line. It's a small local Flask server
bound to `127.0.0.1` only (set `WRITING_UI_PORT` to change the port), reading
and writing the exact same `projects/` directory as the CLI, so the two are
interchangeable.

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
# (writes a synthesis report AND sorts individual ideas into buckets)
writing ideas --project journal
writing ideas --project journal --tag morning --since 2026-01-01 --focus "starting a garden"
writing ideas --project journal --no-bucket   # report only, skip the idea repository
writing ideas --project journal --no-save     # bucket ideas only, skip the report file

# Browse the idea repository
writing buckets --project journal                      # bucket names + open idea counts
writing idea-list --project journal                     # open ideas, grouped by bucket
writing idea-list --project journal --bucket "Craft Notes"
writing idea-list --project journal --status all         # include used/archived ideas too
writing idea-show idea-20260903-012608 --project journal

# Jot down an idea by hand, outside of `writing ideas`
writing idea-add "A piece about the neighbor's dog" --bucket "Fragments" --project journal

# Recategorize or retire an idea
writing idea-bucket idea-20260903-012608 "Place & Memory" --project journal
writing idea-status idea-20260903-012608 used --project journal
```

If you only have one project, `--project` can be omitted; otherwise set it
per-command or export `WRITING_PROJECT`.

### Project layout

```
projects/<name>/
  project.yaml       # project metadata
  entries/*.md        # one transcribed/typed piece of writing per file
  sources/*.jpg        # original photos, kept next to their transcript
  ideas/
    reports/*.md        # freeform synthesis reports from `writing ideas`
    items/*.md            # the bucketed idea repository, one file per idea
```

## Development

```bash
pip install -e . pytest
pytest
```

Tests mock all Claude API calls, so they run offline and don't require
`ANTHROPIC_API_KEY`.
