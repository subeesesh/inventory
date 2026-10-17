import React, { useState, useEffect, useCallback } from 'react';
import { Card } from './ui';
import { useToast } from './ToastProvider';
import api from '../api';

const SEVERITY_COLORS = { critical: '#f87171', warning: '#fbbf24', info: '#60a5fa' };

const STATUS_STYLES = {
  notified:       { color: '#60a5fa', label: 'Notified' },
  pending_review: { color: '#fbbf24', label: 'Needs review' },
  approved:       { color: '#4ade80', label: 'Approved' },
  rejected:       { color: '#94a3b8', label: 'Rejected' },
};

const humanize = (s) => (s || '').replace(/_/g, ' ');

function Pill({ color, children }) {
  return (
    <span style={{ background: `${color}22`, color, padding: '2px 8px', borderRadius: '12px', fontSize: '11px', whiteSpace: 'nowrap' }}>
      {children}
    </span>
  );
}

/**
 * Monitoring alerts (§III-C) and the Automation & Alert System feed (§III-J).
 * Owners can approve or reject actions that the policy engine held for review.
 */
export function AlertsPanel({ role, productName = (id) => id }) {
  const { showToast } = useToast();
  const [events, setEvents]   = useState([]);
  const [actions, setActions] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [error, setError]     = useState(null);

  const load = useCallback(async () => {
    try {
      const [e, a] = await Promise.all([
        api.get('/tenants/monitoring/events'),
        api.get('/tenants/automation/actions'),
      ]);
      setEvents(e || []);
      setActions((a || []).slice(0, 10));
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const res = await api.post('/tenants/monitoring/scan');
      showToast(`Scan complete: ${res.events_detected} new alert(s)`, 'success');
      await load();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setScanning(false);
    }
  };

  const handleReview = async (id, approve) => {
    try {
      await api.post(`/tenants/automation/actions/${id}/review`, { approve });
      showToast(approve ? 'Action approved' : 'Action rejected', 'success');
      await load();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const entityLabel = (e) => (e.entity_type === 'product' ? productName(e.entity_id) : `${e.entity_type} ${e.entity_id || ''}`);

  return (
    <Card title="🛰️ Monitoring & Automation">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px' }}>
        {/* Open alerts */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#94a3b8', fontSize: '13px' }}>Open alerts ({events.length})</span>
            <button
              onClick={handleScan}
              disabled={scanning}
              style={{ padding: '6px 12px', borderRadius: '6px', background: scanning ? 'rgba(139,92,246,0.4)' : '#8b5cf6', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px' }}
            >
              {scanning ? 'Scanning…' : 'Scan now'}
            </button>
          </div>
          {error && <span style={{ color: '#f87171', fontSize: '13px' }}>{error}</span>}
          {events.length === 0
            ? <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>No open alerts.</p>
            : events.slice(0, 8).map(e => (
              <div key={e.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', padding: '8px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                  <span style={{ color: '#e2e8f0', fontSize: '13px', textTransform: 'capitalize' }}>{humanize(e.event_type)}</span>
                  <span style={{ color: '#64748b', fontSize: '12px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entityLabel(e)}</span>
                </div>
                <Pill color={SEVERITY_COLORS[e.severity] || '#94a3b8'}>{e.severity}</Pill>
              </div>
            ))}
        </div>

        {/* Automation actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <span style={{ color: '#94a3b8', fontSize: '13px' }}>Automated actions</span>
          {actions.length === 0
            ? <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>No automated actions yet. Stock alerts trigger an AMDIE reorder analysis automatically.</p>
            : actions.map(a => {
              const st = STATUS_STYLES[a.status] || { color: '#94a3b8', label: a.status };
              return (
                <div key={a.id} style={{ display: 'flex', flexDirection: 'column', gap: '6px', padding: '8px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: '#e2e8f0', fontSize: '13px' }}>{a.description}</span>
                    <Pill color={st.color}>{st.label}</Pill>
                  </div>
                  <span style={{ color: '#64748b', fontSize: '12px' }}>{a.policy_reason}</span>
                  {a.status === 'pending_review' && role === 'owner' && (
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button onClick={() => handleReview(a.id, true)} style={{ padding: '5px 12px', borderRadius: '6px', background: '#16a34a', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px' }}>Approve</button>
                      <button onClick={() => handleReview(a.id, false)} style={{ padding: '5px 12px', borderRadius: '6px', background: 'transparent', color: '#f87171', border: '1px solid #f87171', cursor: 'pointer', fontSize: '12px' }}>Reject</button>
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      </div>
    </Card>
  );
}
