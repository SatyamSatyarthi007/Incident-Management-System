/**
 * RCAForm — Root Cause Analysis submission form.
 * Required before an incident can be closed.
 */

import { useState } from 'react';
import './RCAForm.css';

export default function RCAForm({ onSubmit }) {
  const [formData, setFormData] = useState({
    root_cause: '',
    impact: '',
    resolution: '',
    prevention: '',
    incident_start: '',
    incident_end: '',
    created_by: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function handleChange(e) {
    setFormData(prev => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    // Validation
    const required = ['root_cause', 'impact', 'resolution', 'prevention', 'incident_start', 'incident_end', 'created_by'];
    const missing = required.filter(k => !formData[k].trim());
    if (missing.length > 0) {
      setError(`Please fill in: ${missing.join(', ')}`);
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        ...formData,
        incident_start: new Date(formData.incident_start).toISOString(),
        incident_end: new Date(formData.incident_end).toISOString(),
      };
      await onSubmit(payload);
    } catch (e) {
      setError(e.detail || 'Failed to submit RCA');
    }
    setSubmitting(false);
  }

  return (
    <form className="rca-form" onSubmit={handleSubmit} id="rca-form">
      <div className="rca-form-grid">
        <div className="rca-form-field">
          <label htmlFor="rca-root-cause">Root Cause</label>
          <textarea
            id="rca-root-cause"
            name="root_cause"
            value={formData.root_cause}
            onChange={handleChange}
            placeholder="What was the underlying root cause?"
            rows={3}
          />
        </div>

        <div className="rca-form-field">
          <label htmlFor="rca-impact">Impact</label>
          <textarea
            id="rca-impact"
            name="impact"
            value={formData.impact}
            onChange={handleChange}
            placeholder="What was the business/technical impact?"
            rows={2}
          />
        </div>

        <div className="rca-form-field">
          <label htmlFor="rca-resolution">Resolution</label>
          <textarea
            id="rca-resolution"
            name="resolution"
            value={formData.resolution}
            onChange={handleChange}
            placeholder="How was the incident resolved?"
            rows={2}
          />
        </div>

        <div className="rca-form-field">
          <label htmlFor="rca-prevention">Prevention</label>
          <textarea
            id="rca-prevention"
            name="prevention"
            value={formData.prevention}
            onChange={handleChange}
            placeholder="What steps will prevent recurrence?"
            rows={2}
          />
        </div>

        {/* Date fields in a constrained row */}
        <div className="rca-date-row">
          <div className="rca-form-field">
            <label htmlFor="rca-start">Incident Start</label>
            <input
              type="datetime-local"
              id="rca-start"
              name="incident_start"
              value={formData.incident_start}
              onChange={handleChange}
            />
          </div>

          <div className="rca-form-field">
            <label htmlFor="rca-end">Incident End</label>
            <input
              type="datetime-local"
              id="rca-end"
              name="incident_end"
              value={formData.incident_end}
              onChange={handleChange}
            />
          </div>
        </div>

        <div className="rca-form-field">
          <label htmlFor="rca-author">Author</label>
          <input
            type="text"
            id="rca-author"
            name="created_by"
            value={formData.created_by}
            onChange={handleChange}
            placeholder="Your name"
          />
        </div>
      </div>

      {error && <div className="rca-error">{error}</div>}

      <button
        type="submit"
        className="rca-submit-btn"
        disabled={submitting}
        id="rca-submit"
      >
        {submitting ? 'Submitting...' : 'Submit Root Cause Analysis'}
      </button>
    </form>
  );
}
