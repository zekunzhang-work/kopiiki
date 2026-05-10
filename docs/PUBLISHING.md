# Publishing Kopiiki

Use this note when preparing a public GitHub release or a short announcement.

## Release

Suggested tag:

```text
v0.1.0-alpha
```

Suggested title:

```text
Kopiiki v0.1.0-alpha
```

Suggested release notes:

```md
Kopiiki is a local tool for turning websites into offline snapshots or AI-readable design references for coding agents.

## What's included

- Snapshot mode: generate offline website ZIP archives.
- Design mode: generate a Gemini-powered Design Capsule with `DESIGN.md`, reference files, visual checkpoints, font fallback strategy, and asset prompts.
- Local Flask backend and React/Vite frontend.
- CLI support for `snapshot` and `design` modes.
- Safer defaults for local use: localhost binding, restricted CORS, private target blocking, and ignored `.env` files.

## Design Capsule boundary

Design mode is prompt-first. It does not package source screenshots, source images, videos, logos, commercial font files, trademarked graphics, or full original copy by default.

## Status

This is an alpha release for local experimentation, design research, and coding-agent workflows.

## Requirements

- Python 3
- Node.js 20.19+ or 22.12+
- Gemini API key for Design mode

## Start

```bash
git clone https://github.com/zekunzhang-work/kopiiki.git
cd kopiiki
cp .env.example .env
./start.sh
```

Open `http://localhost:5176`.
```

## Repository Topics

Suggested GitHub topics:

```text
design-tools
design-systems
web-archive
website-snapshot
coding-agents
design-to-code
gemini
playwright
flask
react
vite
ai-tools
markdown
```

## Smoke Test

Run this before announcing Design mode:

```bash
set -a
source .env
set +a
PYTHONPYCACHEPREFIX=/tmp/kopiiki-pycache backend/venv/bin/python -m unittest discover -s backend/tests
```

Expected result:

```text
Ran 10 tests
OK
```

If the real Gemini test is skipped, the process did not read `GEMINI_API_KEY`.

## Demo Checklist

A short demo should show:

- Kopiiki homepage with `Snapshot / Design`.
- A URL being pasted into the input.
- Design mode logs reaching `DONE`.
- The downloaded ZIP structure.
- `DESIGN.md`, `visual-checkpoints.md`, `font-strategy.md`, and `asset-prompts.md`.

Keep the demo under 35 seconds for social posting.

