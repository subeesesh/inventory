import React, { useState, useEffect } from 'react';
import './App.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

const DECISION_TYPE_LABELS = {
  all: 'All Decisions',
  reorder_quantity: 'Reorder Quantity',
  price_adjustment: 'Price Adjustment',
  promotion_trigger: 'Promotion Trigger'
};

function OwnerDashboard({ token, onLogout }) {
  const authHeaders = { Authorization: `Bearer ${token}` };
  const [metrics, setMetrics] = useState({
    cumulative_accuracy: 0.85,
    cash_balance: 50000.0,
    period_budget: 15000.0,
    agent_reliability: { inventory: 0.85, sales: 0.85, finance: 0.85, pricing: 0.85, marketing: 0.85, procurement: 0.85 },
    total_decisions: 0,
    conflict_percentage: 0.0,
    decision_type_stats: {}
  });
  const [products, setProducts] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [activeTab, setActiveTab] = useState('all');
  const [businessGoal, setBusinessGoal] = useState('maximize_profit');
  const [chatHistory, setChatHistory] = useState([
    { role: 'assistant', content: 'Hello! I am the AI Control Tower Copilot. Ask me questions about recent decisions, agent conflicts, pricing, promotions, or budget constraints!' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [selectedDecisionId, setSelectedDecisionId] = useState(null);
  const [decisionExplain, setDecisionExplain] = useState(null);
  const [triggerProduct, setTriggerProduct] = useState(null);
  const [triggerDecisionType, setTriggerDecisionType] = useState('reorder_quantity');
  const [triggerDate, setTriggerDate] = useState('2026-07-25');
  const [loading, setLoading] = useState(false);
  const [outcomeValue, setOutcomeValue] = useState('');

  // Fetch initial data
  useEffect(() => {
    fetchTenantInfo();
    fetchMetrics();
    fetchProducts();
    fetchDecisions(activeTab);
  }, []);

  const fetchTenantInfo = async () => {
    try {
      const res = await fetch(`${API_BASE}/tenants/me`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setBusinessGoal(data.business_goal);
      }
    } catch (e) {
      console.error("Error fetching tenant", e);
    }
  };

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

  const fetchProducts = async () => {
    try {
      const res = await fetch(`${API_BASE}/tenants/products`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setProducts(data);
      }
    } catch (e) {
      console.error("Error fetching products", e);
    }
  };

  const fetchDecisions = async (dt = activeTab) => {
    try {
      const url = dt && dt !== 'all' 
        ? `${API_BASE}/tenants/decisions?decision_type=${dt}`
        : `${API_BASE}/tenants/decisions`;
      const res = await fetch(url, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setDecisions(data);
      }
    } catch (e) {
      console.error("Error fetching decisions", e);
    }
  };

  const handleTabChange = (dt) => {
    setActiveTab(dt);
    fetchDecisions(dt);
  };

  const handleGoalChange = async (e) => {
    const goal = e.target.value;
    setBusinessGoal(goal);
    try {
      await fetch(`${API_BASE}/tenants/goal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ business_goal: goal })
      });
      fetchMetrics();
    } catch (err) {
      console.error("Error updating goal", err);
    }
  };

  const triggerDecision = async () => {
    if (!triggerProduct) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/tenants/decisions/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          product_id: triggerProduct.id,
          date_str: triggerDate,
          decision_type: triggerDecisionType
        })
      });
      if (res.ok) {
        const data = await res.json();
        setTriggerProduct(null);
        fetchDecisions(activeTab);
        fetchMetrics();
        if (data.decision_id) {
          viewExplanation(data.decision_id);
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
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

  const submitOutcome = async (id) => {
    if (!outcomeValue) return;
    try {
      const res = await fetch(`${API_BASE}/tenants/decisions/${id}/outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ actual_outcome: parseFloat(outcomeValue) })
      });
      if (res.ok) {
        setOutcomeValue('');
        viewExplanation(id);
        fetchDecisions(activeTab);
        fetchMetrics();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim()) return;
    const userMsg = { role: 'user', content: chatInput };
    const updatedHistory = [...chatHistory, userMsg];
    setChatHistory(updatedHistory);
    setChatInput('');

    try {
      const res = await fetch(`${API_BASE}/tenants/copilot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ messages: updatedHistory })
      });
      if (res.ok) {
        const data = await res.json();
        setChatHistory([...updatedHistory, { role: 'assistant', content: data.content }]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // SVG Utility Curve visualizer for reorder_quantity
  const renderUtilityCurves = () => {
    if (!decisionExplain) return null;
    const decs = decisionExplain.agent_decisions;
    const fusedX = decisionExplain.fused_recommendation;

    const maxRec = Math.max(
      ...Object.values(decs).map(d => typeof d.recommendation === 'number' ? d.recommendation : 0),
      fusedX,
      100
    ) * 1.3;

    const width = 500;
    const height = 180;
    const padding = 30;

    const scaleX = (x) => padding + (Math.max(0, x) / maxRec) * (width - 2 * padding);
    const scaleY = (y) => height - padding - y * (height - 2 * padding);

    const getTrianglePath = (rec, conf, delta = 50.0) => {
      const spread = (0.4 * Math.abs(rec) + delta) / Math.max(conf, 0.01);
      const left = Math.max(0, rec - spread);
      const right = rec + spread;

      const pLeft = `${scaleX(left)},${scaleY(0)}`;
      const pPeak = `${scaleX(rec)},${scaleY(1.0)}`;
      const pRight = `${scaleX(right)},${scaleY(0)}`;

      return `M ${pLeft} L ${pPeak} L ${pRight} Z`;
    };

    const colorMap = {
      sales: '#6366f1',
      inventory: '#10b981',
      finance: '#06b6d4',
      procurement: '#8b5cf6'
    };

    return (
      <svg className="utility-svg" viewBox={`0 0 ${width} ${height}`}>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#334155" strokeWidth="1" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="#334155" strokeWidth="1" />
        
        {Object.entries(decs).map(([agent, d]) => (
          typeof d.recommendation === 'number' && (
            <path
              key={agent}
              d={getTrianglePath(d.recommendation, d.confidence || 0.8)}
              fill={`${colorMap[agent] || '#6366f1'}26`}
              stroke={colorMap[agent] || '#6366f1'}
              strokeWidth="2"
            />
          )
        ))}

        {/* Fused Recommendation Marker */}
        <line
          x1={scaleX(fusedX)}
          y1={padding}
          x2={scaleX(fusedX)}
          y2={height - padding}
          stroke="#ef4444"
          strokeWidth="2"
          strokeDasharray="4"
        />
        <circle cx={scaleX(fusedX)} cy={scaleY(1.0)} r="6" fill="#ef4444" />
        
        <text x={scaleX(fusedX) + 8} y={padding + 12} fill="#ef4444" fontSize="11" fontWeight="bold">
          Fused: {fusedX.toFixed(1)} units
        </text>
        <text x={padding - 20} y={padding + 5} fill="#64748b" fontSize="10">1.0</text>
        <text x={padding - 20} y={height - padding} fill="#64748b" fontSize="10">0.0</text>
        <text x={width - padding - 20} y={height - 10} fill="#64748b" fontSize="10">Qty</text>
      </svg>
    );
  };

  // Visualizer for price_adjustment
  const renderPriceAdjustmentViz = () => {
    if (!decisionExplain) return null;
    const decs = decisionExplain.agent_decisions;
    const delta = decisionExplain.fused_recommendation;
    const pricingDec = decs.pricing || {};

    const prod = products.find(p => p.id === decisionExplain.product_id);
    const currentPrice = prod ? prod.unit_price : 50.0;
    const newPrice = currentPrice + delta;

    return (
      <div className="price-viz-container">
        <h4>Price Adjustment Delta & Elasticity Impact</h4>
        <div className="price-bars">
          <div className="price-box">
            <span className="lbl">Current Unit Price</span>
            <span className="val">${currentPrice.toFixed(2)}</span>
          </div>
          <div className="delta-indicator" style={{ color: delta >= 0 ? '#10b981' : '#ef4444' }}>
            <span>{delta >= 0 ? '▲ +' : '▼ '}${delta.toFixed(2)}</span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Fused Delta</span>
          </div>
          <div className="price-box highlight">
            <span className="lbl">Optimized Target Price</span>
            <span className="val" style={{ color: 'var(--primary)' }}>${newPrice.toFixed(2)}</span>
          </div>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '4px' }}>
          <strong>Pricing Agent Assessment:</strong> {pricingDec.reason || 'OLS log-log demand elasticity regression evaluated.'}
        </div>
      </div>
    );
  };

  // Visualizer for promotion_trigger
  const renderPromotionViz = () => {
    if (!decisionExplain) return null;
    const discountDepth = decisionExplain.fused_recommendation;
    const mktDec = decisionExplain.agent_decisions.marketing || {};

    return (
      <div className="promo-viz-container">
        <h4>Slow-Moving Stock Discount Depth</h4>
        <div className="promo-gauge">
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
            <span>Suggested Promotional Discount:</span>
            <strong style={{ color: '#ec4899', fontSize: '16px' }}>{(discountDepth * 100).toFixed(1)}% OFF</strong>
          </div>
          <div className="gauge-bar-outer">
            <div className="gauge-bar-inner" style={{ width: `${Math.min(100, Math.max(5, discountDepth * 100 * 2.5))}%` }}>
              {(discountDepth * 100).toFixed(0)}%
            </div>
          </div>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '4px' }}>
          <strong>Marketing Clearance Rationale:</strong> {mktDec.reason || 'Turnover rate analyzed relative to peer product inventory.'}
        </div>
      </div>
    );
  };

  const renderDecisionVisualizer = () => {
    const dt = decisionExplain?.decision_type || 'reorder_quantity';
    if (dt === 'price_adjustment') return renderPriceAdjustmentViz();
    if (dt === 'promotion_trigger') return renderPromotionViz();
    return renderUtilityCurves();
  };

  const formatRecommendation = (val, dt) => {
    if (dt === 'price_adjustment') {
      return `${val >= 0 ? '+' : ''}$${val.toFixed(2)}`;
    }
    if (dt === 'promotion_trigger') {
      return `${(val * 100).toFixed(1)}% off`;
    }
    return `${val.toFixed(1)} units`;
  };

  return (
    <div className="app-container">
      
      {/* Left Column: Dashboard Content */}
      <div className="main-content">
        
        {/* Header */}
        <header className="app-header">
          <div className="logo-section">
            <h1>AI Business Control Tower</h1>
            <p>Adaptive Multi-Agent SME Operations Suite — Phase 2 Multi-Domain Control Tower</p>
          </div>
          <div className="header-controls" style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Logged in as: <strong>Owner</strong></span>
            <button className="glow-btn" onClick={onLogout} style={{ padding: '6px 12px' }}>Logout</button>
            <div className="goal-selector">
              <label>Business Goal:</label>
              <select value={businessGoal} onChange={handleGoalChange}>
                <option value="maximize_profit">Maximize Profit</option>
                <option value="minimize_cost">Minimize Cost</option>
                <option value="minimize_risk">Minimize Risk</option>
                <option value="maximize_turnover">Maximize Turnover</option>
              </select>
            </div>
          </div>
        </header>

        {/* KPIs Section */}
        <div className="kpis-grid">
          <div className="kpi-card glass">
            <div className="kpi-header">
              <span className="kpi-title">Decision Accuracy</span>
            </div>
            <div className="kpi-value">{(metrics.cumulative_accuracy * 100).toFixed(1)}%</div>
            <div className="kpi-footer">Across all decision domains</div>
          </div>
          <div className="kpi-card glass accent">
            <div className="kpi-header">
              <span className="kpi-title">Ledger Cash Balance</span>
            </div>
            <div className="kpi-value">${metrics.cash_balance.toLocaleString()}</div>
            <div className="kpi-footer">Liquidity headroom</div>
          </div>
          <div className="kpi-card glass success">
            <div className="kpi-header">
              <span className="kpi-title">Period Budget Limit</span>
            </div>
            <div className="kpi-value">${metrics.period_budget.toLocaleString()}</div>
            <div className="kpi-footer">Allocated purchasing budget</div>
          </div>
          <div className="kpi-card glass danger">
            <div className="kpi-header">
              <span className="kpi-title">Agent Divergence</span>
            </div>
            <div className="kpi-value">{metrics.conflict_percentage.toFixed(0)}%</div>
            <div className="kpi-footer">Conflict-flagged decisions</div>
          </div>
        </div>

        {/* Sections Grid */}
        <div className="sections-grid">
          
          {/* Products List & Trigger Panel */}
          <div className="section-card glass">
            <h2>Active Catalog & Domain Negotiator</h2>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Product ID</th>
                    <th>Name</th>
                    <th>Category</th>
                    <th>Unit Price</th>
                    <th>Stock Level</th>
                    <th>Reorder Point</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map(p => (
                    <tr key={p.id}>
                      <td><strong>{p.id}</strong></td>
                      <td>{p.name}</td>
                      <td>{p.category}</td>
                      <td>${p.unit_price.toFixed(2)}</td>
                      <td style={{ color: p.stock_level < p.reorder_point ? '#ef4444' : '#10b981' }}>
                        {p.stock_level}
                      </td>
                      <td>{p.reorder_point}</td>
                      <td>
                        <button className="glow-btn" onClick={() => { setTriggerProduct(p); setTriggerDecisionType('reorder_quantity'); }}>
                          Trigger Decision
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Past Decisions Log with Decision Type Tabs */}
          <div className="section-card glass">
            <h2>AMDIE Multi-Domain Decisions Audit Log</h2>

            {/* Decision Type Tabs */}
            <div className="tabs-container">
              {['all', 'reorder_quantity', 'price_adjustment', 'promotion_trigger'].map(tabKey => (
                <button
                  key={tabKey}
                  className={`tab-btn ${activeTab === tabKey ? 'active' : ''}`}
                  onClick={() => handleTabChange(tabKey)}
                >
                  {DECISION_TYPE_LABELS[tabKey]}
                </button>
              ))}
            </div>

            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Product</th>
                    <th>Fused Recommendation</th>
                    <th>Goal Applied</th>
                    <th>Divergence Score</th>
                    <th>Actual Outcome</th>
                    <th>Action</th>
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
                      <td>{formatRecommendation(d.fused_recommendation, d.decision_type)}</td>
                      <td><code style={{ color: '#06b6d4' }}>{d.business_goal_applied}</code></td>
                      <td>
                        <span className={`badge ${d.conflict_detected ? 'conflict' : 'aligned'}`}>
                          {d.conflict_score.toFixed(2)} ({d.conflict_detected ? 'Diverging' : 'Aligned'})
                        </span>
                      </td>
                      <td>
                        {d.actual_outcome !== null ? (
                          <span style={{ color: '#10b981', fontWeight: 600 }}>{d.actual_outcome.toFixed(2)}</span>
                        ) : (
                          <span style={{ color: '#64748b', fontStyle: 'italic' }}>Pending</span>
                        )}
                      </td>
                      <td>
                        <button className="glow-btn" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => viewExplanation(d.id)}>
                          Explain Trace
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </div>

      </div>

      {/* Right Column: Copilot Chat */}
      <div className="copilot-panel">
        <div className="copilot-header">
          <h3>AI Business Control Tower Copilot</h3>
          <p>Multi-domain agent reasoning, pricing & operations</p>
        </div>
        
        <div className="chat-history">
          {chatHistory.map((msg, index) => (
            <div key={index} className={`chat-bubble ${msg.role}`}>
              {msg.content}
            </div>
          ))}
        </div>

        <div className="chat-input-area">
          <input
            type="text"
            placeholder="Ask Copilot about decisions..."
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendChatMessage()}
          />
          <button className="glow-btn" onClick={sendChatMessage}>Send</button>
        </div>
      </div>

      {/* Modal: Trigger reorder / pricing / promotion decision config */}
      {triggerProduct && (
        <div className="detail-overlay">
          <div className="detail-modal glass">
            <button className="close-btn" onClick={() => setTriggerProduct(null)}>&times;</button>
            <div className="modal-header">
              <h2>Trigger AMDIE Multi-Agent Negotiation</h2>
              <p>Select decision domain and compute optimal resolution for {triggerProduct.name} ({triggerProduct.id})</p>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', margin: '20px 0' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <label style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Decision Domain</label>
                <select
                  value={triggerDecisionType}
                  onChange={(e) => setTriggerDecisionType(e.target.value)}
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    color: '#fff',
                    border: '1px solid var(--border-color)',
                    padding: '10px',
                    borderRadius: '4px'
                  }}
                >
                  <option value="reorder_quantity">Reorder Quantity (Inventory, Sales, Finance, Procurement)</option>
                  <option value="price_adjustment">Price Adjustment (Pricing Elasticity, Sales, Risk)</option>
                  <option value="promotion_trigger">Promotion Trigger (Marketing Clearance, Finance)</option>
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <label style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Evaluation Date</label>
                <input
                  type="date"
                  value={triggerDate}
                  onChange={(e) => setTriggerDate(e.target.value)}
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    color: '#fff',
                    border: '1px solid var(--border-color)',
                    padding: '10px',
                    borderRadius: '4px'
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button className="glow-btn" onClick={triggerDecision} disabled={loading}>
                  {loading ? 'Running Multi-Agent Optimization...' : 'Run AMDIE Fusion'}
                </button>
                <button className="glow-btn" style={{ background: '#334155' }} onClick={() => setTriggerProduct(null)}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Explainability Trace Deep Drill-Down */}
      {selectedDecisionId && decisionExplain && (
        <div className="detail-overlay">
          <div className="detail-modal glass">
            <button className="close-btn" onClick={() => setSelectedDecisionId(null)}>&times;</button>
            
            <div className="modal-header">
              <h2>AMDIE Decision Explainability Deep Dive</h2>
              <p>ID: {decisionExplain.id} | Date: {decisionExplain.date} | Domain: <strong>{DECISION_TYPE_LABELS[decisionExplain.decision_type] || decisionExplain.decision_type}</strong> | SKU: {decisionExplain.product_id}</p>
            </div>

            {/* Natural Language Explanation Card */}
            <div className="section-card glass" style={{ background: 'rgba(99, 102, 241, 0.05)', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
              <h3>Decision Explanation</h3>
              <div style={{ fontSize: '14px', lineHeight: 1.6, color: 'var(--text-primary)', whiteSpace: 'pre-line' }}>
                {decisionExplain.natural_language_explanation}
              </div>
            </div>

            <div className="grid-2col">
              {/* Agent Decision Objects */}
              <div className="section-card glass">
                <h3>Domain Agent Outputs</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {Object.entries(decisionExplain.agent_decisions).map(([agent, dec]) => (
                    <div key={agent} className="agent-card">
                      <div className="agent-header">
                        <span style={{ textTransform: 'capitalize' }}>{agent} Agent</span>
                        <span style={{ color: 'var(--accent)' }}>Rec: {formatRecommendation(dec.recommendation, decisionExplain.decision_type)}</span>
                      </div>
                      <div className="agent-metrics">
                        <div className="metric-item">
                          <span className="metric-label">Confidence</span>
                          <span className="metric-val">{dec.confidence.toFixed(2)}</span>
                        </div>
                        <div className="metric-item">
                          <span className="metric-label">Risk</span>
                          <span className="metric-val">{dec.risk_score.toFixed(2)}</span>
                        </div>
                        <div className="metric-item">
                          <span className="metric-label">Cost</span>
                          <span className="metric-val">${dec.expected_cost?.toFixed(0) || '0'}</span>
                        </div>
                      </div>
                      <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Reason: {dec.reason}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Weights and Visualizer depending on decision_type */}
              <div className="section-card glass">
                <h3>AMDIE Weight Negotiation & Visualizer</h3>
                
                <div className="weight-comparison" style={{ marginBottom: '20px' }}>
                  {Object.entries(decisionExplain.weights).map(([agent, comps]) => (
                    <div key={agent} className="bar-row">
                      <span className="bar-label" style={{ textTransform: 'capitalize' }}>{agent}</span>
                      <div className="bar-outer">
                        <div
                          className={`bar-inner ${agent}`}
                          style={{ width: `${Math.max(10, Math.min(100, (comps.reliability || 0.3) * 100))}%` }}
                        ></div>
                      </div>
                      <span className="bar-val">{(comps.reliability * 100 || 33).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>

                <div className="utility-viz-container">
                  {renderDecisionVisualizer()}
                </div>
              </div>
            </div>

            <div className="grid-2col">
              {/* Retrieval Log entries audit */}
              <div className="section-card glass">
                <h3>Audit Log: Retrieval Manager Serving Log</h3>
                <div className="audit-list">
                  {decisionExplain.retrieval_log.map((item, idx) => (
                    <div key={idx} className={`audit-item ${item.source}`}>
                      <strong>[{item.agent_id.toUpperCase()}]</strong> | Source: {item.source.toUpperCase()} | Table: {item.table || 'N/A'} (ID: {item.id})
                      <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>Data: {item.details}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Outcome submission endpoint */}
              <div className="section-card glass">
                <h3>Decision Outcome Logging & Retraining</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                  Provide the actual ground truth outcome (units sold, price delta realized, or clearance lift) to update agent accuracy metrics and trigger AMDIE weight coefficient updates.
                </p>
                {decisionExplain.actual_outcome !== null ? (
                  <div style={{ padding: '12px', background: 'var(--success-glow)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '4px' }}>
                    <span style={{ color: 'var(--success)', fontWeight: 600 }}>Logged Actual Outcome: {formatRecommendation(decisionExplain.actual_outcome, decisionExplain.decision_type)}</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <input
                      type="number"
                      step="any"
                      placeholder="Actual outcome value"
                      value={outcomeValue}
                      onChange={(e) => setOutcomeValue(e.target.value)}
                      style={{
                        background: 'rgba(255,255,255,0.05)',
                        border: '1px solid var(--border-color)',
                        color: '#fff',
                        borderRadius: '4px',
                        padding: '10px',
                        flex: 1
                      }}
                    />
                    <button className="glow-btn" onClick={() => submitOutcome(decisionExplain.id)}>
                      Submit Outcome
                    </button>
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}

export default OwnerDashboard;
