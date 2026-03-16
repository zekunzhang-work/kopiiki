import { useState } from 'react';
import './index.css';

import AsciiTitle from './components/AsciiTitle';
import ScanlineOverlay from './components/ScanlineOverlay';
import MarkdownTerminal from './components/MarkdownTerminal';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [isError, setIsError] = useState(false);
  const [logs, setLogs] = useState([]);
  const [result, setResult] = useState(false);

  // Helper to append formatting logs
  const appendLog = (msgObj) => {
    setLogs(prev => [...prev, msgObj]);
  };

  const handleExtract = async (url) => {
    setIsLoading(true);
    setIsError(false);
    setResult(false);
    setLogs([{ status: 'sys', message: `INITIATING CONNECTION TO ${url}...` }]);

    try {
      // In dev mode, default to localhost:5002 if no env is set
      const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:5002';
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
          
          // Append the new log entry
          setLogs(prev => {
            // Avoid duplicate exact messages in a row
            if (prev.length > 0 && prev[prev.length - 1].message === data.message) return prev;
            return [...prev, { status: data.status, message: data.message }];
          });
          
          if (data.status === 'complete') {
            eventSource.close();
            setIsLoading(false);
            setResult(true);
            
            // Trigger actual download now that extraction is done
            if (data.download_url) {
                const downloadFullUrl = `${apiBase}${data.download_url}`;
                
                // Fetch as blob to strictly enforce the filename on cross-origin requests
                appendLog({ status: 'sys', message: `DOWNLOADING ARTIFACT TO LOCAL FS...` });
                
                fetch(downloadFullUrl)
                  .then(res => res.blob())
                  .then(blob => {
                    const blobUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = blobUrl;
                    // Extract safe_domain from data.download_url (e.g. /api/download/react.dev)
                    const fileName = data.download_url.split('/').pop() + '.zip';
                    a.download = fileName;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(blobUrl);
                    appendLog({ status: 'complete', message: `DOWNLOAD SECURED: ${fileName}` });
                  })
                  .catch(err => {
                    appendLog({ status: 'error', message: `DOWNLOAD FAILED: ${err.message}` });
                  });
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
        eventSource.close();
        setIsError(true);
        appendLog({ status: 'error', message: "CONNECTION TO SERVER LOST. ABORTING." });
        setIsLoading(false);
      };

    } catch (err) {
      appendLog({ status: 'error', message: `FATAL EXCEPTION: ${err.message}` });
      setIsError(true);
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <ScanlineOverlay active={isLoading} />
      <AsciiTitle />
      <MarkdownTerminal 
        onExtract={handleExtract} 
        isLoading={isLoading} 
        logs={logs} 
        result={result} 
        isError={isError} 
      />
    </div>
  );
}

export default App;
