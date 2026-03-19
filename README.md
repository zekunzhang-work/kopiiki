# Kopiiki

A tool for extracting webpage snapshots into self-contained offline bundles.

## 🚀 Quick Start (GUI Mode)

The `start.sh` script automates environment setup and launches the frontend and backend services:
1. Validates Python 3 and Node.js environments.
2. Installs backend (`pip`) and frontend (`npm`) dependencies.
3. Downloads the Playwright Chromium binaries required for headless extraction.
4. Starts the Flask backend (`:5002`) and Vite frontend (`:5176`).

```bash
cd kopiiki
./start.sh
```

- **Frontend Interface**: http://localhost:5176
- **Backend Service**: http://localhost:5002

---

## 🤖 CLI & AI Agent Integration

Kopiiki can be used as a data-ingestion pipeline for AI agents (such as Cursor, Claude Code, etc.). 

A dedicated CLI script is provided for headless execution.

### Manual CLI Usage
To run the extraction pipeline from the terminal:
```bash
# 1. Enter the backend directory
cd kopiiki/backend

# 2. Activate the Python virtual environment
source venv/bin/activate

# 3. Execute the crawler targeting your desired URL
python cli.py https://example.com/
```
The script will start a headless Chromium instance, extract up to 6 top-level sub-pages, map the internal links, and save the resulting `[domain].zip` archive into `kopiiki/backend/downloads/`.

### AI Agent Workflow
LLM agents can integrate Kopiiki into their routines using the following steps:
1. Execute the shell command `python cli.py <URL>`.
2. Extract the archive using `unzip downloads/<domain>.zip -d ./working_dir`.
3. Read the generated `README.md` and the extracted `.html` components to establish a layout reference for generating React/Tailwind code.

---

## ⚙️ Architecture

The project uses a decoupled architecture for concurrent page rendering and asset fetching:

```
[ User Browser / AI Agent ]
      │
[ Frontend (React) :5176 ] <─── Real-time Status (SSE) ───┐
      │                                                   │
      └─── Extraction Request (POST) ───▶ [ Backend (Flask) :5002 ]
                                              │
                                              └──▶ [ Playwright (Chromium) / CLI script ]
                                                        │
                                                        └──▶ [ Target Website ]
```

- **Frontend**: Handles user interaction and progress tracking.
- **Backend**: Python service managing Playwright instances for rendering, navigation parsing, and local asset mapping.

---

## 🖥️ Frontend Guide

Kopiiki provides an interface for straightforward operations:

1. **Enter URL**: Type the target website URL in the central input field.
2. **Start Extraction**: Click the **Enter (KeyReturn)** icon on the right or press the Enter key.
3. **Monitor Progress**: Review real-time logs in the buffer below to track asset downloads.
4. **Cancel Job**: Click the **Stop (StopCircle)** icon at any time to abort the task.
5. **Get Result**: A ZIP bundle containing the offline-ready snapshot will be downloaded automatically upon completion.

![Frontend Interface Preview](docs/assets/preview.png)

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
