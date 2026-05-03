/**
 * API helper — talks to the FastAPI backend via the Vite proxy.
 * Includes auth, admin, and automatic Bearer token injection.
 */

const BASE = '/api';

function getToken() {
  return localStorage.getItem('ims_token');
}

async function request(method, path, body = null, customToken = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };

  // Attach auth token if available
  const token = customToken || getToken();
  if (token) {
    opts.headers['Authorization'] = `Bearer ${token}`;
  }

  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, opts);

  // Handle 204 No Content (e.g. delete)
  if (res.status === 204) return null;

  const data = await res.json();
  if (!res.ok) throw { status: res.status, detail: data.detail || data };
  return data;
}

export const api = {
  // Auth
  signup: (data) => request('POST', '/auth/signup', data),
  login:  (data) => request('POST', '/auth/login', data),
  getMe:  (token) => request('GET', '/auth/me', null, token),

  // Health
  health: () => request('GET', '/health'),

  // Incidents
  listIncidents:     () => request('GET', '/incidents'),
  getIncident:       (id) => request('GET', `/incidents/${id}`),
  getIncidentSignals:(id) => request('GET', `/incidents/${id}/signals`),
  transitionIncident:(id, targetStatus) =>
    request('PATCH', `/incidents/${id}/transition`, { target_status: targetStatus }),

  // RCA
  getRCA:    (id) => request('GET', `/incidents/${id}/rca`),
  submitRCA: (id, data) => request('POST', `/incidents/${id}/rca`, data),

  // Ingest (for testing)
  ingestSignal: (signal) => request('POST', '/ingest', signal),

  // Admin — User Management
  listUsers:       () => request('GET', '/admin/users'),
  updateUserRole:  (id, role) => request('PATCH', `/admin/users/${id}/role`, { role }),
  updateUserStatus:(id, isActive) => request('PATCH', `/admin/users/${id}/status`, { is_active: isActive }),
  deleteUser:      (id) => request('DELETE', `/admin/users/${id}`),
};
