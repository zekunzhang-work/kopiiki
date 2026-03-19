import React, { useState, useEffect } from 'react';
import { KeyReturn, StopCircleIcon } from '@phosphor-icons/react';

// Spinner ASCII frames for terminal vibe
const spinnerFrames = ['[ \\ ]', '[ | ]', '[ / ]', '[ - ]'];

// A sweeping trail of 8px grid blocks for the input scanning animation
const ScanningTrail = ({ text }) => {
  const [headIndex, setHeadIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [totalCells, setTotalCells] = useState(20);
  const measureRef = React.useRef(null);
  
  useEffect(() => {
    if (measureRef.current) {
        const width = measureRef.current.getBoundingClientRect().width;
        // Each cell is exactly 8px wide. Calculate precise required cell count to cover text width.
        const cells = Math.max(Math.ceil(width / 8), 1);
        setTotalCells(cells);
    }
  }, [text]);

  useEffect(() => {
    const sweepInterval = setInterval(() => {
      setHeadIndex(prev => {
        let next = prev + direction;
        // Add a slight "bounce" logic with boundary checking
        if (next >= totalCells - 1) {
          next = totalCells - 1;
          setDirection(-1);
        } else if (next <= 0) {
          next = 0;
          setDirection(1);
        }
        return next;
      });
    }, 30); // Refined to 30ms for a more visceral, high-speed sweep

    return () => clearInterval(sweepInterval);
  }, [direction, totalCells]);

  return (
    <>
      {/* Hidden layout span to perfectly mirror the input font sizing and measure exact pixel width */}
      <span 
        ref={measureRef} 
        className="url-input" 
        style={{ position: 'absolute', visibility: 'hidden', whiteSpace: 'pre', width: 'auto', padding: 0, margin: 0, border: 'none', pointerEvents: 'none' }}
      >
        {text || "Enter URL to extract."}
      </span>
      <div className="scanning-trail">
        {Array.from({ length: totalCells }).map((_, i) => (
          <div 
            key={i} 
            className={`trail-cell ${i === headIndex ? 'active' : ''}`}
          />
        ))}
      </div>
    </>
  );
};

// A single active log line that types out and spins
const ActiveLogLine = ({ message, status }) => {
  const [displayedText, setDisplayedText] = useState('');
  const [spinnerIdx, setSpinnerIdx] = useState(0);

  // Typewriter effect
  useEffect(() => {
    let i = 0;
    setDisplayedText('');
    const typingInterval = setInterval(() => {
      setDisplayedText(message.slice(0, i + 1));
      i++;
      if (i >= message.length) clearInterval(typingInterval);
    }, 10); // Rapid typing
    return () => clearInterval(typingInterval);
  }, [message]);

  // Spinner & Hex illusion
  useEffect(() => {
    let frame = 0;
    const effectInterval = setInterval(() => {
      frame++;
      setSpinnerIdx(frame % spinnerFrames.length);
    }, 100);
    return () => clearInterval(effectInterval);
  }, []);

  const color = status === 'error' ? 'var(--accent)' : 'var(--text-main)';

  return (
    <div className="log-line active-log" style={{ color }}>
      <span className="log-spinner">{spinnerFrames[spinnerIdx]}</span>
      <span className="log-message">{displayedText}</span>
    </div>
  );
};

// Past completed logs
const StaticLogLine = ({ message, status }) => {
  const color = status === 'error' ? 'var(--accent)' : 'var(--text-muted)';
  const prefix = status === 'error' ? '[ ERR ]' : status === 'complete' ? '[ DONE]' : '[ OK  ]';
  return (
    <div className="log-line" style={{ color }}>
      <span className="log-prefix">{prefix}</span>
      <span className="log-message">{message}</span>
    </div>
  );
};

const ExtractInterface = ({ onExtract, onCancel, isLoading, logs, result, isError }) => {
  const [url, setUrl] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!url.trim() || isLoading) return;
    onExtract(url.trim());
  };

  return (
    <div className="extract-interface">
      <form onSubmit={handleSubmit} className="input-area">
        <label className="input-wrapper">
          <div className="input-content">
            <div className={`input-resizer ${isLoading ? 'processing' : ''}`} data-value={url || "https://example.com"}>
              <input 
                type="text" 
                className="url-input" 
                value={url} 
                onChange={(e) => setUrl(e.target.value)} 
                placeholder="Enter URL to extract." 
                disabled={isLoading}
                autoComplete="off"
                spellCheck="false"
              />
              {isLoading && <ScanningTrail text={url} />}
            </div>
            {url.trim() && !isLoading && (
              <button type="submit" className="enter-hint-btn" title="Press Enter to extract">
                <KeyReturn size="1.2em" weight="fill" />
              </button>
            )}
            {isLoading && (
              <button type="button" onClick={onCancel} className="enter-hint-btn stop-btn" title="Stop extraction">
                <StopCircleIcon size="1.2em" weight="fill" />
              </button>
            )}
          </div>
        </label>
      </form>

      {/* Fixed height TUI Stream Buffer */}
      <div className={`status-container ${logs.length > 0 ? 'visible' : ''}`}>
        <div className="stream-buffer-view">
          {logs.map((log, index) => {
            // Is this the very last log while loading?
            const isActive = index === logs.length - 1 && isLoading;
            return isActive ? (
              <ActiveLogLine key={`${index}-active`} message={log.message} status={log.status} />
            ) : (
              <StaticLogLine key={`${index}-static`} message={log.message} status={log.status} />
            );
          })}
          
          {/* Final persistent states after stream closes */}
          {isError && !isLoading && (
             <div className="log-line" style={{ color: 'var(--accent)' }}>
                 <span className="log-prefix">[ ERR ]</span>
                 <span className="log-message">AN ERROR OCCURRED. PLEASE TRY AGAIN.</span>
             </div>
          )}
          {result && !isLoading && (
             <div className="log-line" style={{ color: 'var(--text-main)', fontWeight: 600 }}>
                 <span className="log-prefix">[ DONE]</span>
                 <span className="log-message">EXTRACTION COMPLETE. ARCHIVE DOWNLOADED.</span>
             </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ExtractInterface;
