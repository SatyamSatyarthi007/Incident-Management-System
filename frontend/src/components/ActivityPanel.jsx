/**
 * ActivityPanel — right sidebar showing on-call schedule, recent activity, and summary stats.
 * Displayed when no incident is selected.
 */

import './ActivityPanel.css';

export default function ActivityPanel({ incidents }) {
  const p0Active = incidents.filter(i => i.severity === 'P0' && i.status !== 'CLOSED').length;
  const totalSignals = incidents.reduce((sum, i) => sum + (i.signal_count || 0), 0);

  const closedWithMTTR = incidents.filter(i => i.mttr_seconds != null);
  const avgMTTR = closedWithMTTR.length > 0
    ? closedWithMTTR.reduce((sum, i) => sum + i.mttr_seconds, 0) / closedWithMTTR.length
    : null;

  // Build recent activity from incidents
  const recentActivity = buildRecentActivity(incidents);

  return (
    <div className="activity-panel" id="activity-panel">
      {/* ── Stats Summary ── */}
      <h3 className="panel-section-title">Overview</h3>
      <div className="stats-summary">
        <div className="summary-stat">
          <div className="summary-value summary-val-p0">{p0Active}</div>
          <div className="summary-label">Active P0</div>
        </div>
        <div className="summary-stat">
          <div className="summary-value summary-val-signals">{totalSignals}</div>
          <div className="summary-label">Signals</div>
        </div>
        <div className="summary-stat">
          <div className="summary-value summary-val-total">{incidents.length}</div>
          <div className="summary-label">Total</div>
        </div>
        <div className="summary-stat">
          <div className="summary-value summary-val-mttr">
            {avgMTTR != null ? formatDuration(avgMTTR) : '--'}
          </div>
          <div className="summary-label">Avg MTTR</div>
        </div>
      </div>

      <div className="divider"></div>

      {/* ── On-Call Schedule ── */}
      <h3 className="panel-section-title">On-Call Schedule</h3>
      <div className="on-call-list">
        <div className="on-call-card">
          <div className="on-call-header">
            <span className="on-call-status online"></span>
            <span className="on-call-name">SRE Team Lead</span>
          </div>
          <div className="on-call-role">Primary On-Call</div>
        </div>
        <div className="on-call-card">
          <div className="on-call-header">
            <span className="on-call-status standby"></span>
            <span className="on-call-name">Platform Engineer</span>
          </div>
          <div className="on-call-role">Secondary On-Call</div>
        </div>
      </div>

      <div className="divider"></div>

      {/* ── Recent Activity ── */}
      <h3 className="panel-section-title">Recent Activity</h3>
      <div className="activity-list">
        {recentActivity.length === 0 ? (
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No recent activity</p>
        ) : (
          recentActivity.map((act, idx) => (
            <div key={idx} className={`activity-item activity-${act.status.toLowerCase()}`}>
              <div className="activity-action">{act.action}</div>
              <div className="activity-desc">{act.title}</div>
              <div className="activity-time">{act.time}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function buildRecentActivity(incidents) {
  const activities = [];

  incidents.forEach(incident => {
    if (incident.closed_at) {
      activities.push({
        action: 'Incident closed',
        title: incident.title,
        time: getAge(incident.closed_at),
        status: 'CLOSED',
        sortDate: new Date(incident.closed_at),
      });
    }
    if (incident.resolved_at) {
      activities.push({
        action: 'Incident resolved',
        title: incident.title,
        time: getAge(incident.resolved_at),
        status: 'RESOLVED',
        sortDate: new Date(incident.resolved_at),
      });
    }
    if (incident.acknowledged_at) {
      activities.push({
        action: 'Investigation started',
        title: incident.title,
        time: getAge(incident.acknowledged_at),
        status: 'INVESTIGATING',
        sortDate: new Date(incident.acknowledged_at),
      });
    }
    activities.push({
      action: `${incident.severity} incident created`,
      title: incident.title,
      time: getAge(incident.created_at),
      status: 'OPEN',
      sortDate: new Date(incident.created_at),
    });
  });

  return activities
    .sort((a, b) => b.sortDate - a.sortDate)
    .slice(0, 8);
}

function getAge(dateStr) {
  if (!dateStr) return '';
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatDuration(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}
