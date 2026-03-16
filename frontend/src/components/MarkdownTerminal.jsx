import { useState, useRef, useEffect } from 'react';

export default function MarkdownTerminal({ onExtract, isLoading, logs, result, isError }) {
  const [url, setUrl] = useState('');
  const inputRef = useRef(null);

  // Auto focus to keep the terminal feel
  useEffect(() => {
    if (!isLoading && !result) {
      inputRef.current?.focus();
    }
  }, [isLoading, result]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (url.trim() && !isLoading) {
      onExtract(url);
    }
  };

  return (
    <div className="markdown-terminal">
      {/* State 1: Input / Idle */}
      {!isLoading && !result && (
        <form onSubmit={handleSubmit} className="input-group" onClick={() => inputRef.current?.focus()}>
          <div className="ascii-input-wrapper">
            <span>{`[ URL_ `}</span>
            <input
              ref={inputRef}
              className="ascii-input"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              required
              autoComplete="off"
            />
            <span>{` ]`}</span>
          </div>
          
          <button type="submit" className="ascii-btn" disabled={!url.trim()}>
            {`=== EXTRACT ===`}
          </button>
        </form>
      )}

      {/* State 2 & 3: Processing & Error/Success Logs */}
      {(isLoading || result || isError) && (
        <div className="progress-log">
          {logs.map((log, i) => (
            <div key={i} className="log-line">
              <span className="log-prefix">{`>`}</span>
              <span className="log-msg">{log.message}</span>
              <span className={`log-status ${log.status}`}>
                {`[${log.status.toUpperCase()}]`}
              </span>
            </div>
          ))}
          {isLoading && (
            <div className="log-line">
              <span className="log-prefix">{`>`}</span>
              <span className="log-msg" style={{animation: 'blink 1s step-end infinite'}}>_</span>
            </div>
          )}
        </div>
      )}

      {/* State 3: Success Screen */}
      {result && !isLoading && !isError && (
        <div className="success-view">
          <pre>
{`
    \\||||/
   ( O  O )
====oOO==(__)==OOo====
 EXTRACTION COMPLETE
======================
`}          
          </pre>
          <div>
             <span>{`> Archiving to `}</span>
             <span style={{color: 'var(--ink-accent)', fontWeight: 'bold'}}>{`[ Local System ]`}</span>
          </div>
          <button className="ascii-btn" style={{marginTop: '2rem'}} onClick={() => window.location.reload()}>
            {`< NEW EXTRACTION >`}
          </button>
        </div>
      )}

      {/* State 4: Error Restarter */}
      {isError && !isLoading && (
        <div className="success-view" style={{marginTop: '2rem'}}>
          <button className="ascii-btn" onClick={() => window.location.reload()}>
            {`< SYSTEM REBOOT >`}
          </button>
        </div>
      )}
    </div>
  );
}
