/**
 * CreateIncidentModal — Sends a test signal to the /ingest endpoint.
 * This lets users manually create incidents via the dashboard for testing.
 */

import { useState } from 'react';
import { api } from '../api';
import './CreateIncidentModal.css';

export default function CreateIncidentModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    title: '',
    severity: 'P1',
    source: 'manual-dashboard',
    description: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function handleChange(e) {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.title.trim()) {
      setError('Please enter an incident title.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await api.ingestSignal({
        title: form.title,
        severity: form.severity,
        source: form.source || 'manual-dashboard',
        description: form.description || `Manually created: ${form.title}`,
        timestamp: new Date().toISOString(),
      });
      onCreated?.();
      onClose();
    } catch (e) {
      setError(e.detail || 'Failed to ingest signal. Is the backend running?');
    }
    setSubmitting(false);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <h2 className="modal-title">Create Incident</h2>

        <form className="modal-form" onSubmit={handleSubmit} id="create-incident-form">
          <div className="modal-field">
            <label htmlFor="modal-title">Incident Title</label>
            <input
              id="modal-title"
              name="title"
              type="text"
              className="modal-input"
              placeholder="e.g., Database connection timeout"
              value={form.title}
              onChange={handleChange}
              autoFocus
            />
          </div>

          <div className="modal-row">
            <div className="modal-field">
              <label htmlFor="modal-severity">Severity</label>
              <select
                id="modal-severity"
                name="severity"
                className="modal-input"
                value={form.severity}
                onChange={handleChange}
              >
                <option value="P0">P0 — Critical</option>
                <option value="P1">P1 — High</option>
                <option value="P2">P2 — Medium</option>
              </select>
            </div>

            <div className="modal-field">
              <label htmlFor="modal-source">Source</label>
              <select
                id="modal-source"
                name="source"
                className="modal-input"
                value={form.source}
                onChange={handleChange}
              >
                <option value="manual-dashboard">Dashboard</option>
                <option value="prometheus">Prometheus</option>
                <option value="datadog">Datadog</option>
                <option value="cloudwatch">CloudWatch</option>
              </select>
            </div>
          </div>

          <div className="modal-field">
            <label htmlFor="modal-desc">Description</label>
            <input
              id="modal-desc"
              name="description"
              type="text"
              className="modal-input"
              placeholder="Brief description of the incident"
              value={form.description}
              onChange={handleChange}
            />
          </div>

          {error && <div className="modal-error">{error}</div>}

          <div className="modal-actions">
            <button
              type="submit"
              className="modal-btn modal-btn-primary"
              disabled={submitting}
            >
              {submitting ? 'Creating...' : 'Create'}
            </button>
            <button
              type="button"
              className="modal-btn modal-btn-secondary"
              onClick={onClose}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
