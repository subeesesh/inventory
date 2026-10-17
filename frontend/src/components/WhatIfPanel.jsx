import React, { useState } from 'react';
import { Card } from './ui';
import api from '../api';

const humanize = (s) => (s || '').replace(/_/g, ' ');

export function WhatIfPanel({ products = [] }) {
  const [type, setType]               = useState('price_change');
  const [productId, setProductId]     = useState('');
  const [deltaPct, setDeltaPct]       = useState(10);
  const [delayDays, setDelayDays]     = useState(5);
  const [horizonDays, setHorizonDays] = useState(30);
  const [loading, setLoading]         = useState(false);
  const [result, setResult]           = useState(null);
  const [error, setError]             = useState(null);

  const handleSimulate = async () => {
    setLoading(true); setError(null);
    try {
      const res = await api.post('/tenants/scenarios/simulate', {
        type,
        product_id: productId || null,
        delta_pct: deltaPct / 100.0,
        delay_days: parseInt(delayDays) || 0,
        horizon_days: parseInt(horizonDays) || 30,
      });
      setResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const fmt = (n) => `$${Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <Card title="🔮 Counterfactual 'What-If' Scenario Simulator">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ color: '#94a3b8', fontSize: '12px' }}>Scenario Type</label>
            <select
              value={type}
              onChange={e => setType(e.target.value)}
              style={{ padding: '9px', borderRadius: '6px', background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: '13px' }}
            >
              <option value="price_change">Price Adjustment</option>
              <option value="demand_shock">Demand Shock</option>
              <option value="supplier_delay">Supplier Delay</option>
              <option value="staffing_change">Staffing Hours Change</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ color: '#94a3b8', fontSize: '12px' }}>Target Product (optional)</label>
            <select
              value={productId}
              onChange={e => setProductId(e.target.value)}
              style={{ padding: '9px', borderRadius: '6px', background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: '13px' }}
            >
              <option value="">All products</option>
              {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          {type !== 'supplier_delay' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ color: '#94a3b8', fontSize: '12px' }}>Delta % ({deltaPct > 0 ? `+${deltaPct}%` : `${deltaPct}%`})</label>
              <input
                type="range" min="-50" max="50" value={deltaPct}
                onChange={e => setDeltaPct(Number(e.target.value))}
                style={{ accentColor: '#8b5cf6' }}
              />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ color: '#94a3b8', fontSize: '12px' }}>Delay Days ({delayDays} days)</label>
              <input
                type="number" min="1" max="30" value={delayDays}
                onChange={e => setDelayDays(Number(e.target.value))}
                style={{ padding: '9px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: '13px' }}
              />
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ color: '#94a3b8', fontSize: '12px' }}>Horizon (Days)</label>
            <input
              type="number" min="7" max="90" value={horizonDays}
              onChange={e => setHorizonDays(Number(e.target.value))}
              style={{ padding: '9px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: '13px' }}
            />
          </div>
        </div>

        {error && (
          <div style={{ background: 'rgba(248,113,113,0.15)', border: '1px solid #f87171', color: '#fca5a5', padding: '10px 14px', borderRadius: '6px', fontSize: '13px' }}>
            {error}
          </div>
        )}

        <button
          onClick={handleSimulate}
          disabled={loading}
          style={{
            padding: '12px', borderRadius: '8px', background: loading ? 'rgba(139,92,246,0.4)' : '#8b5cf6',
            color: '#fff', border: 'none', fontWeight: 'bold', cursor: 'pointer', fontSize: '14px',
          }}
        >
          {loading ? 'Simulating Snapshot…' : '▶ Run What-If Simulation'}
        </button>

        {result && (
          <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <h4 style={{ margin: 0, color: '#e2e8f0', fontSize: '14px' }}>Simulation Results ({result.horizon_days} Days)</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', textAlign: 'center' }}>
              <div style={{ background: 'rgba(255,255,255,0.04)', padding: '12px', borderRadius: '8px' }}>
                <div style={{ color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>Baseline Trajectory</div>
                <div style={{ color: '#fff', marginTop: '6px', fontSize: '13px' }}>Demand: {result.current_trajectory.forecast_demand_units} units</div>
                <div style={{ color: '#4ade80', fontSize: '13px' }}>Revenue: {fmt(result.current_trajectory.projected_revenue)}</div>
                <div style={{ color: '#60a5fa', fontSize: '13px' }}>Cash: {fmt(result.current_trajectory.projected_cash_balance)}</div>
              </div>

              <div style={{ background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.3)', padding: '12px', borderRadius: '8px' }}>
                <div style={{ color: '#c084fc', fontSize: '11px', textTransform: 'uppercase' }}>Simulated Trajectory</div>
                <div style={{ color: '#fff', marginTop: '6px', fontSize: '13px' }}>Demand: {result.simulated_trajectory.forecast_demand_units} units</div>
                <div style={{ color: '#4ade80', fontSize: '13px' }}>Revenue: {fmt(result.simulated_trajectory.projected_revenue)}</div>
                <div style={{ color: '#60a5fa', fontSize: '13px' }}>Cash: {fmt(result.simulated_trajectory.projected_cash_balance)}</div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.04)', padding: '12px', borderRadius: '8px' }}>
                <div style={{ color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>Trajectory Delta</div>
                <div style={{ color: result.delta.demand_delta_units >= 0 ? '#4ade80' : '#f87171', marginTop: '6px', fontSize: '13px' }}>
                  Demand: {result.delta.demand_delta_units >= 0 ? `+${result.delta.demand_delta_units}` : result.delta.demand_delta_units}
                </div>
                <div style={{ color: result.delta.revenue_delta >= 0 ? '#4ade80' : '#f87171', fontSize: '13px' }}>
                  Revenue: {result.delta.revenue_delta >= 0 ? `+${fmt(result.delta.revenue_delta)}` : fmt(result.delta.revenue_delta)}
                </div>
                <div style={{ color: result.delta.cash_delta >= 0 ? '#4ade80' : '#f87171', fontSize: '13px' }}>
                  Cash: {result.delta.cash_delta >= 0 ? `+${fmt(result.delta.cash_delta)}` : fmt(result.delta.cash_delta)}
                </div>
              </div>
            </div>

            {result.assumptions && (
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '10px' }}>
                <div style={{ color: '#64748b', fontSize: '11px', textTransform: 'uppercase', marginBottom: '6px' }}>Assumptions</div>
                <ul style={{ margin: 0, paddingLeft: '18px', color: '#94a3b8', fontSize: '12px', lineHeight: 1.7 }}>
                  {Object.entries(result.assumptions).map(([k, v]) => (
                    <li key={k}><span style={{ textTransform: 'capitalize' }}>{humanize(k)}</span>: <span style={{ color: '#cbd5e1' }}>{String(v)}</span></li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
