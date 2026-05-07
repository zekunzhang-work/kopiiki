import React, { useCallback, useEffect, useState } from 'react';
import './index.css';

import ExtractInterface from './components/ExtractInterface';
import DynamicFooter from './components/DynamicFooter';
import HistoryDrawer from './components/HistoryDrawer';
import ReadmeDrawer from './components/ReadmeDrawer';
import TerminalCursor from './components/TerminalCursor';
import TopNav from './components/TopNav';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5002';

function App() {
  const [mode, setMode] = useState('snapshot');
  const [isLoading, setIsLoading] = useState(false);
  const [isError, setIsError] = useState(false);
  const [isCancelled, setIsCancelled] = useState(false);
  const [logs, setLogs] = useState([]);
  const [result, setResult] = useState(false);
  const [resultMode, setResultMode] = useState('snapshot');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [readmeOpen, setReadmeOpen] = useState(false);
  const [historyRecords, setHistoryRecords] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [backendConfig, setBackendConfig] = useState(null);
  
  // Ref to hold the current EventSource and AbortController for cancellation
  const abortCtrlRef = React.useRef(null);
  const eventSourceRef = React.useRef(null);
  const extractIdRef = React.useRef(null);
  const cancelRequestedRef = React.useRef(false);

  // Helper to append formatting logs
  const appendLog = (msgObj) => {
    setLogs(prev => {
      const newLogs = [...prev, msgObj];
      return newLogs.slice(-200);
    });
  };

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError('');
    try {
      const response = await fetch(`${API_BASE}/api/history`);
      if (!response.ok) {
        throw new Error(`History responded with ${response.status}`);
      }
      const data = await response.json();
      setHistoryRecords(Array.isArray(data.records) ? data.records : []);
    } catch (err) {
      setHistoryError(err.message);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const refreshBackendConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/config`);
      if (!response.ok) {
        throw new Error(`Config responded with ${response.status}`);
      }
      const data = await response.json();
      setBackendConfig(data);
    } catch {
      setBackendConfig(null);
    }
  }, []);

  useEffect(() => {
    refreshHistory();
    refreshBackendConfig();
  }, [refreshHistory, refreshBackendConfig]);

  const handleOpenHistory = () => {
    setHistoryOpen(true);
    refreshHistory();
  };

  const handleDeleteHistoryRecord = async (record) => {
    if (!record?.id) return;
    setHistoryError('');
    try {
      const response = await fetch(`${API_BASE}/api/history/${record.id}`, {
        method: 'DELETE',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || `Delete responded with ${response.status}`);
      }
      await refreshHistory();
    } catch (err) {
      setHistoryError(err.message);
    }
  };

  const handleExtract = async (url, selectedMode = mode) => {
    setIsLoading(true);
    setIsError(false);
    setIsCancelled(false);
    setResult(false);
    setResultMode(selectedMode);
    setLogs([{ status: 'sys', message: `INITIATING ${selectedMode.toUpperCase()} EXTRACTION OF ${url}` }]);
    if (selectedMode === 'design' && backendConfig?.design_ai && !backendConfig.design_ai.configured) {
      appendLog({ status: 'sys', message: 'DESIGN CAPSULE AI IS WAITING FOR GEMINI_API_KEY ON THE BACKEND.' });
    }
    cancelRequestedRef.current = false;
    extractIdRef.current = null;

    // Setup cancellation tokens
    const abortCtrl = new AbortController();
    abortCtrlRef.current = abortCtrl;

    try {
      // 1. Start the extraction job and get an ID
      const startResponse = await fetch(`${API_BASE}/api/extract`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url, mode: selectedMode }),
        signal: abortCtrl.signal,
      });

      if (!startResponse.ok) {
        const errorData = await startResponse.json().catch(() => ({}));
        if (startResponse.status === 409) {
          throw new Error(errorData.error || 'Another extraction is already running.');
        }
        throw new Error(errorData.error || `Server responded with ${startResponse.status}`);
      }
      
      const resData = await startResponse.json();
      const extract_id = resData.extract_id;
      extractIdRef.current = extract_id;
      
      // 2. Connect to the SSE stream using the ID
      const eventSource = new EventSource(`${API_BASE}/api/extract/stream/${extract_id}`);
      eventSourceRef.current = eventSource;
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Append the new log entry
          setLogs(prev => {
            // Avoid duplicate exact messages in a row
            if (prev.length > 0 && prev[prev.length - 1].message === data.message) return prev;
            return [...prev, { status: data.status, message: data.message }].slice(-200);
          });
          
          if (data.status === 'complete') {
            eventSource.close();
            if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
            extractIdRef.current = null;
            setIsLoading(false);
            if (cancelRequestedRef.current) {
              setIsCancelled(true);
              setIsError(false);
              setResult(false);
              appendLog({ status: 'cancelled', message: "EXTRACTION FINISHED BEFORE CANCELLATION TOOK EFFECT." });
              refreshHistory();
              return;
            }
            setResult(true);
            refreshHistory();
            
            // Trigger actual download now that extraction is done
            if (data.download_url) {
                const downloadFullUrl = `${API_BASE}${data.download_url}`;
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
            if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
            extractIdRef.current = null;
            setIsError(true);
            setIsCancelled(false);
            setResult(false);
            setIsLoading(false);
            refreshHistory();
          } else if (data.status === 'cancelled') {
            eventSource.close();
            if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
            extractIdRef.current = null;
            setIsCancelled(true);
            setIsError(false);
            setResult(false);
            setIsLoading(false);
            refreshHistory();
          }
        } catch (err) {
          console.error("Error parsing SSE data", err);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
        if (cancelRequestedRef.current) {
          setIsCancelled(true);
          setIsError(false);
          appendLog({ status: 'cancelled', message: "CANCELLATION REQUESTED. STREAM CLOSED." });
        } else {
          setIsError(true);
          setIsCancelled(false);
          appendLog({ status: 'error', message: "CONNECTION LOST. ABORTED." });
        }
        setIsLoading(false);
      };

    } catch (err) {
      if (err.name === 'AbortError') {
        appendLog({ status: 'cancelled', message: "EXTRACTION ABORTED BEFORE BACKEND STARTED." });
        setIsCancelled(true);
        setIsError(false);
      } else {
        appendLog({ status: 'error', message: `EXCEPTION: ${err.message}` });
        setIsError(true);
        setIsCancelled(false);
      }
      setIsLoading(false);
      refreshBackendConfig();
      refreshHistory();
    }
  };

  const handleCancel = async () => {
    cancelRequestedRef.current = true;
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
    }
    setIsLoading(false);
    setIsError(false);
    setIsCancelled(true);
    setResult(false);
    appendLog({ status: 'cancelled', message: "CANCELLATION REQUESTED. WAITING FOR BACKEND TO STOP." });

    if (extractIdRef.current) {
      try {
        const cancelResponse = await fetch(`${API_BASE}/api/extract/cancel`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ extract_id: extractIdRef.current })
        });
        if (!cancelResponse.ok) {
          const errorData = await cancelResponse.json().catch(() => ({}));
          throw new Error(errorData.message || `Cancel responded with ${cancelResponse.status}`);
        }
        refreshHistory();
      } catch (err) {
        console.error("Cancel failed", err);
        appendLog({ status: 'error', message: `CANCEL REQUEST FAILED: ${err.message}` });
        setIsError(true);
      }
    }
  };

  return (
    <div className="app-container">
      <TopNav onHistoryClick={handleOpenHistory} onReadmeClick={() => setReadmeOpen(true)} />
      <TerminalCursor />
      <h1 className="hero-title">Kopiiki</h1>
      <ExtractInterface 
        mode={mode}
        onModeChange={setMode}
        onExtract={handleExtract} 
        onCancel={handleCancel}
        isLoading={isLoading} 
        logs={logs} 
        result={result} 
        resultMode={resultMode}
        isCancelled={isCancelled}
        isError={isError} 
      />
      <DynamicFooter />
      <HistoryDrawer
        apiBase={API_BASE}
        isOpen={historyOpen}
        records={historyRecords}
        isLoading={historyLoading}
        error={historyError}
        onClose={() => setHistoryOpen(false)}
        onRefresh={refreshHistory}
        onDeleteRecord={handleDeleteHistoryRecord}
      />
      <ReadmeDrawer
        isOpen={readmeOpen}
        onClose={() => setReadmeOpen(false)}
      />
    </div>
  );
}

export default App;
