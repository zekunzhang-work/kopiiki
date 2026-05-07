# Kopiiki

Kopiiki extracts websites in two ways:

- **Snapshot**: an offline website archive with rewritten local assets.
- **Design**: an AI-generated Design Capsule, centered on `DESIGN.md`, for coding agents that need to rebuild a site's design language without copying protected assets.

The app keeps a minimal TUI-inspired interface: paste a URL, choose `Snapshot / Design`, run the extraction, watch the log stream, and download the ZIP.

## Quick Start

Run both services from the project root:

```bash
./start.sh
```

The script:

1. Checks Python 3 and Node.js.
2. Installs backend and frontend dependencies.
3. Installs Playwright Chromium if needed.
4. Starts the Flask backend on `:5002`.
5. Starts the Vite frontend on `:5176`.

Open:

- Frontend: http://localhost:5176
- Backend: http://localhost:5002

Vite requires Node.js `20.19+` or `22.12+`.

## Gemini Setup

`Snapshot` works without an API key. `Design` requires Gemini.

```bash
cp .env.example .env
# edit .env and fill GEMINI_API_KEY
```

Optional variables:

```bash
KOPIIKI_GEMINI_MODEL=gemini-3-pro-preview
KOPIIKI_GEMINI_MOCK=1
```

`KOPIIKI_GEMINI_MODEL` defaults to `gemini-3-pro-preview`. If your account does not have preview model access, use `gemini-2.5-pro`.

Restart the backend after changing `.env`.

## GUI Usage

1. Open `http://localhost:5176`.
2. Paste a website URL in the input line.
3. Choose `Snapshot` or `Design`.
4. Press Enter or click the return icon.
5. Wait for `DONE`.
6. Download the generated ZIP.

Use the top-right `HISTORY` panel to download previous ZIP files, copy relative paths, refresh records, or delete old archives. Generated files are stored in `backend/downloads`.

Use the top-right `README` panel for the short in-app guide.

## Output Modes

### Snapshot

Snapshot generates:

```text
<domain>-<jobid>.zip
```

It captures the target page and linked local assets so the result can be opened offline.

### Design

Design mode:

1. Captures deterministic browser evidence with Playwright across desktop, tablet, and mobile viewports.
2. Sends temporary screenshots and extracted DOM/CSS evidence to Gemini.
3. Writes a Markdown-first Design Capsule.
4. Does not package original screenshots, source images, source videos, logos, commercial font files, or trademarked artwork.

Design generates:

```text
<domain>-design-<jobid>.zip
```

ZIP structure:

```text
DESIGN.md
design/
  references/section-anatomy.md
  references/layout-grammar.md
  references/font-strategy.md
  references/component-families.md
  references/motion.md
  references/responsive.md
  references/asset-prompts.md
  references/visual-checkpoints.md
  evidence/observations.md
  evidence/section-map.md
  evidence/observations.json
  scripts/validate-design-capsule.mjs
```

`DESIGN.md` includes tokens, layout grammar, section anatomy, font fallback guidance, responsive strategy, motion guidance, do/don't rules, and references to asset prompts.

Asset prompts specify format, size, background, alpha/transparent requirements, placement, generation prompt, avoid rules, and implementation notes. Kopiiki only writes prompts; it does not generate or download image/video assets.

After unzipping a Design Capsule, run:

```bash
node design/scripts/validate-design-capsule.mjs
```

## CLI Usage

From the backend directory:

```bash
cd backend
source venv/bin/activate

# Snapshot mode
python cli.py https://example.com/
python cli.py https://example.com/ --mode snapshot

# Design mode
python cli.py https://example.com/ --mode design
python cli.py https://example.com/ --design
```

CLI output is written to `backend/downloads`.

## API Notes

The frontend talks to the Flask backend over:

- `POST /api/extract` with `{ url, mode }`
- `GET /api/progress/<job_id>` for SSE logs
- `POST /api/cancel/<job_id>`
- `GET /api/download/<filename>`
- `GET /api/history`
- `GET /api/config`

`/api/config` reports whether Gemini is configured, the provider, mock flag, and model name. It never returns the API key.

## Validation

Backend tests use Python `unittest`:

```bash
PYTHONPYCACHEPREFIX=/tmp/kopiiki-pycache backend/venv/bin/python -m unittest discover -s backend/tests
```

The mock Design Capsule tests run without a Gemini key. If `GEMINI_API_KEY` is set, the suite can also run a real Gemini smoke test against a local HTML fixture.

Frontend checks:

```bash
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Architecture

```text
[ Browser UI / CLI / Agent ]
        |
        v
[ React frontend :5176 ] -- SSE logs --> [ Flask backend :5002 ]
        |                                      |
        |                                      v
        |                         [ Playwright Chromium capture ]
        |                                      |
        |                                      v
        |                           [ Target website evidence ]
        |                                      |
        |                                      v
        |                         [ Snapshot ZIP or Gemini Design ZIP ]
```

Key backend modules:

- `backend/app.py`: API, jobs, SSE, history, downloads.
- `backend/cli.py`: headless CLI entrypoint.
- `backend/webtwin_assets.py`: Snapshot extraction.
- `backend/design_evidence.py`: multi-viewport DOM/CSS/screenshot evidence.
- `backend/gemini_design.py`: Gemini prompt, JSON parsing, fallback normalization.
- `backend/design_capsule.py`: `DESIGN.md` and reference file rendering.

## Legal Boundary

Kopiiki is intended for personal backup, development, testing, research, and education.

Users are responsible for respecting target-site terms, `robots.txt`, copyright law, trademark law, and font/media licenses.

Design mode is deliberately prompt-first: it does not include source screenshots, source imagery, source videos, logos, commercial font files, trademarked graphics, or full original copy by default.

## Acknowledgements

Kopiiki is inspired by [WebTwin](https://github.com/sirioberati/WebTwin) and extends the idea toward agent-readable design extraction.

[MIT License](LICENSE)
