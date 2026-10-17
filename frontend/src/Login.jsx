import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const ROLE_OPTIONS = [
  { value: 'owner', label: 'Store Owner' },
  { value: 'cashier', label: 'Cashier / POS Operator' },
  { value: 'inventory_manager', label: 'Inventory Manager' },
  { value: 'procurement_officer', label: 'Procurement Officer' },
  { value: 'finance_officer', label: 'Finance Officer' },
];

function Login({ onLogin }) {
  const [mode, setMode] = useState('register'); // 'register' or 'login'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('owner');
  const [storeName, setStoreName] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (mode === 'register') {
        const res = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, role, store_name: storeName }),
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Registration failed');
        }

        const data = await res.json();
        onLogin(data.access_token, data.role);
        navigate(data.role === 'cashier' ? '/pos' : '/dashboard');
      } else {
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: formData.toString(),
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Invalid credentials');
        }

        const data = await res.json();
        onLogin(data.access_token, data.role);
        navigate(data.role === 'cashier' ? '/pos' : '/dashboard');
      }
    } catch (err) {
      setError(err.message || 'Action failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: 'var(--bg-color)', padding: '20px' }}>
      <div className="login-card glass" style={{ padding: '36px', width: '380px', borderRadius: '12px', boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
        
        {/* Toggle tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.1)', marginBottom: '24px' }}>
          <button
            onClick={() => { setMode('register'); setError(null); }}
            style={{
              flex: 1, padding: '12px', background: 'transparent', border: 'none', cursor: 'pointer',
              color: mode === 'register' ? '#4ade80' : '#64748b', fontWeight: 'bold', fontSize: '15px',
              borderBottom: mode === 'register' ? '2px solid #4ade80' : 'none',
            }}
          >
            Register Account
          </button>
          <button
            onClick={() => { setMode('login'); setError(null); }}
            style={{
              flex: 1, padding: '12px', background: 'transparent', border: 'none', cursor: 'pointer',
              color: mode === 'login' ? '#4ade80' : '#64748b', fontWeight: 'bold', fontSize: '15px',
              borderBottom: mode === 'login' ? '2px solid #4ade80' : 'none',
            }}
          >
            Log In
          </button>
        </div>

        <h3 style={{ textAlign: 'center', marginBottom: '20px', fontSize: '18px', color: '#e2e8f0' }}>
          {mode === 'register' ? 'Create New Account with Role' : 'Control Tower Login'}
        </h3>

        {error && <div style={{ color: '#f87171', background: 'rgba(248,113,113,0.15)', border: '1px solid #f87171', padding: '10px', borderRadius: '6px', marginBottom: '16px', fontSize: '13px', textAlign: 'center' }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {mode === 'register' && (
            <div>
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: '#94a3b8' }}>Store / Business Name</label>
              <input
                type="text"
                value={storeName}
                onChange={(e) => setStoreName(e.target.value)}
                placeholder="My Retail Store"
                style={inputStyle}
              />
            </div>
          )}

          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: '#94a3b8' }}>Email Address *</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="user@example.com"
              style={inputStyle}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: '#94a3b8' }}>Password *</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              style={inputStyle}
            />
          </div>

          {mode === 'register' && (
            <div>
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: '#94a3b8' }}>Select Role *</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                style={{ ...inputStyle, background: '#1a1a2e', color: '#fff' }}
              >
                {ROLE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: '10px', padding: '14px', borderRadius: '8px', background: '#4ade80', color: '#0f172a',
              fontWeight: 'bold', fontSize: '15px', border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Processing…' : (mode === 'register' ? 'Create Account' : 'Log In')}
          </button>
        </form>

        <p style={{ marginTop: '24px', fontSize: '12px', color: '#64748b', textAlign: 'center', lineHeight: 1.5 }}>
          {mode === 'register' ? (
            <>Already have an account? <span onClick={() => setMode('login')} style={{ color: '#4ade80', cursor: 'pointer', textDecoration: 'underline' }}>Log in here</span></>
          ) : (
            <>Need an account? <span onClick={() => setMode('register')} style={{ color: '#4ade80', cursor: 'pointer', textDecoration: 'underline' }}>Register here</span></>
          )}
        </p>
      </div>
    </div>
  );
}

const inputStyle = {
  width: '100%', padding: '11px 14px', borderRadius: '6px',
  border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.05)',
  color: '#fff', fontSize: '14px', boxSizing: 'border-box',
};

export default Login;
