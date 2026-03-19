# Kopiiki AI Agent Context 

> **Important**: This file contains the foundational product philosophy, current architectural status, and critical design decisions for Kopiiki. **Every AI agent MUST read and adhere to these principles before suggesting or making any code changes.**

## 🎯 1. Core Product Goal (项目核心定位与诉求)
Kopiiki is **NOT** a traditional "offline HTML viewer" (like HTTrack) for human consumption, nor is it a simple web scraper.

**Kopiiki is an Upstream Data-Ingestion Pipeline for an AI-Driven React Refactoring SOP.**
- **The Workflow:** Kopiiki extracts the precise styling, images, and structural DOM of any target website (HTML/React/Vue). This extracted artifact (the ZIP bundle) is then fed into a downstream LLM Agent SOP. The downstream AI reads these pristine assets and semantic tags to "reverse-engineer" and generate a native, componentized React source code repository with **95%+ visual fidelity**.
- **The Value Proposition:** Kopiiki handles the messy "first half" (bypassing anti-bot protections, waiting for lazy-loaded DOMs, capturing network assets, and mapping local references). The AI handles the "second half" (understanding the layout and writing Tailwind/React code).

## 🏗️ 2. Current Architecture & Status (当前现状事实)
- **Tech Stack:**
  - **Backend**: Python Flask + Playwright (`app.py`, `webtwin_assets.py`). Uses synchronous Playwright to freeze animations, scroll for lazy-loaded items, and capture network responses in memory.
  - **Frontend**: React + Vite (`App.jsx`), featuring a terminal-like TUI with real-time SSE logs.
- **The "Local DOM Rewriter" (Crucial Feature):** 
  - In `webtwin_assets.py`, Kopiiki parses the downloaded HTML/CSS and **strictly rewrites all absolute URLs (`https://...`) to local relative paths (`./img/logo.png`)**. 
  - **Why this matters:** This is the most critical feature bridging the gap to the LLM. Because the HTML explicitly points to `./img/xxx.png`, the downstream LLM doesn't have to "guess" which downloaded image corresponds to which DOM node. It can confidently generate `<img src="/img/xxx.png" />` in its React output. **Never revert this behavior.**
- **Concurrency Model:**
  - Designed as a **single-user local desktop tool**.
  - Uses a single-instance exclusive lock (`EXTRACTION_LOCK`) and a `CANCEL_TOKEN` in `app.py`. Do not over-engineer with Redis/Celery queueing systems.

## 🚫 3. Strict Rules & Anti-Patterns (禁忌操作)
1. **DO NOT introduce "Absolute URLs" back into the unified HTML payload.** The LLM SOP relies on the exact localized mappings generated inside the ZIP archive.
2. **DO NOT process generic iframes as JS.** Iframes from unknown external sources should be isolated or ignored, not appended to the `js` compilation pipeline, to avoid corrupting the output intent.
3. **DO NOT use Python's raw `threading` without checking `CANCEL_TOKEN`.** Playwright headless browsers consume massive local resources. Every loop must respect the user's cancellation signal.

## 🚀 4. Next Evolution Blueprint (下一步关键演进)
The ultimate evolution to perfectly serve the LLM SOP lies in the currently stubbed `GET /api/extract-json` endpoint. To solve the "Context Window Exhaustion" caused by cross-referencing massive obfuscated CSS files (`class="css-1a2b3c"`), Kopiiki should adopt **Computed Style Inlining**:
1. **The Playwright Advantage**: Instead of downloading external scoped CSS and forcing the LLM to do expensive string-matching (which works on small pages but causes severe attention dilution on large ones), use Playwright to call `window.getComputedStyle()` on every visible node.
2. **Absolute Framework Agnosticism**: Inject the final computed layout rules directly into the DOM as `style="display:flex; color:#333;"`. This collapses Tailwind, CSS Modules, or Styled Components into a single, self-contained truth.
3. **AST JSON/Markdown Serialization**: Output this normalized, self-contained tree (stripping all `<script>`, tracking wrappers, and `<link>` tags) as highly dense Markdown or JSON. This ensures the downstream AI receives the maximum signal-to-noise ratio for constructing the React replica, consciously trading responsive breakpoints (media queries) for 100% deterministic visual layout extraction.

---
*If you are an AI reading this, acknowledge these rules and ask the user which module of the Kopiiki pipeline you should improve next based on the LLM SOP goal.*
