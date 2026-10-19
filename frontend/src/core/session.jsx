import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { clearSession, getToken } from './api';

const SessionContext = createContext(null);
const ThemeContext = createContext(null);

function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function writeStored(key, value) {
  try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
}

export function SessionProvider({ children }) {
  const [token, setToken] = useState(getToken);
  const [role, setRole] = useState(() => readStored('role'));
  const [email, setEmail] = useState(() => readStored('email'));

  const login = useCallback(({ access_token, role: r }, userEmail) => {
    writeStored('token', access_token);
    writeStored('role', r);
    if (userEmail) writeStored('email', userEmail);
    setToken(access_token);
    setRole(r);
    setEmail(userEmail || null);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    try { localStorage.removeItem('email'); } catch { /* storage unavailable */ }
    setToken(null);
    setRole(null);
    setEmail(null);
  }, []);

  const value = useMemo(() => ({ token, role, email, login, logout }), [token, role, email, login, logout]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export const useSession = () => useContext(SessionContext);

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => document.documentElement.getAttribute('data-theme') || 'light');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    writeStored('theme', theme);
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme, toggle: () => setTheme(t => (t === 'dark' ? 'light' : 'dark')) }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);

// Recharts draws SVG attributes, which cannot use CSS variables — resolve them per theme
export function useChartColors() {
  const { theme } = useTheme();
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    return {
      primary: v('--primary'),
      success: v('--success'),
      warning: v('--warning'),
      danger: v('--danger'),
      info: v('--info'),
      violet: v('--violet'),
      grid: v('--border'),
      axis: v('--muted'),
      surface: v('--surface'),
      text: v('--text'),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}
