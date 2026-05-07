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

## Usage Flow

1. Paste a website URL.
2. Choose `Snapshot` or `Design`.
3. Press Enter or click the return icon.
4. Wait for `DONE`.
5. Download the generated ZIP.

`Snapshot` creates an offline website archive. `Design` creates a Gemini-powered Design Capsule with `DESIGN.md`, reference files, and asset prompts for coding agents.

## Gemini State

`Design` needs `GEMINI_API_KEY` on the backend. The frontend reads `/api/config` only to show whether Gemini is configured. The API key is never sent to the browser.

## Checks

```bash
npm run lint
npm run build
```

## Key Files

- `src/App.jsx`: global app state, drawers, history, config loading.
- `src/components/ExtractInterface.jsx`: URL form, mode switch, stream log UI.
- `src/components/HistoryDrawer.jsx`: previous ZIP archives.
- `src/components/ReadmeDrawer.jsx`: short in-app guide.
- `src/components/TopNav.jsx`: top navigation and external links.
- `src/components/TerminalCursor.jsx`: terminal-style cursor trail.
- `src/index.css`: TUI layout, hover rules, responsive styling.
