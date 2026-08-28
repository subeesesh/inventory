import React, { useState, useEffect } from 'react';
import { StatCard, Chart, Card, DataTable, Modal, RoleGate } from '../components/ui';
import { useToast } from '../components/ToastProvider';
import api from '../api';

const TRIGGER_ROLES = {
  reorder_quantity:  ['owner', 'inventory_manager', 'procurement_officer'],
  price_adjustment:  ['owner', 'finance_officer'],
  promotion_trigger: ['owner', 'inventory_manager'],
};

function Skeleton() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px' }}>
      {[0,1,2,3].map(i => (
        <div key={i} style={{
          height: '110px', borderRadius: '12px',
          background: 'linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%)',
          backgroundSize: '200% 100%',
          animation: 'shimmer 1.5s infinite',
        }} />
      ))}
      <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
    </div>
  );
}

export const Dashboard = ({ role }) => {
  const { showToast } = useToast();
  const [metrics, setMetrics]       = useState(null);
  const [salesData, setSalesData]   = useState([]);
  const [decisions, setDecisions]   = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [selectedDecision, setSelectedDecision] = useState(null);

  // Trigger widget state
  const [triggerProductId, setTriggerProductId] = useState('');
  const [triggerDate, setTriggerDate]           = useState(new Date().toISOString().slice(0, 10));
  const [triggerType, setTriggerType]           = useState('reorder_quantity');
  const [triggerLoading, setTriggerLoading]     = useState(false);
  const [triggerResult, setTriggerResult]       = useState(null);
  const [triggerError, setTriggerError]         = useState(null);

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [m, d] = await Promise.all([
          api.get('/tenants/metrics'),
          api.get('/tenants/decisions'),
        ]);
        setMetrics(m);
        setDecisions((d || []).slice(0, 8));

        if (role === 'owner' || role === 'finance_officer') {
          const s = await api.get('/tenants/reports?type=sales_summary');
          setSalesData(s.data || []);
        }
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, [role]);

  const handleTrigger = async () => {
    if (!triggerProductId.trim()) { setTriggerError('Product ID is required'); return; }
    setTriggerLoading(true); setTriggerResult(null); setTriggerError(null);
    try {
      const result = await api.post('/tenants/decisions/trigger', {
        product_id: triggerProductId,
        date_str: triggerDate,
        decision_type: triggerType,
      });
      setTriggerResult(result);
      showToast('AMDIE analysis complete', 'success');
    } catch (e) {
      setTriggerError(e.message);
    } finally {
      setTriggerLoading(false);
    }
  };

  const decisionCols = [
    { header: 'Product', render: r => <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{(r.product_id || '').slice(0, 12)}…</span> },
    { header: 'Type', render: r => {
      const colors = { reorder_quantity: '#60a5fa', price_adjustment: '#c084fc', promotion_trigger: '#fbbf24' };
      return <span style={{ background: `${colors[r.decision_type] || '#94a3b8'}22`, color: colors[r.decision_type] || '#94a3b8', padding: '2px 8px', borderRadius: '12px', fontSize: '12px' }}>{(r.decision_type || '').replace('_', ' ')}</span>;
    }},
    { header: 'Recommendation', render: r => <span>{typeof r.fused_recommendation === 'number' ? r.fused_recommendation.toFixed(2) : '—'}</span> },
    { header: '', render: r => r.conflict_detected ? <span title="Conflict detected">⚠️</span> : null },
    { header: 'Date', render: r => r.date ? new Date(r.date).toLocaleDateString() : '—' },
  ];

  // Determine which trigger options this role can see
  const visibleTriggerOptions = Object.entries(TRIGGER_ROLES).filter(([, roles]) => roles.includes(role));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      <h2 style={{ margin: 0, fontSize: '22px' }}>AMDIE Control Tower</h2>

      {error && (
        <div style={{ background: 'rgba(248,113,113,0.15)', border: '1px solid #f87171', color: '#fca5a5', padding: '12px 16px', borderRadius: '8px' }}>
          ⚠️ {error}
        </div>
      )}

      {/* Stat cards */}
      {loading ? <Skeleton /> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px' }}>
          <StatCard title="Today's Revenue" value={`$${(metrics?.total_revenue_today || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} icon="💵" color="#4ade80" />
          <StatCard title="Today's Transactions" value={String(metrics?.total_transactions_today || 0)} icon="🧾" color="#60a5fa" />
          <RoleGate allowedRoles={['owner', 'inventory_manager', 'procurement_officer']} currentRole={role}>
            <StatCard
              title="Low Stock Items"
              value={String(metrics?.low_stock_count || 0)}
              icon="📦"
              color={(metrics?.low_stock_count || 0) > 0 ? '#f87171' : '#4ade80'}
            />
          </RoleGate>
          <StatCard title="AI Accuracy" value={`${((metrics?.cumulative_accuracy || 0) * 100).toFixed(1)}%`} icon="🧠" color="#8b5cf6" />
          <RoleGate allowedRoles={['owner', 'procurement_officer']} currentRole={role}>
            <StatCard title="Pending POs" value={String(metrics?.pending_po_count || 0)} icon="🚚" color="#fbbf24" />
          </RoleGate>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
        {/* Revenue chart — owner & finance_officer only */}
        <RoleGate allowedRoles={['owner', 'finance_officer']} currentRole={role}>
          <Card title="Sales Revenue (Last 30 Days)">
            {salesData.length === 0
              ? <p style={{ color: '#64748b', textAlign: 'center' }}>No sales data in this period.</p>
              : <Chart data={salesData} dataKeys={['revenue']} xAxisKey="date" />}
          </Card>
        </RoleGate>

        {/* AMDIE Trigger widget */}
        {visibleTriggerOptions.length > 0 && (
          <Card title="Run AMDIE Analysis">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <input
                value={triggerProductId}
                onChange={e => setTriggerProductId(e.target.value)}
                placeholder="Product ID"
                style={{ padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
              />
              <input
                type="date"
                value={triggerDate}
                onChange={e => setTriggerDate(e.target.value)}
                style={{ padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
              />
              <select
                value={triggerType}
                onChange={e => setTriggerType(e.target.value)}
                style={{ padding: '10px', borderRadius: '6px', background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
              >
                {visibleTriggerOptions.map(([dt]) => (
                  <option key={dt} value={dt}>{dt.replace(/_/g, ' ')}</option>
                ))}
              </select>
              {triggerError && <span style={{ color: '#f87171', fontSize: '13px' }}>{triggerError}</span>}
              <button
                onClick={handleTrigger}
                disabled={triggerLoading}
                style={{ padding: '12px', borderRadius: '8px', background: triggerLoading ? 'rgba(139,92,246,0.4)' : '#8b5cf6', color: '#fff', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}
              >
                {triggerLoading ? 'Running…' : '▶ Run Analysis'}
              </button>
              {triggerResult && (
                <div style={{ background: 'rgba(74,222,128,0.08)', border: '1px solid #4ade80', borderRadius: '8px', padding: '12px', fontSize: '13px', color: '#a7f3d0' }}>
                  <strong>Fused recommendation:</strong> {triggerResult.fused_recommendation?.toFixed(2)}<br />
                  <strong>Conflict:</strong> {triggerResult.conflict_detected ? '⚠️ Yes' : '✓ No'}<br />
                  <span style={{ color: '#64748b' }}>{triggerResult.explanation?.slice(0, 180)}…</span>
                </div>
              )}
            </div>
          </Card>
        )}
      </div>

      {/* Recent decisions feed */}
      <Card title="Recent AI Decisions">
        {decisions.length === 0
          ? <p style={{ color: '#64748b', textAlign: 'center' }}>No decisions yet. Trigger an AMDIE analysis above.</p>
          : (
            <DataTable
              columns={decisionCols}
              data={decisions}
              onRowClick={setSelectedDecision}
            />
          )}
      </Card>

      {/* Decision detail modal */}
      {selectedDecision && (
        <Modal title="Decision Detail" onClose={() => setSelectedDecision(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <p style={{ color: '#94a3b8', fontSize: '13px', margin: 0 }}>Product: <strong style={{ color: '#fff' }}>{selectedDecision.product_id}</strong></p>
            <p style={{ color: '#94a3b8', fontSize: '13px', margin: 0 }}>Type: <strong style={{ color: '#fff' }}>{selectedDecision.decision_type}</strong></p>
            <p style={{ color: '#94a3b8', fontSize: '13px', margin: 0 }}>Recommendation: <strong style={{ color: '#4ade80' }}>{selectedDecision.fused_recommendation?.toFixed(4)}</strong></p>
            <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '16px', maxHeight: '300px', overflowY: 'auto', color: '#cbd5e1', fontSize: '13px', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
              {selectedDecision.explanation || 'No explanation available.'}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
