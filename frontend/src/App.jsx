import React, { useState, useEffect } from 'react';
import './index.css';

import ExtractInterface from './components/ExtractInterface';
import DynamicFooter from './components/DynamicFooter';
import TerminalCursor from './components/TerminalCursor';
import TopNav from './components/TopNav';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [isError, setIsError] = useState(false);
  const [logs, setLogs] = useState([]);
  const [result, setResult] = useState(false);
  
  // Ref to hold the current EventSource and AbortController for cancellation
  const abortCtrlRef = React.useRef(null);
  const eventSourceRef = React.useRef(null);

  // Helper to append formatting logs
  const appendLog = (msgObj) => {
    setLogs(prev => [...prev, msgObj]);
  };

  const handleExtract = async (url) => {
    setIsLoading(true);
    setIsError(false);
    setResult(false);
    setLogs([{ status: 'sys', message: `INITIATING EXTRACTION OF ${url}` }]);

    // Setup cancellation tokens
    const abortCtrl = new AbortController();
    abortCtrlRef.current = abortCtrl;

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
        signal: abortCtrl.signal,
      });

      if (!startResponse.ok) {
        const errorData = await startResponse.json().catch(() => ({}));
        throw new Error(errorData.error || `Server responded with ${startResponse.status}`);
      }
      
      const { extract_id } = await startResponse.json();
      
      // 2. Connect to the SSE stream using the ID
      const eventSource = new EventSource(`${apiBase}/api/extract/stream/${extract_id}`);
      eventSourceRef.current = eventSource;
      
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
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = downloadFullUrl;
                // EXPLICITLY set the filename attribute to force browser naming
                a.download = data.filename || 'site_extraction.zip';
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
        eventSource.close();
        setIsError(true);
        appendLog({ status: 'error', message: "CONNECTION LOST. ABORTED." });
        setIsLoading(false);
      };

    } catch (err) {
      if (err.name === 'AbortError') {
        appendLog({ status: 'error', message: "EXTRACTION ABORTED BY USER." });
      } else {
        appendLog({ status: 'error', message: `EXCEPTION: ${err.message}` });
      }
      setIsError(true);
      setIsLoading(false);
    }
  };

  const handleCancel = () => {
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    setIsLoading(false);
    setIsError(true); // Treat cancellation as an error state for UI bounds
    appendLog({ status: 'error', message: "EXTRACTION ABORTED BY USER." });
  };

  return (
    <div className="app-container">
      <TopNav />
      <TerminalCursor />
      <h1 className="hero-title">Kopiiki</h1>
      <ExtractInterface 
        onExtract={handleExtract} 
        onCancel={handleCancel}
        isLoading={isLoading} 
        logs={logs} 
        result={result} 
        isError={isError} 
      />
      <DynamicFooter />
    </div>
  );
}

export default App;
