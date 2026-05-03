/**
 * IncidentDetail — right panel showing full incident info, raw signals, and actions.
 */

import { useState, useEffect } from 'react';
import { api } from '../api';
import RCAForm from './RCAForm';
import './IncidentDetail.css';

const TRANSITIONS = {
  OPEN:          'INVESTIGATING',
  INVESTIGATING: 'RESOLVED',
  RESOLVED:      'CLOSED',
};

export default function IncidentDetail({ incident, onUpdate, onClose, userRole }) {
  const canAct = userRole === 'ADMIN' || userRole === 'OPERATOR';
  const [signals, setSignals] = useState([]);
  const [loadingSignals, setLoadingSignals] = useState(false);
  const [rca, setRca] = useState(null);
  const [showRCAForm, setShowRCAForm] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!incident) return;
    loadSignals();
    loadRCA();
    setShowRCAForm(false);
    setError(null);
  }, [incident?.id]);

  async function loadSignals() {
    setLoadingSignals(true);
    try {
      const res = await api.getIncidentSignals(incident.id);
      setSignals(res.signals || []);
    } catch (e) {
      console.error('Failed to load signals:', e);
    }
    setLoadingSignals(false);
  }

  async function loadRCA() {
    try {
      const res = await api.getRCA(incident.id);
      setRca(res);
    } catch (e) {
      setRca(null);
    }
  }

  async function handleTransition() {
    const nextStatus = TRANSITIONS[incident.status];
    if (!nextStatus) return;

    if (nextStatus === 'CLOSED' && !rca) {
      setShowRCAForm(true);
      setError('Submit an RCA before closing this incident.');
      return;
    }

    setTransitioning(true);
    setError(null);
    try {
      await api.transitionIncident(incident.id, nextStatus);
      onUpdate?.();
    } catch (e) {
      setError(e.detail || 'Transition failed');
    }
    setTransitioning(false);
  }

  async function handleRCASubmit(data) {
    try {
      await api.submitRCA(incident.id, data);
      await loadRCA();
      setShowRCAForm(false);
      setError(null);
      onUpdate?.();
    } catch (e) {
      throw e;
    }
  }

  if (!incident) {
    return (
      <div className="detail-panel detail-empty" id="detail-panel">
        <div className="detail-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="48" height="48">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="9" y1="21" x2="9" y2="9" />
          </svg>
          <h3>Select an Incident</h3>
          <p>Click an incident from the feed to view details, raw signals, and manage its lifecycle.</p>
        </div>
      </div>
    );
  }

  const nextStatus = TRANSITIONS[incident.status];
  const mttr = incident.mttr_seconds;

  return (
    <div className="detail-panel" id="detail-panel">
      {/* ── Header ── */}
      <div className="detail-header">
        <div className="detail-header-top">
          <span className={`severity-badge severity-${incident.severity.toLowerCase()}-badge`}>
            {incident.severity}
          </span>
          <span className={`status-badge status-${incident.status.toLowerCase()}`}>
            {incident.status}
          </span>
          <button className="detail-close-btn" onClick={onClose} title="Close panel">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <h2 className="detail-title">{incident.title}</h2>
        <div className="detail-meta-row">
          <MetaItem label="Source" value={incident.source} />
          <MetaItem label="Signals" value={incident.signal_count} />
          <MetaItem label="Created" value={formatDate(incident.created_at)} />
          {mttr != null && (
            <MetaItem label="MTTR" value={formatDuration(mttr)} highlight />
          )}
        </div>
      </div>

      {/* ── Timeline ── */}
      <div className="detail-section">
        <h3 className="section-title">Timeline</h3>
        <div className="timeline">
          <TimelineItem label="Created" time={incident.created_at} active />
          <TimelineItem label="Acknowledged" time={incident.acknowledged_at} />
          <TimelineItem label="Resolved" time={incident.resolved_at} />
          <TimelineItem label="Closed" time={incident.closed_at} />
        </div>
      </div>

      {/* ── Actions ── */}
      {incident.status !== 'CLOSED' && canAct && (
        <div className="detail-section">
          <h3 className="section-title">Actions</h3>
          <div className="action-buttons">
            {nextStatus && (
              <button
                className={`action-btn action-${nextStatus.toLowerCase()}`}
                onClick={handleTransition}
                disabled={transitioning}
                id={`btn-transition-${nextStatus.toLowerCase()}`}
              >
                {transitioning ? 'Processing...' : `Move to ${nextStatus}`}
              </button>
            )}
            {incident.status === 'RESOLVED' && !rca && (
              <button
                className="action-btn action-rca"
                onClick={() => setShowRCAForm(true)}
                id="btn-submit-rca"
              >
                Submit RCA
              </button>
            )}
          </div>
          {error && <div className="detail-error">{typeof error === 'string' ? error : JSON.stringify(error)}</div>}
        </div>
      )}

      {/* ── RCA Form ── */}
      {showRCAForm && !rca && (
        <div className="detail-section">
          <h3 className="section-title">Root Cause Analysis</h3>
          <RCAForm onSubmit={handleRCASubmit} />
        </div>
      )}

      {/* ── RCA Display ── */}
      {rca && (
        <div className="detail-section">
          <h3 className="section-title">Root Cause Analysis</h3>
          <div className="rca-display">
            <RCAField label="Root Cause" value={rca.root_cause} />
            <RCAField label="Impact" value={rca.impact} />
            <RCAField label="Resolution" value={rca.resolution} />
            <RCAField label="Prevention" value={rca.prevention} />
            <div className="rca-dates">
              <RCAField label="Incident Start" value={formatDate(rca.incident_start)} />
              <RCAField label="Incident End" value={formatDate(rca.incident_end)} />
              <RCAField label="Author" value={rca.created_by} />
            </div>
          </div>
        </div>
      )}

      {/* ── Raw Signals ── */}
      <div className="detail-section">
        <h3 className="section-title">
          Raw Signals
          <span className="signal-count-badge">{signals.length}</span>
        </h3>
        {loadingSignals ? (
          <div className="signals-loading">Loading signals from MongoDB...</div>
        ) : signals.length === 0 ? (
          <div className="signals-empty">No raw signals found</div>
        ) : (
          <div className="signals-list">
            {signals.slice(0, 20).map((sig, idx) => (
              <div key={sig.signal_id || idx} className="signal-item">
                <div className="signal-header">
                  <span className="signal-id">{sig.signal_id?.slice(0, 8)}...</span>
                  <span className="signal-time">{formatDate(sig.timestamp)}</span>
                </div>
                <div className="signal-desc">{sig.description || 'No description'}</div>
              </div>
            ))}
            {signals.length > 20 && (
              <div className="signals-more">+ {signals.length - 20} more signals</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MetaItem({ label, value, highlight }) {
  return (
    <div className={`meta-item ${highlight ? 'meta-highlight' : ''}`}>
      <span className="meta-label">{label}</span>
      <span className="meta-value">{value}</span>
    </div>
  );
}

function TimelineItem({ label, time, active }) {
  const done = !!time;
  return (
    <div className={`timeline-item ${done ? 'timeline-done' : ''} ${active && done ? 'timeline-active' : ''}`}>
      <div className="timeline-dot"></div>
      <div className="timeline-content">
        <span className="timeline-label">{label}</span>
        {done && <span className="timeline-time">{formatDate(time)}</span>}
      </div>
    </div>
  );
}

function RCAField({ label, value }) {
  return (
    <div className="rca-field">
      <span className="rca-label">{label}</span>
      <span className="rca-value">{value}</span>
    </div>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  return d.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function formatDuration(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${(seconds / 3600).toFixed(1)}h`;
}
