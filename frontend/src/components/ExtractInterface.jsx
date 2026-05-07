import React, { useState, useEffect, useMemo, useRef } from 'react';
import { KeyReturn, StopCircleIcon } from '@phosphor-icons/react';
import { animate, scrambleText } from 'animejs';

// Spinner ASCII frames for terminal vibe
const spinnerFrames = ['\\', '|', '/', '-'];
const SCAN_CURSOR = '░▒▓█';
const SCAN_LOOP_DELAY_MS = 360;
const extractionModes = [
  {
    id: 'snapshot',
    label: 'Snapshot',
    success: 'SNAPSHOT COMPLETE. ARCHIVE DOWNLOADED.',
  },
  {
    id: 'design',
    label: 'Design',
    success: 'DESIGN CAPSULE COMPLETE. ARCHIVE DOWNLOADED.',
  },
];

const escapeHtml = (value) => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

const getLogLabel = (status) => {
  if (status === 'error') return 'ERR';
  if (status === 'complete') return 'DONE';
  if (status === 'cancelled') return 'STOP';
  return 'OK';
};

const getTerminalErrorMessage = (message = '') => {
  const normalized = message.toLowerCase();
  if (normalized.includes('gemini_api_key')) {
    return 'DESIGN CAPSULE NEEDS GEMINI_API_KEY ON THE BACKEND.';
  }
  if (normalized.includes('gemini') || normalized.includes('quota') || normalized.includes('rate limit')) {
    return 'GEMINI ANALYSIS FAILED. CHECK API KEY, QUOTA, MODEL, AND BACKEND LOGS.';
  }
  if (normalized.includes('playwright') || normalized.includes('design evidence') || normalized.includes('captur')) {
    return 'BROWSER EVIDENCE CAPTURE FAILED. CHECK THE URL AND PLAYWRIGHT SETUP.';
  }
  if (normalized.includes('mode must')) {
    return 'INVALID EXTRACTION MODE.';
  }
  return message ? `ERROR: ${message}` : 'AN ERROR OCCURRED. PLEASE TRY AGAIN.';
};

const usePrefersReducedMotion = () => {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setPrefersReducedMotion(mediaQuery.matches);

    updatePreference();

    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', updatePreference);
      return () => mediaQuery.removeEventListener('change', updatePreference);
    }

    mediaQuery.addListener(updatePreference);
    return () => mediaQuery.removeListener(updatePreference);
  }, []);

  return prefersReducedMotion;
};

// A text disturbance pass that alternates Anime.js' reveal wave from left to right.
const ScanningTextOverlay = ({ text, reducedMotion }) => {
  const overlayRef = useRef(null);
  const [from, setFrom] = useState('left');
  const safeText = useMemo(() => escapeHtml(text || 'Enter URL to extract.'), [text]);

  useEffect(() => {
    const target = overlayRef.current;
    if (!target) return undefined;

    if (reducedMotion) {
      target.innerHTML = safeText;
      return undefined;
    }

    let isMounted = true;
    let loopTimeoutId;
    target.innerHTML = safeText;

    const animation = animate(target, {
      innerHTML: scrambleText({
        cursor: SCAN_CURSOR,
        from,
      }),
      onComplete: () => {
        loopTimeoutId = window.setTimeout(() => {
          if (isMounted) setFrom(current => (current === 'left' ? 'right' : 'left'));
        }, SCAN_LOOP_DELAY_MS);
      },
    });

    return () => {
      isMounted = false;
      window.clearTimeout(loopTimeoutId);
      animation.cancel();
    };
  }, [from, reducedMotion, safeText]);

  return (
    <span
      ref={overlayRef}
      aria-hidden="true"
      className="scramble-input-overlay"
    />
  );
};

const LogPrefix = ({ label, className = 'log-prefix' }) => (
  <span className={className} aria-label={label}>
    <span aria-hidden="true">[</span>
    <span className="log-prefix-label">{label}</span>
    <span aria-hidden="true">]</span>
  </span>
);

// A single active log line that types out and spins
const ActiveLogLine = ({ message, status, isProcessing, reducedMotion }) => {
  const [spinnerIdx, setSpinnerIdx] = useState(0);
  const messageRef = useRef(null);
  const safeMessage = useMemo(() => escapeHtml(message), [message]);

  // Spinner & Hex illusion
  useEffect(() => {
    if (!isProcessing || reducedMotion) {
      setSpinnerIdx(0);
      return undefined;
    }

    let frame = 0;
    const effectInterval = setInterval(() => {
      frame++;
      setSpinnerIdx(frame % spinnerFrames.length);
    }, 100);
    return () => clearInterval(effectInterval);
  }, [isProcessing, reducedMotion]);

  useEffect(() => {
    const target = messageRef.current;
    if (!target) return undefined;

    if (reducedMotion) {
      target.innerHTML = safeMessage;
      return undefined;
    }

    target.innerHTML = '';

    const animation = animate(target, {
      innerHTML: scrambleText({
        text: safeMessage,
        from: 'left',
        override: '',
        revealRate: 88,
        settleDuration: 240,
        settleRate: 34,
        perturbation: 0.25,
      }),
      duration: Math.min(1400, Math.max(420, message.length * 18)),
      ease: 'linear',
    });

    return () => {
      animation.cancel();
    };
  }, [message.length, reducedMotion, safeMessage]);

  const color = status === 'error' ? 'var(--accent)' : 'var(--text-main)';
  const prefix = isProcessing ? spinnerFrames[spinnerIdx] : getLogLabel(status);

  return (
    <div className="log-line active-log" style={{ color }}>
      <LogPrefix label={prefix} className="log-spinner" />
      <span ref={messageRef} className="log-message" />
    </div>
  );
};

// Past completed logs
const StaticLogLine = ({ message, status }) => {
  const color = status === 'error' ? 'var(--accent)' : 'var(--text-muted)';
  const prefix = getLogLabel(status);
  return (
    <div className="log-line" style={{ color }}>
      <LogPrefix label={prefix} />
      <span className="log-message">{message}</span>
    </div>
  );
};

const ModeTabs = ({ mode, onModeChange, disabled }) => {
  return (
    <div className="mode-tabs" role="group" aria-label="Extraction mode">
      {extractionModes.map((item, index) => (
        <React.Fragment key={item.id}>
          {index > 0 && (
            <span className="mode-separator" aria-hidden="true">/</span>
          )}
          <button
            type="button"
            className={`mode-option ${mode === item.id ? 'active' : ''}`}
            aria-pressed={mode === item.id}
            disabled={disabled}
            onClick={() => onModeChange(item.id)}
          >
            <span className="mode-option-text">
              {mode === item.id ? `[${item.label}]` : item.label}
            </span>
          </button>
        </React.Fragment>
      ))}
    </div>
  );
};

const ExtractInterface = ({ mode, resultMode, onModeChange, onExtract, onCancel, isLoading, logs, result, isError, isCancelled }) => {
  const [url, setUrl] = useState('');
  const prefersReducedMotion = usePrefersReducedMotion();
  const showInputScramble = isLoading && !prefersReducedMotion;
  const completedMode = extractionModes.find(item => item.id === resultMode) || extractionModes[0];
  const latestErrorMessage = useMemo(() => {
    const latestError = [...logs].reverse().find(log => log.status === 'error');
    return getTerminalErrorMessage(latestError?.message);
  }, [logs]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!url.trim() || isLoading) return;
    onExtract(url.trim(), mode);
  };

  return (
    <div className="extract-interface">
      <form onSubmit={handleSubmit} className="input-area">
        <div className="input-wrapper">
          <div className="input-content">
            <ModeTabs mode={mode} onModeChange={onModeChange} disabled={isLoading} />
            <div className={`input-resizer ${showInputScramble ? 'processing' : ''}`} data-value={url || "https://example.com"}>
              <input 
                type="text" 
                className="url-input" 
                aria-label="Website URL"
                value={url} 
                onChange={(e) => setUrl(e.target.value)} 
                placeholder="Enter URL to extract." 
                disabled={isLoading}
                autoComplete="off"
                spellCheck="false"
              />
              {isLoading && (
                <ScanningTextOverlay text={url} reducedMotion={prefersReducedMotion} />
              )}
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
        </div>
      </form>

      {/* Fixed height TUI Stream Buffer */}
      <div className={`status-container ${logs.length > 0 ? 'visible' : ''}`}>
        <div className="stream-buffer-view">
          {logs.map((log, index) => {
            // Animate the newest line, including fast failure states where loading ends immediately.
            const isActive = index === logs.length - 1;
            return isActive ? (
              <ActiveLogLine
                key={`${index}-active`}
                message={log.message}
                status={log.status}
                isProcessing={isLoading}
                reducedMotion={prefersReducedMotion}
              />
            ) : (
              <StaticLogLine key={`${index}-static`} message={log.message} status={log.status} />
            );
          })}
          
          {/* Final persistent states after stream closes */}
          {isError && !isLoading && (
             <div className="log-line" style={{ color: 'var(--accent)' }}>
                 <LogPrefix label="ERR" />
                 <span className="log-message">{latestErrorMessage}</span>
             </div>
          )}
          {isCancelled && !isLoading && !isError && (
             <div className="log-line" style={{ color: 'var(--text-muted)' }}>
                 <LogPrefix label="STOP" />
                 <span className="log-message">EXTRACTION CANCELLED. TEMP FILES CLEANED.</span>
             </div>
          )}
          {result && !isLoading && (
             <div className="log-line" style={{ color: 'var(--text-main)', fontWeight: 600 }}>
                 <LogPrefix label="DONE" />
                 <span className="log-message">{completedMode.success}</span>
             </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ExtractInterface;
