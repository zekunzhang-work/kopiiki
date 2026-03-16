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
    setMessage("Connecting to engine...");

    try {
      const apiBase = import.meta.env.VITE_API_URL || '';
      // 1. Start the extraction job and get an ID
      const startResponse = await fetch(`${apiBase}/api/extract`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      if (!startResponse.ok) {
        const errorData = await startResponse.json().catch(() => ({}));
        throw new Error(errorData.error || `Server responded with ${startResponse.status}`);
      }
      
      const { extract_id } = await startResponse.json();
      
      // 2. Connect to the SSE stream using the ID
      const eventSource = new EventSource(`${apiBase}/api/extract/stream/${extract_id}`);
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMessage(data.message);
          
          if (data.status === 'complete') {
            eventSource.close();
            setIsLoading(false);
            
            // Trigger actual download now that extraction is done
            if (data.download_url) {
                const downloadFullUrl = `${apiBase}${data.download_url}`;
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = downloadFullUrl;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }
          } else if (data.status === 'error') {
            eventSource.close();
            setIsError(true);
            setIsLoading(false);
          }
        } catch (err) {
          console.error("Error parsing SSE data", err);
        }
      };

      eventSource.onerror = () => {
        // SSE error (e.g., connection drop)
        eventSource.close();
        setIsError(true);
        setMessage("Connection to server lost. Extraction may have failed.");
        setIsLoading(false);
      };

    } catch (err) {
      setMessage(`Failed to start: ${err.message}`);
      setIsError(true);
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
