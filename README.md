# Kopiiki

A tool for extracting webpage snapshots into self-contained offline bundles.

## 🚀 Quick Start

Run the start script from the project root to automate environment setup and launch the services:

```bash
cd kopiiki
./start.sh
```

- **Frontend Interface**: http://localhost:5176
- **Backend Service**: http://localhost:5002

---

## ⚙️ Architecture

The project uses a decoupled architecture for concurrent page rendering and asset fetching:

```
[ User Browser ]
      │
[ Frontend (React) :5176 ] <─── Real-time Status (SSE) ───┐
      │                                                │
      └─── Extraction Request (POST) ───▶ [ Backend (Flask) :5002 ]
                                              │
                                              └──▶ [ Playwright (Chromium) ]
                                                        │
                                                        └──▶ [ Target Website ]
```

- **Frontend**: Handles user interaction and visual progress tracking.
- **Backend**: Python service managing Playwright instances for high-fidelity rendering and recursive asset parsing.

---

## 🖥️ Frontend Guide

Kopiiki provides a minimal interface for straightforward operations:

1. **Enter URL**: Type the target website URL in the central input field.
2. **Start Extraction**: Click the **Enter (KeyReturn)** icon on the right or press the Enter key.
3. **Monitor Progress**: Review real-time logs in the buffer below to track asset downloads.
4. **Cancel Job**: Click the **Stop (StopCircle)** icon at any time to abort the task.
5. **Get Result**: A ZIP bundle containing the offline-ready snapshot will be downloaded automatically upon completion.

![Frontend Interface Preview](file:///Users/zzk.wegic.js/.gemini/antigravity/brain/6489c19b-8503-4976-a5a9-4860d1a2d42f/initial_state_1773729233817.png)

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
