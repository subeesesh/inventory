import React, { useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer
} from 'recharts';

// ── Role Gate (RBAC UI wrapper) ──────────────────────────────────────────────
export const RoleGate = ({ allowedRoles, currentRole, children }) => {
  if (allowedRoles.includes('all') || allowedRoles.includes(currentRole)) {
    return <>{children}</>;
  }
  return null;
};

// ── Layout Primitives ────────────────────────────────────────────────────────
export const Card = ({ children, title, className = "", style = {} }) => (
  <div className={`card ${className}`} style={{ background: 'rgba(20, 20, 25, 0.8)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '12px', padding: '20px', ...style }}>
    {title && <h3 style={{ margin: '0 0 15px 0', fontSize: '18px', fontWeight: '500', color: '#fff' }}>{title}</h3>}
    {children}
  </div>
);

export const StatCard = ({ title, value, icon, color = "#4ade80" }) => (
  <Card style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '24px' }}>
    <div>
      <div style={{ fontSize: '14px', color: '#94a3b8', marginBottom: '8px' }}>{title}</div>
      <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#fff' }}>{value}</div>
    </div>
    <div style={{ fontSize: '40px', color: color }}>
      {icon}
    </div>
  </Card>
);

// ── Data Display ─────────────────────────────────────────────────────────────
export const DataTable = ({ columns, data, onRowClick }) => (
  <div style={{ overflowX: 'auto' }}>
    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', color: '#cbd5e1' }}>
      <thead>
        <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          {columns.map((col, i) => (
            <th key={i} style={{ padding: '12px', fontWeight: '500', color: '#94a3b8' }}>{col.header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, i) => (
          <tr 
            key={row.id || i} 
            onClick={() => onRowClick && onRowClick(row)}
            style={{ 
              borderBottom: '1px solid rgba(255,255,255,0.05)', 
              cursor: onRowClick ? 'pointer' : 'default',
              transition: 'background 0.2s'
            }}
            onMouseOver={(e) => onRowClick && (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
            onMouseOut={(e) => onRowClick && (e.currentTarget.style.background = 'transparent')}
          >
            {columns.map((col, j) => (
              <td key={j} style={{ padding: '12px' }}>
                {col.render ? col.render(row) : row[col.accessor]}
              </td>
            ))}
          </tr>
        ))}
        {data.length === 0 && (
          <tr>
            <td colSpan={columns.length} style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
              No data available
            </td>
          </tr>
        )}
      </tbody>
    </table>
  </div>
);

export const StatusBadge = ({ status }) => {
  let bg = 'rgba(255,255,255,0.1)';
  let color = '#fff';
  
  if (status === 'received' || status === 'completed') {
    bg = 'rgba(74, 222, 128, 0.2)'; color = '#4ade80';
  } else if (status === 'ordered' || status === 'pending') {
    bg = 'rgba(250, 204, 21, 0.2)'; color = '#facc15';
  } else if (status === 'cancelled' || status === 'error') {
    bg = 'rgba(248, 113, 113, 0.2)'; color = '#f87171';
  }
  
  return (
    <span style={{ background: bg, color, padding: '4px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold', textTransform: 'uppercase' }}>
      {status}
    </span>
  );
};

// ── Overlays ─────────────────────────────────────────────────────────────────
export const Modal = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  
  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
      background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: '#1e1e24', border: '1px solid rgba(255,255,255,0.1)', 
        borderRadius: '12px', width: '100%', maxWidth: '600px',
        maxHeight: '90vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)'
      }}>
        <div style={{ padding: '20px', borderBottom: '1px solid rgba(255,255,255,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: '20px' }}>{title}</h2>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', fontSize: '24px' }}>&times;</button>
        </div>
        <div style={{ padding: '20px', overflowY: 'auto' }}>
          {children}
        </div>
      </div>
    </div>
  );
};

// ── Forms ────────────────────────────────────────────────────────────────────
export const Form = ({ onSubmit, children }) => (
  <form onSubmit={(e) => { e.preventDefault(); onSubmit(e); }} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
    {children}
  </form>
);

export const ProductSearchSelect = ({ products, onSelect, placeholder = "Search product..." }) => {
  const [search, setSearch] = useState('');
  
  const filtered = products.filter(p => 
    p.name.toLowerCase().includes(search.toLowerCase()) || 
    (p.sku && p.sku.toLowerCase().includes(search.toLowerCase())) ||
    (p.barcode && p.barcode.includes(search))
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <input 
        type="text" 
        value={search} 
        onChange={e => setSearch(e.target.value)} 
        placeholder={placeholder}
        style={{ padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
      />
      {search && (
        <div style={{ maxHeight: '200px', overflowY: 'auto', background: 'rgba(0,0,0,0.5)', borderRadius: '6px' }}>
          {filtered.map(p => (
            <div 
              key={p.id} 
              onClick={() => { onSelect(p); setSearch(''); }}
              style={{ padding: '10px', borderBottom: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer' }}
            >
              {p.name} {p.sku ? `(${p.sku})` : ''} - ${(p.unit_price || 0).toFixed(2)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── Charts ───────────────────────────────────────────────────────────────────
export const Chart = ({ data, type = "line", dataKeys = [], xAxisKey = "date", height = 300 }) => {
  const colors = ["#8b5cf6", "#3b82f6", "#10b981", "#f59e0b", "#ef4444"];
  const ChartComponent = type === "bar" ? BarChart : LineChart;
  const DataComponent = type === "bar" ? Bar : Line;

  return (
    <div style={{ width: '100%', height: height }}>
      <ResponsiveContainer>
        <ChartComponent data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
          <XAxis dataKey={xAxisKey} stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
          <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
          <RechartsTooltip 
            contentStyle={{ background: '#1e1e24', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px', color: '#fff' }}
            itemStyle={{ color: '#fff' }}
          />
          <Legend />
          {dataKeys.map((key, i) => (
            <DataComponent 
              key={key} 
              type="monotone" 
              dataKey={key} 
              stroke={colors[i % colors.length]} 
              fill={colors[i % colors.length]} 
              strokeWidth={2}
            />
          ))}
        </ChartComponent>
      </ResponsiveContainer>
    </div>
  );
};
