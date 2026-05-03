/**
 * Header — top bar with title, WebSocket status, theme toggle, user profile, and create incident button.
 */

import './Header.css';

export default function Header({ connected, onCreateClick, isDark, onToggleTheme, user, onLogout }) {
  const canCreate = user?.role === 'ADMIN' || user?.role === 'OPERATOR';
  return (
    <header className="header" id="header">
      <div className="header-left">
        <h1 className="header-title">Incident Management</h1>
        <p className="header-subtitle">Real-time incident tracking and response</p>
      </div>

      <div className="header-right">
        <div className={`ws-status ${connected ? 'ws-connected' : 'ws-disconnected'}`}>
          <span className="ws-dot"></span>
          <span>{connected ? 'Live' : 'Offline'}</span>
        </div>

        {/* Theme Toggle */}
        <button
          className="theme-toggle"
          onClick={onToggleTheme}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          id="theme-toggle-btn"
          aria-label="Toggle theme"
        >
          {isDark ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>

        {canCreate && (
          <button className="create-btn" onClick={onCreateClick} id="create-incident-btn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Create Incident</span>
          </button>
        )}

        {/* User Profile & Logout */}
        {user && (
          <div className="user-profile" id="user-profile">
            <div className="user-avatar">
              {user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
            </div>
            <div className="user-info">
              <span className="user-name">{user.full_name}</span>
              <span className="user-designation">{user.role} · {user.designation}</span>
            </div>
            <button className="logout-btn" onClick={onLogout} title="Sign out" id="logout-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
