import React from 'react';
import { BookOpen, X } from '@phosphor-icons/react';

const ReadmeDrawer = ({ isOpen, onClose }) => (
  <div className={`readme-shell ${isOpen ? 'open' : ''}`} aria-hidden={!isOpen}>
    <button className="readme-backdrop" type="button" onClick={onClose} tabIndex={isOpen ? 0 : -1} />
    <aside className="readme-panel" aria-label="Kopiiki README">
      <div className="readme-header">
        <div className="readme-title-block">
          <BookOpen size={18} weight="bold" />
          <span>README</span>
        </div>
        <button className="readme-icon-btn" type="button" onClick={onClose} title="Close README">
          <X size={16} weight="bold" />
        </button>
      </div>

      <div className="readme-content">
        <section>
          <h2>QUICK START</h2>
          <ol>
            <li>Open a terminal in the Kopiiki folder.</li>
            <li>Run <code>./start.sh</code>.</li>
            <li>Open <code>http://localhost:5176</code>.</li>
          </ol>
        </section>

        <section>
          <h2>API KEY</h2>
          <p><code>Snapshot</code> works without an API key. <code>Design</code> needs Gemini.</p>
          <ol>
            <li>Copy <code>.env.example</code> to <code>.env</code>.</li>
            <li>Fill <code>GEMINI_API_KEY</code>.</li>
            <li>Restart the backend after changing <code>.env</code>.</li>
          </ol>
        </section>

        <section>
          <h2>BACKEND</h2>
          <p>Run the backend on port <code>5002</code>.</p>
          <pre><code>backend/venv/bin/python backend/app.py</code></pre>
          <p>Backend logs are printed in the terminal. With <code>./start.sh</code>, logs also go to <code>backend.log</code>.</p>
        </section>

        <section>
          <h2>FRONTEND</h2>
          <p>Run the frontend on port <code>5176</code>.</p>
          <pre><code>npm --prefix frontend run dev -- --port 5176</code></pre>
        </section>

        <section>
          <h2>USE THE APP</h2>
          <ol>
            <li>Paste a website URL.</li>
            <li>Choose <code>Snapshot</code> or <code>Design</code>.</li>
            <li>Press Enter or click the return icon.</li>
            <li>Wait for <code>DONE</code>, then download the ZIP.</li>
          </ol>
        </section>

        <section>
          <h2>MODES</h2>
          <p><code>Snapshot</code> creates an offline website archive.</p>
          <p><code>Design</code> creates a Markdown Design Capsule for coding agents.</p>
          <p><code>Design</code> does not package source screenshots, images, videos, logos, or commercial font files.</p>
        </section>

        <section>
          <h2>HISTORY</h2>
          <p>Open <code>HISTORY</code> in the top-right nav to download previous ZIP files, copy paths, refresh records, or delete old archives.</p>
          <p>Generated files are stored in <code>backend/downloads</code>.</p>
        </section>

        <section>
          <h2>CHECK DESIGN ZIP</h2>
          <p>Unzip a Design Capsule and run its built-in check.</p>
          <pre><code>node design/scripts/validate-design-capsule.mjs</code></pre>
        </section>
      </div>
    </aside>
  </div>
);

export default ReadmeDrawer;
