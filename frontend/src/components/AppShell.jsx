import { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import {
  Activity, Boxes, BrainCircuit, ClipboardCheck, FlaskConical, LayoutDashboard, LogOut, Menu,
  MessageSquareText, Moon, Network, Radar, Settings, ShoppingCart, Sun, Truck, Users, X,
} from 'lucide-react';
import { useSession, useTheme } from '../core/session';
import { ROLES, can } from '../core/constants';
import { useApi } from '../core/useApi';

const NAV = [
  { group: 'Overview', items: [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, area: 'dashboard' },
    { to: '/twin', label: 'Business Twin', icon: Network, area: 'twin' },
  ]},
  { group: 'Decision intelligence', items: [
    { to: '/decisions', label: 'Decision Studio', icon: BrainCircuit, area: 'decisions' },
    { to: '/simulator', label: 'What-if Simulator', icon: FlaskConical, area: 'simulator' },
    { to: '/copilot', label: 'Copilot', icon: MessageSquareText, area: 'copilot' },
    { to: '/monitoring', label: 'Monitoring & Alerts', icon: Radar, area: 'monitoring' },
  ]},
  { group: 'Operations', items: [
    { to: '/pos', label: 'Point of Sale', icon: ShoppingCart, area: 'pos' },
    { to: '/inventory', label: 'Inventory', icon: Boxes, area: 'inventory' },
    { to: '/purchases', label: 'Purchases & Suppliers', icon: Truck, area: 'purchases' },
    { to: '/customers', label: 'Customers', icon: Users, area: 'customers' },
  ]},
  { group: 'Governance', items: [
    { to: '/compliance', label: 'Compliance', icon: ClipboardCheck, area: 'compliance' },
    { to: '/settings', label: 'Settings', icon: Settings, area: 'settings' },
  ]},
];

export const firstAllowedPath = (role) => {
  for (const g of NAV) for (const i of g.items) if (can(role, i.area)) return i.to;
  return '/settings';
};

export function ThemeToggle({ className }) {
  const { theme, toggle } = useTheme();
  const dark = theme === 'dark';
  return (
    <button
      onClick={toggle}
      className={clsx('grid size-9 place-items-center rounded-lg border border-line bg-surface text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink', className)}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={dark ? 'Light theme' : 'Dark theme'}
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid size-9 place-items-center rounded-xl bg-primary text-on-primary">
        <Activity className="size-5" />
      </span>
      <div className="leading-tight">
        <p className="text-sm font-semibold text-ink">BizTwin AI</p>
        <p className="text-[11px] text-muted">Business Control Tower</p>
      </div>
    </div>
  );
}

function Sidebar({ role, onNavigate }) {
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
      {NAV.map(g => {
        const items = g.items.filter(i => can(role, i.area));
        if (!items.length) return null;
        return (
          <div key={g.group}>
            <p className="mb-1.5 px-3 text-[11px] font-semibold tracking-wide text-muted uppercase">{g.group}</p>
            <div className="space-y-0.5">
              {items.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={onNavigate}
                  className={({ isActive }) => clsx(
                    'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive ? 'bg-primary-soft font-medium text-primary' : 'text-ink-2 hover:bg-surface-2 hover:text-ink',
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  <span className="truncate">{label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

export function AppShell() {
  const { role, email, logout } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: tenant } = useApi(can(role, 'dashboard') ? '/tenants/me' : null);

  const handleLogout = () => { logout(); navigate('/login', { replace: true }); };

  const current = NAV.flatMap(g => g.items).find(i => location.pathname.startsWith(i.to));

  const userBlock = (
    <div className="border-t border-line p-3">
      <div className="flex items-center gap-3 rounded-lg px-2 py-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-xs font-semibold text-ink-2 uppercase">
          {(email || ROLES[role] || '?').slice(0, 2)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{email || 'Signed in'}</p>
          <p className="truncate text-xs text-muted">{ROLES[role] || role}</p>
        </div>
        <button onClick={handleLogout} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-danger-soft hover:text-danger" title="Log out" aria-label="Log out">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <aside className="no-print hidden w-64 shrink-0 flex-col border-r border-line bg-surface lg:flex">
        <div className="flex h-16 items-center border-b border-line px-5"><Brand /></div>
        <Sidebar role={role} />
        {userBlock}
      </aside>

      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 flex bg-black/40 lg:hidden" onClick={() => setMobileOpen(false)}>
          <aside className="animate-in flex w-72 flex-col bg-surface" onClick={e => e.stopPropagation()}>
            <div className="flex h-16 items-center justify-between border-b border-line px-5">
              <Brand />
              <button onClick={() => setMobileOpen(false)} className="text-muted" aria-label="Close menu"><X className="size-5" /></button>
            </div>
            <Sidebar role={role} onNavigate={() => setMobileOpen(false)} />
            {userBlock}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface/80 px-4 backdrop-blur sm:px-6">
          <button onClick={() => setMobileOpen(true)} className="grid size-9 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 lg:hidden" aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink">{current?.label || 'BizTwin AI'}</p>
            {tenant && <p className="truncate text-xs text-muted">{tenant.name}</p>}
          </div>
          <ThemeToggle />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
