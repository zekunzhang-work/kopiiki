<div align="center">

# 🔮 Kopiiki

**Clone any website into a portable asset bundle — powered by Playwright.**

Extract the full visual snapshot of any webpage (HTML, CSS, JS, images, fonts, metadata) into a self-contained ZIP file that renders offline.

[Quick Start](#-quick-start) · [Docker](#-docker) · [How It Works](#-how-it-works) · [Output Format](#-output-format) · [Roadmap](#-roadmap)

</div>

---

## ✨ Features

- **🎭 Playwright-powered** — Uses a real Chromium browser to render JavaScript, trigger lazy loading, and capture the fully hydrated DOM.
- **📦 Complete asset extraction** — Downloads CSS, JS, images, fonts, favicons, videos, and audio referenced by the page.
- **🧩 Component detection** — Automatically identifies navigation, headers, footers, hero sections, cards, forms, and more.
- **📋 Metadata export** — Extracts SEO metadata, Open Graph tags, structured data (JSON-LD), and font families into `metadata.json`.
- **🖥️ Modern UI** — Dark, minimal, high-fidelity interface built with React + Vite.
- **🐳 Docker ready** — One command to run without installing Python or Node.js.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+

### One-click launch

```bash
git clone https://github.com/YOUR_USERNAME/kopiiki.git
cd kopiiki
./start.sh
```

The script automatically handles virtual environment creation, dependency installation, Playwright browser download, and starts both services. Open **http://localhost:5176** in your browser.

### Manual setup

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python app.py    # Runs on port 5002

# Frontend (in a new terminal)
cd frontend
npm install
npm run dev      # Runs on port 5176
```

---

## 🐳 Docker

No Python or Node.js required — just Docker:

```bash
docker compose up
# or
docker build -t kopiiki . && docker run -p 5000:5000 kopiiki
```

Open **http://localhost:5000** and start extracting.

---

## ⚙️ How It Works

```
┌──────────┐     POST /api/extract      ┌──────────────┐
│  React   │ ──────────────────────────▸ │  Flask API   │
│ Frontend │                             │   (Python)   │
│ :5176    │ ◂────── ZIP stream ──────── │   :5002      │
└──────────┘                             └──────┬───────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │  Playwright Chromium  │
                                    │  (headless browser)   │
                                    └───────────┬───────────┘
                                                │
                                    1. Navigate to URL
                                    2. Wait for network idle
                                    3. Disable animations
                                    4. Scroll to trigger lazy load
                                    5. Capture full DOM
                                                │
                                    ┌───────────▼───────────┐
                                    │  Asset Extraction     │
                                    │  (BeautifulSoup +     │
                                    │   requests)           │
                                    └───────────┬───────────┘
                                                │
                                    6. Parse HTML for asset URLs
                                    7. Download CSS, JS, images,
                                       fonts, videos, favicons
                                    8. Extract metadata & components
                                    9. Package into ZIP
```

---

## 📁 Output Format

The downloaded ZIP contains:

```
website_extract.zip
├── index.html          # Full rendered HTML with fixed URLs
├── css/                # Stylesheets (external + imported)
│   └── fonts.css       # Auto-generated Google Fonts imports
├── js/                 # JavaScript files
├── img/                # Images (png, jpg, svg, webp, etc.)
├── fonts/              # Web fonts (woff2, ttf, etc.)
├── favicons/           # Favicon files
├── videos/             # Video assets
├── audio/              # Audio assets
├── components/         # Detected UI components
│   ├── index.html      # Component viewer page
│   ├── navigation/     # Nav components
│   ├── header/         # Header components
│   ├── hero/           # Hero sections
│   ├── card/           # Card patterns
│   └── ...
├── metadata.json       # SEO, OG tags, structured data
└── README.md           # Usage instructions
```

### Viewing the extracted site

For best results, serve the extracted files locally:

```bash
cd extracted_site
python3 -m http.server 8000
# Open http://localhost:8000
```

---

## ⚠️ Disclaimer

This tool is intended for **personal backup, self-testing, educational, and research purposes only**. Users are solely responsible for ensuring their use complies with:

- The target website's Terms of Service and `robots.txt`
- Applicable copyright and intellectual property laws in their jurisdiction
- Any relevant data protection regulations

The authors of Kopiiki are not responsible for any misuse of this tool.

---

## 📄 License & Acknowledgements

[MIT](LICENSE)

Kopiiki is built upon the foundation of [**WebTwin**](https://github.com/sirioberati/WebTwin) by [@sirioberati](https://github.com/sirioberati) (Sirio Berati). The original WebTwin copyright is preserved in the LICENSE file. We are grateful for the open-source work that made this project possible.
