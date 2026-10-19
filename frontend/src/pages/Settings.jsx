import { useEffect, useState } from 'react';
import clsx from 'clsx';
import { Check, Monitor, Moon, Sun, Target, UserRound } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { useSession, useTheme } from '../core/session';
import { BUSINESS_GOALS, ROLES, can } from '../core/constants';
import { Button, Card, ErrorNote, PageHeader, Skeleton } from '../components/ui';
import { useToast } from '../components/Toast';

export default function Settings() {
  const { role, email } = useSession();
  const { theme, setTheme } = useTheme();
  const { showToast } = useToast();
  const tenant = useApi(can(role, 'dashboard') ? '/tenants/me' : null);
  const [goal, setGoal] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (tenant.data) setGoal(tenant.data.business_goal); }, [tenant.data]);

  const saveGoal = async () => {
    setSaving(true);
    try {
      await api.post('/tenants/goal', { business_goal: goal });
      showToast('Business goal updated — new decisions will use it', 'success');
      tenant.reload();
    } catch (e) { showToast(e.message, 'error'); } finally { setSaving(false); }
  };

  const themes = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
  ];

  return (
    <>
      <PageHeader title="Settings" description="Your account, appearance and the business goal AMDIE optimises for." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {can(role, 'dashboard') && (
          <Card title="Business goal" subtitle="AMDIE adjusts every fused decision towards this goal" icon={Target} className="xl:row-span-2">
            {tenant.loading ? <Skeleton className="h-60" /> : (
              <div className="space-y-3">
                <ErrorNote>{tenant.error}</ErrorNote>
                {Object.entries(BUSINESS_GOALS).map(([k, g]) => (
                  <button
                    key={k}
                    disabled={role !== 'owner'}
                    onClick={() => setGoal(k)}
                    className={clsx('flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-colors disabled:cursor-default',
                      goal === k ? 'border-primary bg-primary-soft/60' : 'border-line hover:border-line-strong')}
                  >
                    <span className={clsx('mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border', goal === k ? 'border-primary bg-primary text-on-primary' : 'border-line-strong')}>
                      {goal === k && <Check className="size-3" />}
                    </span>
                    <span>
                      <span className="block text-sm font-medium text-ink">{g.label}</span>
                      <span className="block text-xs text-muted">{g.hint}</span>
                    </span>
                  </button>
                ))}
                {role === 'owner' ? (
                  <div className="flex justify-end pt-2">
                    <Button onClick={saveGoal} loading={saving} disabled={!goal || goal === tenant.data?.business_goal}>Save goal</Button>
                  </div>
                ) : (
                  <p className="text-xs text-muted">Only the store owner can change the business goal.</p>
                )}
              </div>
            )}
          </Card>
        )}

        <Card title="Appearance" icon={Monitor}>
          <div className="grid grid-cols-2 gap-3">
            {themes.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => setTheme(value)}
                className={clsx('flex items-center gap-3 rounded-xl border p-4 transition-colors',
                  theme === value ? 'border-primary bg-primary-soft/60' : 'border-line hover:border-line-strong')}
              >
                <Icon className={clsx('size-5', theme === value ? 'text-primary' : 'text-muted')} />
                <span className="text-sm font-medium text-ink">{label}</span>
              </button>
            ))}
          </div>
        </Card>

        <Card title="Account" icon={UserRound}>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between gap-4"><dt className="text-muted">Email</dt><dd className="truncate font-medium text-ink">{email || '—'}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-muted">Role</dt><dd className="font-medium text-ink">{ROLES[role] || role}</dd></div>
            {tenant.data && <div className="flex justify-between gap-4"><dt className="text-muted">Store</dt><dd className="font-medium text-ink">{tenant.data.name}</dd></div>}
            {tenant.data && <div className="flex justify-between gap-4"><dt className="text-muted">HR agent</dt><dd className="font-medium text-ink">{tenant.data.enables_hr_agent ? 'Enabled' : 'Disabled'}</dd></div>}
          </dl>
        </Card>
      </div>
    </>
  );
}
