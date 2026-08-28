import React, { createContext, useContext, useState, useCallback } from 'react';

export const ToastContext = createContext(null);

const TYPE_STYLES = {
  success: { border: '#4ade80', icon: '✓' },
  error:   { border: '#f87171', icon: '✕' },
  info:    { border: '#60a5fa', icon: 'ℹ' },
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type = 'success') => {
    const id = Date.now() + Math.random();
    setToasts(prev => [{ id, message, type }, ...prev]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3500);
  }, []);

  const dismiss = (id) => setToasts(prev => prev.filter(t => t.id !== id));

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}

      {/* Toast container — bottom-right */}
      <div style={{
        position: 'fixed', bottom: '24px', right: '24px',
        display: 'flex', flexDirection: 'column', gap: '10px',
        zIndex: 9999, minWidth: '300px', maxWidth: '400px',
      }}>
        {toasts.map(t => {
          const s = TYPE_STYLES[t.type] || TYPE_STYLES.info;
          return (
            <div key={t.id} style={{
              background: '#1e1e2c',
              border: `1px solid ${s.border}`,
              borderLeft: `4px solid ${s.border}`,
              borderRadius: '8px',
              padding: '14px 16px',
              color: '#e2e8f0',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
              animation: 'slideInToast 0.25s ease',
            }}>
              <span style={{ color: s.border, fontWeight: 'bold', fontSize: '16px' }}>{s.icon}</span>
              <span style={{ flex: 1, fontSize: '14px' }}>{t.message}</span>
              <button
                onClick={() => dismiss(t.id)}
                style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '16px', lineHeight: 1, padding: '0 4px' }}
              >×</button>
            </div>
          );
        })}
      </div>

      <style>{`
        @keyframes slideInToast {
          from { opacity: 0; transform: translateX(40px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
}
