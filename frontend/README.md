# Kopiiki Frontend

This is the React/Vite interface for Kopiiki.

It provides:

- The main URL input.
- The inline `Snapshot / Design` mode switch.
- Streaming extraction logs.
- ZIP download state.
- `HISTORY` and `README` drawers.

The frontend expects the Flask backend to run on `http://localhost:5002`.

## Run

From the repository root, the easiest path is:

```bash
./start.sh
```

To run only the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5176
```

Vite requires Node.js `20.19+` or `22.12+`.

If Playwright Chromium installation hangs while using `../start.sh`, you can start the UI only:

```bash
KOPIIKI_SKIP_BROWSER_INSTALL=1 ../start.sh
```

Extraction still needs Playwright Chromium to be installed before Snapshot or Design jobs can run.

## Usage Flow

1. Paste a website URL.
2. Choose `Snapshot` or `Design`.
3. Press Enter or click the return icon.
4. Wait for `DONE`.
5. Download the generated ZIP.

`Snapshot` creates an offline website archive. `Design` creates a Gemini-powered Design Capsule with `DESIGN.md`, reference files, and asset prompts for coding agents.

Design mode is prompt-first. It does not package source screenshots, source imagery, source videos, logos, commercial font files, trademarked graphics, or full original copy by default.

## Gemini State

`Design` needs `GEMINI_API_KEY` on the backend. The frontend reads `/api/config` only to show whether Gemini is configured. The API key is never sent to the browser.

## API Boundary

The backend is intended to run locally. By default it restricts CORS to local frontend origins and blocks localhost/private-network extraction targets unless `KOPIIKI_ALLOW_PRIVATE_TARGETS=1` is set for trusted local testing.

## Checks

```bash
npm run lint
npm run build
npm audit --audit-level=moderate
```

## Key Files

- `src/App.jsx`: global app state, drawers, history, config loading.
- `src/components/ExtractInterface.jsx`: URL form, mode switch, stream log UI.
- `src/components/HistoryDrawer.jsx`: previous ZIP archives.
- `src/components/ReadmeDrawer.jsx`: short in-app guide.
- `src/components/TopNav.jsx`: top navigation and external links.
- `src/components/TerminalCursor.jsx`: terminal-style cursor trail.
- `src/index.css`: terminal-style layout, hover rules, responsive styling.
