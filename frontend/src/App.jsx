import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './Login';
import { Layout } from './components/Layout';
import { Dashboard, POS, Inventory, Purchases, Customers, AiAssistant } from './pages';
import { ToastProvider } from './components/ToastProvider';
import './App.css';
import './index.css';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [role, setRole] = useState(localStorage.getItem('role'));

  const handleLogin = (newToken, newRole) => {
    localStorage.setItem('token', newToken);
    localStorage.setItem('role', newRole);
    setToken(newToken);
    setRole(newRole);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    setToken(null);
    setRole(null);
  };

  const ProtectedRoute = ({ children, allowedRoles }) => {
    if (!token) return <Navigate to="/login" replace />;
    if (allowedRoles && !allowedRoles.includes(role)) {
      return (
        <div style={{ padding: '50px', textAlign: 'center', color: '#f87171' }}>
          <h2>403 - Forbidden</h2>
          <p>Your role ({role}) cannot access this area.</p>
        </div>
      );
    }
    return children;
  };

  return (
    <ToastProvider>
      <BrowserRouter>
      <Routes>
        <Route 
          path="/login" 
          element={token ? <Navigate to="/dashboard" replace /> : <Login onLogin={handleLogin} />} 
        />
        
        {/* Main Application Routes inside Layout */}
        <Route path="/" element={token ? <Layout role={role} onLogout={handleLogout} /> : <Navigate to="/login" />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          
          <Route path="dashboard" element={
            <ProtectedRoute allowedRoles={['owner', 'inventory_manager', 'procurement_officer', 'finance_officer']}>
              <Dashboard token={token} role={role} />
            </ProtectedRoute>
          } />
          
          <Route path="pos" element={
            <ProtectedRoute allowedRoles={['owner', 'cashier']}>
              <POS token={token} role={role} />
            </ProtectedRoute>
          } />
          
          <Route path="inventory" element={
            <ProtectedRoute allowedRoles={['owner', 'cashier', 'inventory_manager', 'procurement_officer', 'finance_officer']}>
              <Inventory token={token} role={role} />
            </ProtectedRoute>
          } />
          
          <Route path="purchases" element={
            <ProtectedRoute allowedRoles={['owner', 'procurement_officer', 'finance_officer']}>
              <Purchases token={token} role={role} />
            </ProtectedRoute>
          } />
          
          <Route path="customers" element={
            <ProtectedRoute allowedRoles={['owner', 'cashier', 'finance_officer']}>
              <Customers token={token} />
            </ProtectedRoute>
          } />
          
          <Route path="ai" element={
            <ProtectedRoute allowedRoles={['owner', 'inventory_manager', 'procurement_officer', 'finance_officer']}>
              <AiAssistant token={token} />
            </ProtectedRoute>
          } />
        </Route>
      </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
