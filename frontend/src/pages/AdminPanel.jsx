/**
 * AdminPanel — Jenkins-style user management page.
 * Admin can list users, change roles, enable/disable accounts, and delete users.
 */

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import './AdminPanel.css';

const ROLES = ['ADMIN', 'OPERATOR', 'VIEWER'];

const ROLE_LABELS = {
  ADMIN: { label: 'Admin', desc: 'Full access — manage users, incidents, RCA' },
  OPERATOR: { label: 'Operator', desc: 'Create incidents, transition, submit RCA' },
  VIEWER: { label: 'Viewer', desc: 'Read-only — view dashboard and incidents' },
};

const ROLE_COLORS = {
  ADMIN: 'role-admin',
  OPERATOR: 'role-operator',
  VIEWER: 'role-viewer',
};

export default function AdminPanel() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionMsg, setActionMsg] = useState(null);

  const fetchUsers = useCallback(async () => {
    try {
      const data = await api.listUsers();
      setUsers(data);
      setError(null);
    } catch (err) {
      setError(err.detail || 'Failed to load users');
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // Clear action messages after 3s
  useEffect(() => {
    if (actionMsg) {
      const t = setTimeout(() => setActionMsg(null), 3000);
      return () => clearTimeout(t);
    }
  }, [actionMsg]);

  async function handleRoleChange(userId, newRole) {
    try {
      await api.updateUserRole(userId, newRole);
      setActionMsg(`Role updated to ${newRole}`);
      fetchUsers();
    } catch (err) {
      setError(err.detail || 'Failed to update role');
    }
  }

  async function handleToggleStatus(userId, currentStatus) {
    try {
      await api.updateUserStatus(userId, !currentStatus);
      setActionMsg(currentStatus ? 'User disabled' : 'User enabled');
      fetchUsers();
    } catch (err) {
      setError(err.detail || 'Failed to update status');
    }
  }

  async function handleDelete(userId, userName) {
    if (!window.confirm(`Are you sure you want to permanently delete ${userName}?`)) return;
    try {
      await api.deleteUser(userId);
      setActionMsg(`${userName} deleted`);
      fetchUsers();
    } catch (err) {
      setError(err.detail || 'Failed to delete user');
    }
  }

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="loader-spinner"></div>
        <span>Loading users...</span>
      </div>
    );
  }

  return (
    <div className="admin-panel" id="admin-panel">
      {/* Header */}
      <div className="admin-header">
        <div>
          <h2 className="admin-title">User Management</h2>
          <p className="admin-subtitle">
            Manage user roles and permissions — {users.length} user{users.length !== 1 ? 's' : ''} registered
          </p>
        </div>
      </div>

      {/* Permission Matrix */}
      <div className="permission-matrix">
        <h3 className="matrix-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
          </svg>
          Permission Matrix
        </h3>
        <div className="matrix-grid">
          <div className="matrix-header">
            <span>Permission</span>
            <span>Admin</span>
            <span>Operator</span>
            <span>Viewer</span>
          </div>
          {[
            ['View Dashboard', true, true, true],
            ['View Incidents', true, true, true],
            ['Create Incidents', true, true, false],
            ['Transition States', true, true, false],
            ['Submit RCA', true, true, false],
            ['Manage Users', true, false, false],
            ['Change Roles', true, false, false],
            ['Delete Users', true, false, false],
          ].map(([perm, admin, op, viewer]) => (
            <div className="matrix-row" key={perm}>
              <span className="matrix-perm">{perm}</span>
              <span>{admin ? '✅' : '—'}</span>
              <span>{op ? '✅' : '—'}</span>
              <span>{viewer ? '✅' : '—'}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Messages */}
      {error && <div className="admin-error">{error}</div>}
      {actionMsg && <div className="admin-success">{actionMsg}</div>}

      {/* User Table */}
      <div className="users-table-wrapper">
        <table className="users-table" id="users-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Email</th>
              <th>Designation</th>
              <th>Role</th>
              <th>Status</th>
              <th>Joined</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => {
              const isSelf = u.id === currentUser?.id;
              return (
                <tr key={u.id} className={!u.is_active ? 'user-disabled' : ''}>
                  <td>
                    <div className="user-cell">
                      <div className={`user-avatar-sm ${ROLE_COLORS[u.role]}`}>
                        {u.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
                      </div>
                      <span className="user-cell-name">
                        {u.full_name}
                        {isSelf && <span className="you-badge">You</span>}
                      </span>
                    </div>
                  </td>
                  <td className="user-email">{u.email}</td>
                  <td className="user-desg">{u.designation}</td>
                  <td>
                    <select
                      className={`role-select ${ROLE_COLORS[u.role]}`}
                      value={u.role}
                      onChange={e => handleRoleChange(u.id, e.target.value)}
                      disabled={isSelf}
                      title={isSelf ? 'Cannot change your own role' : `Change role for ${u.full_name}`}
                    >
                      {ROLES.map(r => (
                        <option key={r} value={r}>{ROLE_LABELS[r].label}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <span className={`status-pill ${u.is_active ? 'status-active' : 'status-inactive'}`}>
                      {u.is_active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td className="user-date">
                    {new Date(u.created_at).toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', year: 'numeric'
                    })}
                  </td>
                  <td>
                    <div className="action-btns">
                      <button
                        className={`action-btn ${u.is_active ? 'btn-disable' : 'btn-enable'}`}
                        onClick={() => handleToggleStatus(u.id, u.is_active)}
                        disabled={isSelf}
                        title={isSelf ? 'Cannot disable yourself' : u.is_active ? 'Disable user' : 'Enable user'}
                      >
                        {u.is_active ? (
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" /><line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                          </svg>
                        ) : (
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                            <polyline points="22 4 12 14.01 9 11.01" />
                          </svg>
                        )}
                      </button>
                      <button
                        className="action-btn btn-delete"
                        onClick={() => handleDelete(u.id, u.full_name)}
                        disabled={isSelf}
                        title={isSelf ? 'Cannot delete yourself' : 'Delete user permanently'}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
