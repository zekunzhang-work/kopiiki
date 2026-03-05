import { useState } from 'react';
import './index.css';

// SVG Icon Component
const ZapIcon = () => (
  <svg
    className="logo-icon"
    xmlns="http://www.w3.org/2000/svg"
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z" />
  </svg>
);

function App() {
  const [url, setUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [isError, setIsError] = useState(false);

  const handleExtract = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    setIsLoading(true);
    setIsError(false);

    // Animate some interesting messages during the long playwright extraction
    let messageIndex = 0;
    const progressMessages = [
      "Initializing Headless Browser...",
      "Navigating to URL & Bypassing Anti-Bot...",
      "Injecting CSS to Freeze Animations...",
      "Scrolling to Trigger Lazy-loaded Assets...",
      "Compiling Final DOM & Downloading ZIP..."
    ];

    setMessage(progressMessages[0]);
    const messageInterval = setInterval(() => {
      messageIndex = (messageIndex + 1) % progressMessages.length;
      setMessage(progressMessages[messageIndex]);
    }, 4500);

    try {
      const apiBase = import.meta.env.VITE_API_URL || '';
      const response = await fetch(`${apiBase}/api/extract`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Server responded with ${response.status}`);
      }

      // Handle transparent ZIP blob download
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = downloadUrl;

      // Grab filename from header if possible, else fallback
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = 'extracted_site.zip';
      if (contentDisposition && contentDisposition.indexOf('attachment') !== -1) {
        const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
        if (matches != null && matches[1]) {
          filename = matches[1].replace(/['"]/g, '');
        }
      }
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);

      clearInterval(messageInterval);
      setMessage('Extraction Complete! ZIP downloaded.');
      setIsError(false);

    } catch (err) {
      clearInterval(messageInterval);
      setMessage(`Extraction Failed: ${err.message}`);
      setIsError(true);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <ZapIcon />
      <h1>Kopiiki</h1>
      <p className="subtitle">High-fidelity Web Extraction Engine.</p>

      <form onSubmit={handleExtract} className="input-group">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com"
          required
          autoComplete="off"
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !url.trim()}>
          Extract Assets
        </button>
      </form>

      <div className="status-area">
        {isLoading && <div className="spinner"></div>}
        {message && (
          <div className={`message ${isError ? 'error' : ''}`}>
            {message}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
