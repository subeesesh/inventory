import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, BrainCircuit, FlaskConical, Network, ShieldCheck } from 'lucide-react';
import api from '../core/api';
import { useSession } from '../core/session';
import { ROLES } from '../core/constants';
import { Button, ErrorNote, Field, Input, Segmented, Select } from '../components/ui';
import { ThemeToggle, firstAllowedPath } from '../components/AppShell';

const HIGHLIGHTS = [
  { icon: Network, title: 'Business digital twin', text: 'One live view of stock, sales, cash, suppliers and staff.' },
  { icon: BrainCircuit, title: 'Nine cooperating AI agents', text: 'AMDIE weighs each agent by its track record and fuses their advice.' },
  { icon: FlaskConical, title: 'Safe what-if testing', text: 'Simulate price changes, delays and demand shocks before acting.' },
  { icon: ShieldCheck, title: 'Owner stays in control', text: 'Routine actions are notified; high-impact ones wait for approval.' },
];

export default function Login() {
  const { login } = useSession();
  const navigate = useNavigate();
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ email: '', password: '', role: 'owner', store: '' });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = mode === 'register'
        ? await api.post('/auth/register', { email: form.email, password: form.password, role: form.role, store_name: form.store || undefined })
        : await api.postForm('/auth/login', { username: form.email, password: form.password });
      login(data, form.email);
      navigate(firstAllowedPath(data.role), { replace: true });
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      {/* Story panel */}
      <section className="relative hidden flex-col justify-between overflow-hidden bg-hero p-12 text-white lg:flex">
        <div className="pointer-events-none absolute -top-32 -right-32 size-96 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-40 -left-20 size-[28rem] rounded-full bg-white/5" />
        <div className="relative flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-white/15"><Activity className="size-5" /></span>
          <div>
            <p className="font-semibold">BizTwin AI</p>
            <p className="text-xs text-white/70">A multi-agent business control tower</p>
          </div>
        </div>
        <div className="relative max-w-lg">
          <h1 className="text-3xl leading-tight font-semibold">Every decision, weighed by every part of your business.</h1>
          <div className="mt-10 grid gap-5">
            {HIGHLIGHTS.map(({ icon: Icon, title, text }) => (
              <div key={title} className="flex gap-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/15"><Icon className="size-5" /></span>
                <div>
                  <p className="font-medium">{title}</p>
                  <p className="text-sm text-white/75">{text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-white/60">Dr. N.G.P. Institute of Technology · Department of AI &amp; Data Science</p>
      </section>

      {/* Form */}
      <section className="flex flex-col bg-bg">
        <div className="flex justify-end p-4"><ThemeToggle /></div>
        <div className="flex flex-1 items-center justify-center px-4 pb-16">
          <div className="w-full max-w-sm">
            <div className="mb-8 lg:hidden">
              <span className="mb-3 grid size-11 place-items-center rounded-xl bg-primary text-on-primary"><Activity className="size-5" /></span>
              <p className="font-semibold text-ink">BizTwin AI</p>
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-ink">{mode === 'login' ? 'Welcome back' : 'Create your store'}</h2>
            <p className="mt-1 mb-6 text-sm text-muted">
              {mode === 'login' ? 'Sign in to your control tower.' : 'Set up an account and choose your role.'}
            </p>

            <Segmented
              className="mb-6 w-full"
              value={mode}
              onChange={(m) => { setMode(m); setError(null); }}
              options={[{ value: 'login', label: 'Sign in' }, { value: 'register', label: 'Register' }]}
            />

            <form onSubmit={submit} className="space-y-4">
              {mode === 'register' && (
                <Field label="Store or business name">
                  <Input value={form.store} onChange={set('store')} placeholder="My Retail Store" />
                </Field>
              )}
              <Field label="Email">
                <Input type="email" required autoComplete="email" value={form.email} onChange={set('email')} placeholder="you@store.com" />
              </Field>
              <Field label="Password">
                <Input type="password" required autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={form.password} onChange={set('password')} placeholder="••••••••" />
              </Field>
              {mode === 'register' && (
                <Field label="Role">
                  <Select value={form.role} onChange={set('role')}>
                    {Object.entries(ROLES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                </Field>
              )}
              <ErrorNote>{error}</ErrorNote>
              <Button type="submit" size="lg" loading={loading} className="w-full">
                {mode === 'login' ? 'Sign in' : 'Create account'}
              </Button>
            </form>

            {mode === 'login' && (
              <p className="mt-6 rounded-lg border border-dashed border-line px-3 py-2.5 text-xs text-muted">
                Demo store: <span className="font-mono text-ink-2">owner@example.com</span> / <span className="font-mono text-ink-2">password</span>
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
