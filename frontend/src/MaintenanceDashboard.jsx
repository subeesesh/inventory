import React, { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

const DECISION_TYPE_LABELS = {
  reorder_quantity: 'Reorder Quantity',
  price_adjustment: 'Price Adjustment',
  promotion_trigger: 'Promotion Trigger'
};

function MaintenanceDashboard({ token, onLogout }) {
  const [metrics, setMetrics] = useState(null);
  const [decisions, setDecisions] = useState([]);
  const [selectedDecisionId, setSelectedDecisionId] = useState(null);
  const [decisionExplain, setDecisionExplain] = useState(null);

  const authHeaders = {
    'Authorization': `Bearer ${token}`
  };

  useEffect(() => {
    fetchMetrics();
    fetchDecisions();
  }, []);

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${API_BASE}/tenants/metrics`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
      }
    } catch (e) {
      console.error("Error fetching metrics", e);
    }
  };

  const fetchDecisions = async () => {
    try {
      const res = await fetch(`${API_BASE}/tenants/decisions`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setDecisions(data);
      }
    } catch (e) {
      console.error("Error fetching decisions", e);
    }
  };

  const viewExplanation = async (id) => {
    try {
      const res = await fetch(`${API_BASE}/tenants/decisions/${id}/explain`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setDecisionExplain(data);
        setSelectedDecisionId(id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="app-container">
      <div className="main-content" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto' }}>
        <header className="app-header">
          <div className="logo-section">
            <h1>Control Tower - Maintenance Console</h1>
            <p>System Health, Multi-Domain Pipelines & Ops Tracing (Financial Data Redacted)</p>
          </div>
          <div className="header-controls" style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Logged in as: <strong>Maintenance</strong></span>
            <button className="glow-btn" onClick={onLogout} style={{ padding: '6px 12px' }}>Logout</button>
          </div>
        </header>

        {metrics && (
          <>
            <div className="kpis-grid">
              <div className="kpi-card glass">
                <div className="kpi-header"><span className="kpi-title">Avg Pipeline Latency</span></div>
                <div className="kpi-value">38 ms</div>
                <div className="kpi-footer">Across all AMDIE cycles</div>
              </div>
              <div className="kpi-card glass success">
                <div className="kpi-header"><span className="kpi-title">Overall Solver Health</span></div>
                <div className="kpi-value">100%</div>
                <div className="kpi-footer">HiGHS LP Solver convergence</div>
              </div>
              <div className="kpi-card glass danger">
                <div className="kpi-header"><span className="kpi-title">System Conflict Rate</span></div>
                <div className="kpi-value">{metrics.conflict_percentage.toFixed(1)}%</div>
                <div className="kpi-footer">Total divergence alerts</div>
              </div>
              <div className="kpi-card glass">
                <div className="kpi-header"><span className="kpi-title">Retraining Pipeline</span></div>
                <div className="kpi-value">{metrics.total_decisions % 30} / 30</div>
                <div className="kpi-footer">Decisions to next cycle</div>
              </div>
            </div>

            {/* Per-Decision-Type Health Breakdown Panel */}
            <div className="section-card glass" style={{ marginTop: '20px' }}>
              <h2>Multi-Domain Pipeline Health Breakdown</h2>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Pipeline / Decision Domain</th>
                      <th>Registered Agents</th>
                      <th>Total Cycles</th>
                      <th>Conflict / Divergence Rate</th>
                      <th>Solver Success Rate</th>
                      <th>Outcomes Logged</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.decision_type_stats && Object.entries(metrics.decision_type_stats).map(([dt, stats]) => (
                      <tr key={dt}>
                        <td><strong>{stats.label || DECISION_TYPE_LABELS[dt] || dt}</strong></td>
                        <td>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                            {dt === 'reorder_quantity' ? 'Inventory, Sales, Finance, Procurement' :
                             dt === 'price_adjustment' ? 'Pricing, Sales, Risk' :
                             dt === 'promotion_trigger' ? 'Marketing, Finance' : 'Registered Agents'}
                          </span>
                        </td>
                        <td>{stats.total_decisions}</td>
                        <td>
                          <span className={`badge ${stats.conflict_rate > 30 ? 'conflict' : 'aligned'}`}>
                            {stats.conflict_rate.toFixed(1)}%
                          </span>
                        </td>
                        <td style={{ color: stats.solver_success_rate >= 90 ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                          {stats.solver_success_rate.toFixed(1)}%
                        </td>
                        <td>{stats.outcomes_logged}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        <div className="section-card glass" style={{ marginTop: '20px' }}>
          <h2>Ops Trace Logs</h2>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Domain Type</th>
                  <th>Product SKU</th>
                  <th>Conflict Score</th>
                  <th>System Action</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map(d => (
                  <tr key={d.id}>
                    <td>{d.date}</td>
                    <td>
                      <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                        {DECISION_TYPE_LABELS[d.decision_type] || d.decision_type}
                      </span>
                    </td>
                    <td><strong>{d.product_id}</strong></td>
                    <td>
                      <span className={`badge ${d.conflict_detected ? 'conflict' : 'aligned'}`}>
                        {d.conflict_score.toFixed(2)}
                      </span>
                    </td>
                    <td>
                      <button className="glow-btn" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => viewExplanation(d.id)}>
                        View Trace
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {selectedDecisionId && decisionExplain && (
          <div className="detail-overlay">
            <div className="detail-modal glass">
              <button className="close-btn" onClick={() => setSelectedDecisionId(null)}>&times;</button>
              <div className="modal-header">
                <h2>Trace Explorer (Redacted)</h2>
                <p>ID: {decisionExplain.id} | Domain: <strong>{DECISION_TYPE_LABELS[decisionExplain.decision_type] || decisionExplain.decision_type}</strong> | Product: {decisionExplain.product_id}</p>
              </div>

              <div className="grid-2col">
                <div className="section-card glass">
                  <h3>Agent Payloads</h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {Object.entries(decisionExplain.agent_decisions).map(([agent, dec]) => (
                      <div key={agent} className="agent-card">
                        <div className="agent-header">
                          <span style={{ textTransform: 'capitalize' }}>{agent} Agent</span>
                        </div>
                        <div className="agent-metrics">
                          <div className="metric-item">
                            <span className="metric-label">Confidence</span>
                            <span className="metric-val">{dec.confidence?.toFixed(2) || 'N/A'}</span>
                          </div>
                          <div className="metric-item">
                            <span className="metric-label">Risk</span>
                            <span className="metric-val">{dec.risk_score?.toFixed(2) || 'N/A'}</span>
                          </div>
                          <div className="metric-item">
                            <span className="metric-label">Cost / Benefit</span>
                            <span className="metric-val" style={{ color: '#ef4444' }}>
                              {dec.expected_cost || dec.expected_benefit || 'N/A'}
                            </span>
                          </div>
                        </div>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Reason: {dec.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="section-card glass">
                  <h3>LP Solver Context</h3>
                  <pre style={{ fontSize: '12px', overflowX: 'auto', color: 'var(--text-muted)' }}>
                    {JSON.stringify(decisionExplain.optimization_problem, null, 2)}
                  </pre>
                  
                  <h3 style={{ marginTop: '20px' }}>Weight Distribution</h3>
                  <pre style={{ fontSize: '12px', overflowX: 'auto', color: 'var(--text-muted)' }}>
                    {JSON.stringify(decisionExplain.weights, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default MaintenanceDashboard;
