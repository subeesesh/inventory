import { useMemo, useState } from 'react';
import { Check, Radar, RefreshCw, ShieldCheck, X, Zap } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { useSession } from '../core/session';
import { ACTION_STATUS, SEVERITY_TONE } from '../core/constants';
import { dateTime, humanize, num } from '../core/format';
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, Segmented, Skeleton, StatCard } from '../components/ui';
import { useToast } from '../components/Toast';

export default function Monitoring() {
  const { role } = useSession();
  const { showToast } = useToast();
  const events = useApi('/tenants/monitoring/events', { initial: [] });
  const actions = useApi('/tenants/automation/actions', { initial: [] });
  const twin = useApi('/tenants/twin');
  const [scanning, setScanning] = useState(false);
  const [severity, setSeverity] = useState('all');
  const [busy, setBusy] = useState(null);

  const entityName = (e) => {
    if (e.entity_type === 'product') return twin.data?.inventory?.find(p => p.product_id === e.entity_id)?.name || e.entity_id;
    if (e.entity_type === 'supplier') return twin.data?.supply_network?.find(s => s.supplier_id === e.entity_id)?.name || 'Supplier';
    return humanize(e.entity_type);
  };

  const counts = useMemo(() => {
    const c = { critical: 0, warning: 0, info: 0 };
    events.data.forEach(e => { c[e.severity] = (c[e.severity] || 0) + 1; });
    return c;
  }, [events.data]);
  const shown = events.data.filter(e => severity === 'all' || e.severity === severity);
  const pending = actions.data.filter(a => a.status === 'pending_review');

  const scan = async () => {
    setScanning(true);
    try {
      const r = await api.post('/tenants/monitoring/scan');
      showToast(`Scan complete — ${r.events_detected} open alert${r.events_detected === 1 ? '' : 's'}`, 'success');
      await Promise.all([events.reload(), actions.reload()]);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setScanning(false);
    }
  };

  const review = async (id, approve) => {
    setBusy(id);
    try {
      await api.post(`/tenants/automation/actions/${id}/review`, { approve });
      showToast(approve ? 'Action approved' : 'Action rejected', 'success');
      await actions.reload();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Monitoring & alerts"
        description="The monitoring engine scans the twin every five minutes for stock depletion, cash shortfalls, sales spikes and unreliable suppliers. Stock alerts trigger an AMDIE reorder analysis automatically."
        actions={<Button icon={RefreshCw} onClick={scan} loading={scanning}>Scan now</Button>}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Open alerts" value={num(events.data.length)} icon={Radar} tone="primary" loading={events.loading} />
        <StatCard label="Critical" value={num(counts.critical)} icon={Zap} tone={counts.critical ? 'danger' : 'success'} loading={events.loading} />
        <StatCard label="Warnings" value={num(counts.warning)} icon={Radar} tone="warning" loading={events.loading} />
        <StatCard label="Awaiting your review" value={num(pending.length)} icon={ShieldCheck} tone={pending.length ? 'warning' : 'success'} loading={actions.loading} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card
          title="Open alerts"
          padded={false}
          actions={(
            <Segmented
              value={severity}
              onChange={setSeverity}
              options={[{ value: 'all', label: 'All' }, { value: 'critical', label: 'Critical' }, { value: 'warning', label: 'Warning' }, { value: 'info', label: 'Info' }]}
            />
          )}
        >
          <ErrorNote className="m-4">{events.error}</ErrorNote>
          {events.loading ? <div className="p-5"><Skeleton className="h-64" /></div>
            : shown.length === 0 ? <Empty icon={ShieldCheck} title="No open alerts">Everything the monitor watches is within its limits.</Empty>
            : (
              <ul className="divide-y divide-line">
                {shown.map(e => (
                  <li key={e.id} className="flex items-center gap-4 px-5 py-3.5">
                    <span className={`size-2 shrink-0 rounded-full ${e.severity === 'critical' ? 'bg-danger' : e.severity === 'warning' ? 'bg-warning' : 'bg-info'}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink capitalize">{humanize(e.event_type)}</p>
                      <p className="truncate text-xs text-muted">{entityName(e)} · detected {dateTime(e.detected_at)}</p>
                    </div>
                    <Badge tone={SEVERITY_TONE[e.severity] || 'neutral'}>{e.severity}</Badge>
                  </li>
                ))}
              </ul>
            )}
        </Card>

        <Card title="Automated actions" subtitle="Routine actions are sent as notifications; high-impact ones wait for the owner" padded={false}>
          <ErrorNote className="m-4">{actions.error}</ErrorNote>
          {actions.loading ? <div className="p-5"><Skeleton className="h-64" /></div>
            : actions.data.length === 0 ? <Empty icon={Zap} title="No automated actions yet">When a stock alert triggers a reorder decision, the resulting action appears here.</Empty>
            : (
              <ul className="divide-y divide-line">
                {actions.data.map(a => {
                  const st = ACTION_STATUS[a.status] || { tone: 'neutral', label: humanize(a.status) };
                  return (
                    <li key={a.id} className="px-5 py-3.5">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-medium text-ink">{a.description}</p>
                        <Badge tone={st.tone}>{st.label}</Badge>
                      </div>
                      {a.policy_reason && <p className="mt-1 text-xs text-muted">{a.policy_reason}</p>}
                      {a.status === 'pending_review' && role === 'owner' && (
                        <div className="mt-3 flex gap-2">
                          <Button size="sm" variant="success" icon={Check} loading={busy === a.id} onClick={() => review(a.id, true)}>Approve</Button>
                          <Button size="sm" variant="secondary" icon={X} disabled={busy === a.id} onClick={() => review(a.id, false)}>Reject</Button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
        </Card>
      </div>
    </>
  );
}
