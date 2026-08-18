import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './Login';
import OwnerDashboard from './OwnerDashboard';
import MaintenanceDashboard from './MaintenanceDashboard';
import './App.css';

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
    if (!token) {
      return <Navigate to="/login" replace />;
    }
    if (allowedRoles && !allowedRoles.includes(role)) {
      return (
        <div style={{ color: 'white', padding: '50px', textAlign: 'center', background: 'var(--bg-color)', height: '100vh' }}>
          <h2>403 - Forbidden</h2>
          <p style={{ margin: '20px 0' }}>Your current role ({role}) does not have permission to view this page.</p>
          <button onClick={handleLogout} className="glow-btn">Return to Login</button>
        </div>
      );
    }
    return children;
  };

  return (
    <BrowserRouter>
      <Routes>
        <Route 
          path="/login" 
          element={token ? <Navigate to={role === 'owner' ? '/owner' : '/maintenance'} replace /> : <Login onLogin={handleLogin} />} 
        />
        
        <Route 
          path="/owner" 
          element={
            <ProtectedRoute allowedRoles={['owner']}>
              <OwnerDashboard token={token} onLogout={handleLogout} />
            </ProtectedRoute>
          } 
        />
        
        <Route 
          path="/maintenance" 
          element={
            <ProtectedRoute allowedRoles={['maintenance']}>
              <MaintenanceDashboard token={token} onLogout={handleLogout} />
            </ProtectedRoute>
          } 
        />

        <Route 
          path="/" 
          element={<Navigate to={token ? (role === 'owner' ? '/owner' : '/maintenance') : '/login'} replace />} 
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
