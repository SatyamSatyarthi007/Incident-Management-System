/**
 * Sidebar — left navigation panel with branding, nav items, key metrics, and health indicators.
 * Shows "User Management" nav item only for ADMIN users.
 */

import { useAuth } from '../context/AuthContext';
import './Sidebar.css';

export default function Sidebar({ incidents, health, activeView, onViewChange }) {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const open = incidents.filter(i => i.status === 'OPEN').length;
  const investigating = incidents.filter(i => i.status === 'INVESTIGATING').length;
  const resolved = incidents.filter(i => i.status === 'RESOLVED').length;
  const activeCount = open + investigating;

  return (
    <aside className="sidebar" id="sidebar">
      {/* ── Brand ── */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-row">
          <div className="sidebar-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
          <div>
            <div className="sidebar-title">IMS</div>
            <div className="sidebar-subtitle">Incident Management</div>
          </div>
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav className="sidebar-nav">
        <button
          className={`nav-item ${activeView === 'dashboard' ? 'active' : ''}`}
          onClick={() => onViewChange('dashboard')}
          id="nav-dashboard"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
          Dashboard
          {activeCount > 0 && <span className="nav-badge">{activeCount}</span>}
        </button>

        <button
          className={`nav-item ${activeView === 'incidents' ? 'active' : ''}`}
          onClick={() => onViewChange('incidents')}
          id="nav-incidents"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          All Incidents
        </button>

        <button
          className={`nav-item ${activeView === 'signals' ? 'active' : ''}`}
          onClick={() => onViewChange('signals')}
          id="nav-signals"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
          Signals
        </button>

        {/* Admin-only nav item */}
        {isAdmin && (
          <>
            <div className="nav-divider" />
            <button
              className={`nav-item nav-admin ${activeView === 'admin' ? 'active' : ''}`}
              onClick={() => onViewChange('admin')}
              id="nav-admin"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              User Management
              <span className="nav-admin-badge">Admin</span>
            </button>
          </>
        )}
      </nav>

      {/* ── Key Metrics ── */}
      <div className="sidebar-metrics">
        <MetricBox label="Active" value={open} color="#dc2626" bgColor="#fef2f2" />
        <MetricBox label="Investigating" value={investigating} color="#d97706" bgColor="#fffbeb" />
        <MetricBox label="Resolved" value={resolved} color="#16a34a" bgColor="#dcfce7" />
      </div>

      {/* ── Health Indicators ── */}
      {health && (
        <div className="sidebar-health">
          <HealthDot label="PG" up={health.postgres === 'up'} />
          <HealthDot label="Mongo" up={health.mongodb === 'up'} />
          <HealthDot label="Redis" up={health.redis === 'up'} />
        </div>
      )}
    </aside>
  );
}

function MetricBox({ label, value, color, bgColor }) {
  return (
    <div className="metric-box">
      <div className="metric-info">
        <span className="metric-label">{label}</span>
        <span className="metric-value" style={{ color }}>{value}</span>
      </div>
      <div className="metric-icon" style={{ background: bgColor, color }}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
        </svg>
      </div>
    </div>
  );
}

function HealthDot({ label, up }) {
  return (
    <div className={`health-dot ${up ? 'health-up' : 'health-down'}`} title={`${label}: ${up ? 'UP' : 'DOWN'}`}>
      <span className="health-indicator"></span>
      <span>{label}</span>
    </div>
  );
}
