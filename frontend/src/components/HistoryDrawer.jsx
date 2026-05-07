import React, { useMemo, useState } from 'react';
import {
  Archive,
  ArrowClockwise,
  CopySimple,
  DownloadSimple,
  Trash,
  X,
} from '@phosphor-icons/react';

const filters = [
  { id: 'all', label: 'ALL' },
  { id: 'archives', label: 'ARCHIVES' },
  { id: 'deleted', label: 'DELETED' },
];

const statusLabel = {
  complete: 'DONE',
  cancelled: 'STOP',
  error: 'ERR',
  interrupted: 'LOST',
  processing: 'RUN',
};

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (value) => {
  if (!value) return 'PENDING';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('en-US', {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).toUpperCase();
};

const HistoryDrawer = ({
  apiBase,
  isOpen,
  records,
  isLoading,
  error,
  onClose,
  onRefresh,
  onDeleteRecord,
}) => {
  const [filter, setFilter] = useState('archives');
  const [copiedId, setCopiedId] = useState(null);

  const visibleRecords = useMemo(() => {
    if (filter === 'archives') {
      return records.filter(record => record.artifact_status === 'available');
    }
    if (filter === 'deleted') {
      return records.filter(record => record.artifact_status === 'deleted');
    }
    return records;
  }, [filter, records]);

  const copyPath = async (record) => {
    if (!record.relative_path) return;
    await navigator.clipboard.writeText(record.relative_path);
    setCopiedId(record.id);
    window.setTimeout(() => setCopiedId(current => (current === record.id ? null : current)), 1200);
  };

  return (
    <div className={`history-shell ${isOpen ? 'open' : ''}`} aria-hidden={!isOpen}>
      <button className="history-backdrop" type="button" onClick={onClose} tabIndex={isOpen ? 0 : -1} />
      <aside className="history-panel" aria-label="Extraction history">
        <div className="history-header">
          <div className="history-title-block">
            <Archive size={18} weight="bold" />
            <span>HISTORY</span>
          </div>
          <div className="history-header-actions">
            <button className="history-icon-btn" type="button" onClick={onRefresh} title="Refresh history">
              <ArrowClockwise size={16} weight="bold" />
            </button>
            <button className="history-icon-btn" type="button" onClick={onClose} title="Close history">
              <X size={16} weight="bold" />
            </button>
          </div>
        </div>

        <div className="history-tabs" role="tablist" aria-label="History filter">
          {filters.map(item => (
            <button
              key={item.id}
              className={`history-tab ${filter === item.id ? 'active' : ''}`}
              type="button"
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="history-meta">
          <span>{visibleRecords.length} RECORDS</span>
          {isLoading && <span>SYNCING</span>}
        </div>

        {error && (
          <div className="history-error">
            {error}
          </div>
        )}

        <div className="history-list">
          {!isLoading && visibleRecords.length === 0 && (
            <div className="history-empty">
              NO MATCHING RECORDS.
            </div>
          )}

          {visibleRecords.map(record => {
            const canDownload = record.exists && record.download_url;
            const canDelete = record.artifact_status === 'available' && record.exists;
            const status = statusLabel[record.status] || record.status || 'LOG';
            const mode = record.mode === 'design' ? 'DESIGN' : 'SNAPSHOT';
            return (
              <article className={`history-row ${record.artifact_status}`} key={record.id}>
                <div className="history-row-main">
                  <div className="history-row-topline">
                    <span className="history-domain">{record.domain || 'UNKNOWN DOMAIN'}</span>
                    <span className={`history-mode ${record.mode === 'design' ? 'design' : 'snapshot'}`}>{mode}</span>
                    <span className="history-status">[{status}]</span>
                  </div>
                  <div className="history-url">{record.url}</div>
                  <div className="history-path">
                    {record.relative_path || record.message || 'NO ARTIFACT'}
                  </div>
                </div>

                <div className="history-row-footer">
                  <span>{formatDate(record.completed_at || record.created_at)}</span>
                  <span>{formatBytes(record.size_bytes)}</span>
                  <span>{record.artifact_status?.toUpperCase() || 'NONE'}</span>
                </div>

                <div className="history-actions" aria-label={`Actions for ${record.domain || record.id}`}>
                  {canDownload ? (
                    <a
                      className="history-icon-btn"
                      href={`${apiBase}${record.download_url}`}
                      download={record.filename}
                      title="Download archive"
                    >
                      <DownloadSimple size={16} weight="bold" />
                    </a>
                  ) : (
                    <span className="history-icon-btn disabled" title="No archive">
                      <DownloadSimple size={16} weight="bold" />
                    </span>
                  )}
                  <button
                    className="history-icon-btn"
                    type="button"
                    onClick={() => copyPath(record)}
                    disabled={!record.relative_path}
                    title={copiedId === record.id ? 'Copied' : 'Copy relative path'}
                  >
                    <CopySimple size={16} weight="bold" />
                  </button>
                  <button
                    className="history-icon-btn danger"
                    type="button"
                    onClick={() => onDeleteRecord(record)}
                    disabled={!canDelete}
                    title="Delete archive"
                  >
                    <Trash size={16} weight="bold" />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </aside>
    </div>
  );
};

export default HistoryDrawer;
