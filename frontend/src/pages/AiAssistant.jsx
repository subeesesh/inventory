import React, { useState, useEffect, useRef } from 'react';
import { Card } from '../components/ui';
import api from '../api';

const TYPE_COLOR = {
  reorder_quantity:  '#60a5fa',
  price_adjustment:  '#c084fc',
  promotion_trigger: '#fbbf24',
};

export const AiAssistant = () => {
  const [decisions, setDecisions]   = useState([]);
  const [messages, setMessages]     = useState([
    { role: 'assistant', text: 'Hello! I am AMDIE, your AI Multi-Agent Decision Intelligence Engine. Ask me about inventory levels, pricing decisions, procurement, or any past analysis.' },
  ]);
  const [input, setInput]           = useState('');
  const [loading, setLoading]       = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    api.get('/tenants/decisions')
      .then(d => setDecisions((d || []).slice(0, 8)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text }]);
    setLoading(true);
    try {
      const res = await api.post('/tenants/copilot/chat', {
        messages: [{ role: 'user', content: text }],
      });
      setMessages(prev => [...prev, { role: 'assistant', text: res.reply || res.response || JSON.stringify(res) }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', text: `⚠️ Error: ${e.message}`, isError: true }]);
    } finally {
      setLoading(false);
    }
  };

  const handleDecisionClick = (d) => {
    const q = `Explain decision ${d.id} for product ${d.product_id} on ${d.date}`;
    handleSend(q);
  };

  return (
    <div style={{ display: 'flex', gap: '24px', height: 'calc(100vh - 120px)' }}>
      {/* ── Left: Recent decisions ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0', minWidth: '260px', maxWidth: '320px' }}>
        <Card title="Recent AI Decisions" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {decisions.length === 0
            ? <p style={{ color: '#64748b', fontSize: '13px', textAlign: 'center' }}>No decisions yet.</p>
            : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', flex: 1 }}>
                {decisions.map(d => {
                  const color = TYPE_COLOR[d.decision_type] || '#94a3b8';
                  return (
                    <div
                      key={d.id}
                      onClick={() => handleDecisionClick(d)}
                      style={{
                        background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
                        borderLeft: `3px solid ${color}`, borderRadius: '8px', padding: '10px 12px',
                        cursor: 'pointer', transition: 'background 0.15s',
                      }}
                      onMouseOver={e => e.currentTarget.style.background = 'rgba(255,255,255,0.08)'}
                      onMouseOut={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span style={{ background: `${color}22`, color, padding: '2px 7px', borderRadius: '10px', fontSize: '10px', fontWeight: 600 }}>
                          {(d.decision_type || '').replace(/_/g, ' ')}
                        </span>
                        {d.conflict_detected && <span title="Conflict detected" style={{ fontSize: '12px' }}>⚠️</span>}
                      </div>
                      <div style={{ fontFamily: 'monospace', fontSize: '11px', color: '#94a3b8', marginBottom: '4px' }}>
                        {(d.product_id || '').slice(0, 14)}…
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ color: '#e2e8f0', fontSize: '13px', fontWeight: 600 }}>
                          {typeof d.fused_recommendation === 'number' ? d.fused_recommendation.toFixed(2) : '—'}
                        </span>
                        <span style={{ color: '#475569', fontSize: '11px' }}>
                          {d.date ? new Date(d.date).toLocaleDateString() : '—'}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          <p style={{ color: '#475569', fontSize: '11px', textAlign: 'center', marginTop: '12px' }}>Click a card to ask AMDIE about it</p>
        </Card>
      </div>

      {/* ── Right: Chat ── */}
      <div style={{ flex: 2, display: 'flex', flexDirection: 'column' }}>
        <Card title="AMDIE Copilot Chat" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '14px', paddingRight: '4px', paddingBottom: '8px' }}>
            {messages.map((m, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '78%', padding: '12px 16px', borderRadius: '12px',
                  background: m.role === 'user'
                    ? 'linear-gradient(135deg, #6d28d9, #8b5cf6)'
                    : (m.isError ? 'rgba(248,113,113,0.15)' : 'rgba(255,255,255,0.05)'),
                  color: m.isError ? '#fca5a5' : '#e2e8f0',
                  border: m.role === 'user' ? 'none' : '1px solid rgba(255,255,255,0.08)',
                  lineHeight: 1.55, fontSize: '14px', whiteSpace: 'pre-wrap',
                }}>
                  {m.text}
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div style={{ padding: '12px 18px', borderRadius: '12px', background: 'rgba(255,255,255,0.05)', color: '#64748b', border: '1px solid rgba(255,255,255,0.08)', fontSize: '14px' }}>
                  <span style={{ animation: 'pulse 1.5s infinite' }}>Thinking…</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px', marginTop: '12px', display: 'flex', gap: '10px' }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder="Ask about stock levels, pricing decisions, procurement…"
              disabled={loading}
              style={{ flex: 1, padding: '13px 16px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: '14px' }}
            />
            <button
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
              style={{
                padding: '0 24px', borderRadius: '8px', fontWeight: 'bold', fontSize: '15px', border: 'none', cursor: 'pointer',
                background: loading || !input.trim() ? 'rgba(139,92,246,0.3)' : '#8b5cf6', color: '#fff',
              }}
            >
              Send
            </button>
          </div>
        </Card>
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
    </div>
  );
};
