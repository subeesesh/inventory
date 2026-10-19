import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ShieldOff } from 'lucide-react';
import { SessionProvider, ThemeProvider, useSession } from './core/session';
import { can } from './core/constants';
import { ToastProvider } from './components/Toast';
import { AppShell, firstAllowedPath } from './components/AppShell';
import { Empty, Spinner } from './components/ui';
import Login from './pages/Login';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Twin = lazy(() => import('./pages/Twin'));
const Decisions = lazy(() => import('./pages/Decisions'));
const Simulator = lazy(() => import('./pages/Simulator'));
const Copilot = lazy(() => import('./pages/Copilot'));
const Monitoring = lazy(() => import('./pages/Monitoring'));
const POS = lazy(() => import('./pages/POS'));
const Inventory = lazy(() => import('./pages/Inventory'));
const Purchases = lazy(() => import('./pages/Purchases'));
const Customers = lazy(() => import('./pages/Customers'));
const Compliance = lazy(() => import('./pages/Compliance'));
const Settings = lazy(() => import('./pages/Settings'));

const PAGES = [
  ['dashboard', Dashboard], ['twin', Twin], ['decisions', Decisions], ['simulator', Simulator],
  ['copilot', Copilot], ['monitoring', Monitoring], ['pos', POS], ['inventory', Inventory],
  ['purchases', Purchases], ['customers', Customers], ['compliance', Compliance], ['settings', Settings],
];

function Guard({ area, children }) {
  const { role } = useSession();
  if (!can(role, area)) {
    return <Empty icon={ShieldOff} title="Not available for your role">Ask the store owner if you need access to this area.</Empty>;
  }
  return children;
}

function Routed() {
  const { token, role } = useSession();
  const home = firstAllowedPath(role);
  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to={home} replace /> : <Login />} />
      <Route element={token ? <AppShell /> : <Navigate to="/login" replace />}>
        <Route index element={<Navigate to={home} replace />} />
        {PAGES.map(([area, Page]) => (
          <Route
            key={area}
            path={area}
            element={(
              <Guard area={area}>
                <Suspense fallback={<div className="grid h-64 place-items-center"><Spinner /></div>}>
                  <Page />
                </Suspense>
              </Guard>
            )}
          />
        ))}
        {/* Old links from the previous UI */}
        <Route path="ai" element={<Navigate to="/copilot" replace />} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <SessionProvider>
        <ToastProvider>
          <BrowserRouter>
            <Routed />
          </BrowserRouter>
        </ToastProvider>
      </SessionProvider>
    </ThemeProvider>
  );
}
