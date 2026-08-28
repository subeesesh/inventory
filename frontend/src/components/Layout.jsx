import React from 'react';
import { NavLink, useNavigate, Outlet } from 'react-router-dom';

const navConfig = [
  { path: '/dashboard', label: 'Dashboard', icon: '📊', roles: ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'] },
  { path: '/pos', label: 'POS & Billing', icon: '🛒', roles: ['owner', 'cashier'] },
  { path: '/inventory', label: 'Inventory & Products', icon: '📦', roles: ['owner', 'cashier', 'inventory_manager', 'procurement_officer', 'finance_officer'] },
  { path: '/purchases', label: 'Purchases & Suppliers', icon: '🚚', roles: ['owner', 'procurement_officer', 'finance_officer'] },
  { path: '/customers', label: 'Customers', icon: '👥', roles: ['owner', 'cashier', 'finance_officer'] },
  { path: '/ai', label: 'AI Assistant', icon: '✨', roles: ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'] },
];

export const Layout = ({ role, onLogout }) => {
  const navigate = useNavigate();
  
  const visibleNavs = navConfig.filter(n => n.roles.includes(role));

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-color)', color: '#f8fafc' }}>
      
      {/* Sidebar */}
      <div style={{ 
        width: '260px', 
        background: 'rgba(20, 20, 25, 0.95)', 
        borderRight: '1px solid rgba(255,255,255,0.05)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 0'
      }}>
        <div style={{ padding: '0 24px', marginBottom: '32px' }}>
          <h1 style={{ fontSize: '20px', margin: 0, fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '24px' }}>🔮</span> 
            Control Tower
          </h1>
          <div style={{ marginTop: '8px', fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Role: <span style={{ color: '#4ade80' }}>{role}</span>
          </div>
        </div>

        <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px', padding: '0 12px' }}>
          {visibleNavs.map(nav => (
            <NavLink 
              key={nav.path} 
              to={nav.path}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: '12px',
                padding: '12px 16px', borderRadius: '8px',
                textDecoration: 'none',
                color: isActive ? '#fff' : '#94a3b8',
                background: isActive ? 'rgba(74, 222, 128, 0.1)' : 'transparent',
                borderLeft: isActive ? '3px solid #4ade80' : '3px solid transparent',
                fontWeight: isActive ? '500' : 'normal',
                transition: 'all 0.2s'
              })}
            >
              <span style={{ fontSize: '18px' }}>{nav.icon}</span>
              {nav.label}
            </NavLink>
          ))}
        </nav>

        <div style={{ padding: '0 24px' }}>
          <button 
            onClick={() => {
              onLogout();
              navigate('/login');
            }}
            style={{ 
              width: '100%', padding: '12px', borderRadius: '8px',
              background: 'rgba(248, 113, 113, 0.1)', color: '#f87171',
              border: '1px solid rgba(248, 113, 113, 0.2)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
            }}
          >
            <span>🚪</span> Logout
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px' }}>
        <Outlet />
      </div>
      
    </div>
  );
};
