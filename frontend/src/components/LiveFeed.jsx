/**
 * LiveFeed — active incidents list, sorted by severity (P0 > P1 > P2).
 * Clean card-based layout with severity indicators and status badges.
 */

import { useState } from 'react';
import './LiveFeed.css';

const SEVERITY_ORDER = { P0: 0, P1: 1, P2: 2 };
const STATUS_ORDER = { OPEN: 0, INVESTIGATING: 1, RESOLVED: 2, CLOSED: 3 };

const SEVERITY_LABELS = { P0: 'Critical', P1: 'High', P2: 'Medium' };

export default function LiveFeed({ incidents, onSelect, selectedId }) {
  const [filter, setFilter] = useState('ALL');

  const filtered = incidents
    .filter(i => {
      if (filter === 'ALL') return true;
      if (filter === 'ACTIVE') return i.status === 'OPEN' || i.status === 'INVESTIGATING';
      return i.status === filter;
    })
    .sort((a, b) => {
      const sevDiff = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9);
      if (sevDiff !== 0) return sevDiff;
      const statusDiff = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9);
      if (statusDiff !== 0) return statusDiff;
      return new Date(b.created_at) - new Date(a.created_at);
    });

  return (
    <div className="livefeed" id="livefeed">
      <div className="livefeed-header">
        <h2 className="livefeed-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          Active Incidents
          <span className="livefeed-count">{filtered.length}</span>
        </h2>
        <div className="livefeed-filters">
          {['ALL', 'ACTIVE', 'OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED'].map(s => (
            <button
              key={s}
              className={`filter-btn ${filter === s ? 'filter-active' : ''}`}
              onClick={() => setFilter(s)}
              id={`filter-${s.toLowerCase()}`}
            >
              {s === 'ALL' ? 'All' : s === 'ACTIVE' ? 'Active' : s.charAt(0) + s.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="livefeed-list">
        {filtered.length === 0 ? (
          <div className="livefeed-empty">
            <div className="livefeed-empty-icon">🌤️</div>
            <h3>All systems operational</h3>
            <p>No incidents match this filter</p>
          </div>
        ) : (
          filtered.map((incident, idx) => (
            <IncidentCard
              key={incident.id}
              incident={incident}
              selected={incident.id === selectedId}
              onClick={() => onSelect(incident)}
              delay={idx * 30}
            />
          ))
        )}
      </div>
    </div>
  );
}

function IncidentCard({ incident, selected, onClick, delay }) {
  const age = getAge(incident.created_at);
  const isActiveP0 = incident.severity === 'P0' && (incident.status === 'OPEN' || incident.status === 'INVESTIGATING');

  return (
    <div
      className={`incident-card severity-${incident.severity.toLowerCase()} ${selected ? 'incident-card-selected' : ''} ${isActiveP0 ? 'p0-active' : ''}`}
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
      id={`incident-${incident.id}`}
    >
      {/* Header: Badges + ID */}
      <div className="card-header">
        <div className="card-badges">
          <span className={`severity-badge severity-${incident.severity.toLowerCase()}-badge`}>
            {SEVERITY_LABELS[incident.severity] || incident.severity}
          </span>
          <span className={`status-badge status-${incident.status.toLowerCase()}`}>
            {incident.status}
          </span>
        </div>
        <span className="card-id">#{incident.id}</span>
      </div>

      {/* Title */}
      <div className="card-title">{incident.title}</div>

      {/* Meta */}
      <div className="card-meta">
        <span className="card-source">{incident.source}</span>
        <span className="meta-dot">●</span>
        <span>{incident.signal_count} signal{incident.signal_count !== 1 ? 's' : ''}</span>
        <span className="meta-dot">●</span>
        <span>Assigned to SRE Team</span>
      </div>

      {/* Footer */}
      <div className="card-footer">
        <span className="card-time">Created {age}</span>
        <button className="card-action-btn" onClick={(e) => { e.stopPropagation(); onClick(); }}>
          View Details →
        </button>
      </div>
    </div>
  );
}

function getAge(dateStr) {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
