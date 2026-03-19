# Kopiiki

A tool for extracting webpage snapshots into self-contained offline bundles.

## 🚀 Quick Start (GUI Mode)

For a seamless out-of-the-box experience with a Terminal User Interface (TUI) and visual progress bars, use the included bootstrap script.

The `start.sh` script is a foolproof initiator that:
1. Validates your Python 3 and Node.js environments.
2. Automatically installs backend (`pip`) and frontend (`npm`) dependencies.
3. Automatically downloads the Playwright Chromium binaries required for headless extraction.
4. Concurrently boots the Flask backend (`:5002`) and Vite frontend (`:5176`).

```bash
cd kopiiki
./start.sh
```

- **Frontend Interface**: http://localhost:5176
- **Backend Service**: http://localhost:5002

---

## 🤖 CLI & AI Agent Integration

Kopiiki is fundamentally designed as an **Upstream Data-Ingestion Pipeline for AI Agents** (such as Cursor, Claude Code, Aider, etc.). 

If you or your autonomous Agent prefer to run Kopiiki without the GUI overhead, a dedicated CLI wrapper is available.

### Manual CLI Usage
You can invoke the extraction pipeline directly from your terminal:
```bash
# 1. Enter the backend directory
cd kopiiki/backend

# 2. Activate the Python virtual environment
source venv/bin/activate

# 3. Execute the crawler targeting your desired URL
python cli.py https://example.com/
```
The engine will boot a headless Chromium instance, sniff up to 6 topological sub-pages, map and stitch the AST, and silently drop the assembled `[domain].zip` into `kopiiki/backend/downloads/`.

### AI Agent Workflow
LLM Autonomous Agents can perfectly slot Kopiiki into their CI/CD or codebase refactoring routines:
1. The Agent executes the shell command `python cli.py <URL>`.
2. Upon success, the Agent executes `unzip downloads/<domain>.zip -d ./working_dir`.
3. The Agent reads the dynamically generated `README.md` and the perfectly-linked, offline-first `.html` components to establish a ground-truth layout layout reference for producing React/Tailwind code.

---

## ⚙️ Architecture

The project uses a decoupled architecture for concurrent page rendering and asset fetching:

```
[ User Browser / AI Agent ]
      │
[ Frontend (React) :5176 ] <─── Real-time Status (SSE) ───┐
      │                                                │
      └─── Extraction Request (POST) ───▶ [ Backend (Flask) :5002 ]
                                              │
                                              └──▶ [ Playwright (Chromium) / CLI script ]
                                                        │
                                                        └──▶ [ Target Website ]
```

- **Frontend**: Handles user interaction and visual progress tracking.
- **Backend**: Python service managing Playwright instances for high-fidelity rendering, native navigation sniffing, and AST rewriting for true offline local mapping.

---

## ❤️ Acknowledgements & Legal Disclaimer

### Acknowledgements
This project is inspired by and built upon the foundation of [**WebTwin**](https://github.com/sirioberati/WebTwin). We thank the original authors for their open-source contributions to web archival research.

### Legal Disclaimer
1. **Intended Use**: Kopiiki is designed for personal backup, testing, research, and educational purposes ONLY.
2. **Compliance**: Users are responsible for ensuring their usage complies with the target website's `robots.txt`, Terms of Service, and applicable copyright laws.
3. **Liability**: The developers of Kopiiki assume no liability for any misuse of this tool, copyright infringement, or legal issues resulting from extracted content.

---

[MIT License](LICENSE)
