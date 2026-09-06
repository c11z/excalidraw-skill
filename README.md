# excalidraw-skill

A testbed for refining the `excalidraw-diagram` skill for [Claude Code](https://docs.anthropic.com/en/docs/claude-code),
a skill that produces Excalidraw diagrams which **argue visually** rather than just label boxes. The skill itself lives
in `.claude/skills/excalidraw-diagram/` and is forked from
[coleam00/excalidraw-diagram-skill](https://github.com/coleam00/excalidraw-diagram-skill) with a few changes:

- **Okabe-Ito color palette.** All colors derive from the colorblind-safe Okabe-Ito hues, defined in
  `references/color-palette.md`.
- **Lint hook.** `references/lint_excalidraw.py` runs automatically after every file write (see `.claude/settings.json`)
  and checks `.excalidraw` files for structural problems.
- **Render pipeline.** `references/render_excalidraw.py` renders `.excalidraw` files to PNG with Playwright so the agent
  can inspect and fix its own output.

Finished diagrams go in `diagrams/`, one subdirectory per project with the `.excalidraw` source and rendered `.png`.

## Layout

```text
.claude/
  settings.json                       # PostToolUse hook that lints Excalidraw JSON
  skills/excalidraw-diagram/
    SKILL.md                          # Design methodology + workflow
    README.md                         # Upstream skill docs
    references/
      color-palette.md                # Okabe-Ito palette (edit to rebrand)
      element-templates.md            # JSON templates for each element type
      json-schema.md                  # Excalidraw JSON format reference
      lint_excalidraw.py              # Structural linter (also runs as a hook)
      render_excalidraw.py            # Render .excalidraw to PNG
      render_template.html            # Browser template used by the renderer
      pyproject.toml                  # Python deps (playwright)
diagrams/
  vacasa-data-platform/               # Example diagram project
```

## Setup

The renderer needs Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
cd .claude/skills/excalidraw-diagram/references
uv sync
uv run playwright install chromium
```

## Usage

Open the repo in Claude Code and ask for a diagram:

> Create an Excalidraw diagram showing how events flow from the ingestion service to the warehouse.

The skill handles concept mapping, layout, JSON generation, linting, rendering, and visual validation. To render or lint
by hand:

```bash
cd .claude/skills/excalidraw-diagram/references
uv run python render_excalidraw.py ../../../../diagrams/my-project/my-diagram.excalidraw
python3 lint_excalidraw.py ../../../../diagrams/my-project/my-diagram.excalidraw
```

## Using the skill elsewhere

Copy `.claude/skills/excalidraw-diagram/` into another project's `.claude/skills/` directory. Copy the hook from
`.claude/settings.json` too if you want automatic linting there.
