/**
 * App — Routes: Login, Signup, Dashboard (protected).
 * Dashboard layout: Header, 3-column dashboard.
 * WebSocket auto-refreshes the incident list on real-time updates.
 */

import { useState, useEffect, useCallback } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import { api } from './api';
import { useWebSocket } from './hooks/useWebSocket';
import { useTheme } from './hooks/useTheme';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import LiveFeed from './components/LiveFeed';
import IncidentDetail from './components/IncidentDetail';
import ActivityPanel from './components/ActivityPanel';
import CreateIncidentModal from './components/CreateIncidentModal';
import AdminPanel from './pages/AdminPanel';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import './App.css';

// ── Protected wrapper — redirects to /login if not authenticated ─────────

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="initial-loader">
        <div className="loader-spinner"></div>
        <span>Loading...</span>
      </div>
    );
  }
  return user ? children : <Navigate to="/login" replace />;
}

// ── Dashboard (the main authenticated view) ──────────────────────────────

function Dashboard() {
  const { user, logout } = useAuth();
  const [incidents, setIncidents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState('dashboard');
  const [showCreateModal, setShowCreateModal] = useState(false);

  // ── Theme ──────────────────────────────────────────────────────────────
  const { isDark, toggleTheme } = useTheme();

  // ── Data fetching ──────────────────────────────────────────────────────
  const fetchIncidents = useCallback(async () => {
    try {
      const data = await api.listIncidents();
      setIncidents(data);
      if (selected) {
        const updated = data.find(i => i.id === selected.id);
        if (updated) setSelected(updated);
      }
    } catch (e) {
      console.error('Failed to fetch incidents:', e);
    }
    setLoading(false);
  }, [selected?.id]);

  const fetchHealth = useCallback(async () => {
    try {
      const data = await api.health();
      setHealth(data);
    } catch (e) {
      console.error('Failed to fetch health:', e);
    }
  }, []);

  // ── Initial load ───────────────────────────────────────────────────────
  useEffect(() => {
    fetchIncidents();
    fetchHealth();
    const interval = setInterval(() => {
      fetchIncidents();
      fetchHealth();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // ── WebSocket — live updates ───────────────────────────────────────────
  const handleWsMessage = useCallback((data) => {
    console.log('[WS] Received:', data);
    fetchIncidents();
  }, [fetchIncidents]);

  const { connected } = useWebSocket(handleWsMessage);

  // ── Handlers ───────────────────────────────────────────────────────────
  function handleSelectIncident(incident) { setSelected(incident); }
  function handleCloseDetail() { setSelected(null); }
  function handleIncidentUpdate() { fetchIncidents(); }

  return (
    <div className="app" id="app">
      <Header
        connected={connected}
        onCreateClick={() => setShowCreateModal(true)}
        isDark={isDark}
        onToggleTheme={toggleTheme}
        user={user}
        onLogout={logout}
      />

      <div className="app-body">
        <Sidebar
          incidents={incidents}
          health={health}
          activeView={activeView}
          onViewChange={setActiveView}
        />

        {activeView === 'admin' ? (
          <main className="main-content main-content-full">
            <AdminPanel />
          </main>
        ) : (
          <>
            <main className="main-content">
              <LiveFeed
                incidents={incidents}
                onSelect={handleSelectIncident}
                selectedId={selected?.id}
              />
            </main>

            <aside className="right-panel">
              {selected ? (
                <IncidentDetail
                  incident={selected}
                  onUpdate={handleIncidentUpdate}
                  onClose={handleCloseDetail}
                  userRole={user?.role}
                />
              ) : (
                <ActivityPanel incidents={incidents} />
              )}
            </aside>
          </>
        )}
      </div>

      {loading && (
        <div className="initial-loader">
          <div className="loader-spinner"></div>
          <span>Connecting to IMS backend...</span>
        </div>
      )}

      {showCreateModal && (
        <CreateIncidentModal
          onClose={() => setShowCreateModal(false)}
          onCreated={fetchIncidents}
        />
      )}
    </div>
  );
}

// ── App — Router ─────────────────────────────────────────────────────────

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
