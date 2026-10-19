import { useMemo, useState } from 'react';
import { Boxes, Clock, Gauge, Network, ShieldAlert, Users, Wallet } from 'lucide-react';
import { useApi } from '../core/useApi';
import { date, humanize, money, moneyCompact, num, pct } from '../core/format';
import { Badge, Card, Empty, ErrorNote, Input, PageHeader, Progress, Segmented, Skeleton, StatCard, Table } from '../components/ui';

function stockStatus(p) {
  if (p.stock_level <= 0) return { tone: 'danger', label: 'Out of stock' };
  if (p.stock_level <= p.reorder_point) return { tone: 'warning', label: 'Reorder' };
  return { tone: 'success', label: 'Healthy' };
}

export default function Twin() {
  const { data: t, error, loading } = useApi('/tenants/twin');
  const [view, setView] = useState('inventory');
  const [q, setQ] = useState('');

  const suppliersById = useMemo(() => Object.fromEntries((t?.supply_network || []).map(s => [s.supplier_id, s])), [t]);
  const inventory = (t?.inventory || []).filter(p => !q || `${p.name} ${p.category} ${p.product_id}`.toLowerCase().includes(q.toLowerCase()));
  const network = (t?.supply_network || []).filter(s => !q || s.name.toLowerCase().includes(q.toLowerCase()));
  const productName = (id) => t?.inventory?.find(p => p.product_id === id)?.name || id;

  const below = (t?.inventory || []).filter(p => p.stock_level <= p.reorder_point).length;
  const avgReliability = t?.supply_network?.length
    ? t.supply_network.reduce((s, x) => s + x.reliability_score, 0) / t.supply_network.length
    : 0;

  const inventoryCols = [
    { header: 'Product', render: p => (
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{p.name}</p>
        <p className="text-xs text-muted">{p.product_id} · {p.category}</p>
      </div>
    ) },
    { header: 'Stock vs reorder point', className: 'w-64', render: p => {
      const cap = Math.max(p.reorder_point * 3, p.stock_level, 1);
      const s = stockStatus(p);
      return (
        <div className="flex items-center gap-3">
          <Progress value={p.stock_level / cap} tone={s.tone} className="flex-1" />
          <span className="num w-16 text-right text-xs text-ink-2">{num(p.stock_level)} / {num(p.reorder_point)}</span>
        </div>
      );
    } },
    { header: 'Price', align: 'right', render: p => money(p.unit_price) },
    { header: 'Supplier', render: p => {
      const s = suppliersById[p.supplier_ids?.[0]];
      return s ? <span className="text-xs">{s.avg_lead_time_days.toFixed(1)} d lead · {pct(s.reliability_score)} reliable</span> : <span className="text-xs text-muted">—</span>;
    } },
    { header: 'Status', render: p => { const s = stockStatus(p); return <Badge tone={s.tone} dot>{s.label}</Badge>; } },
  ];

  const networkCols = [
    { header: 'Supplier', render: s => <span className="font-medium text-ink">{s.name}</span> },
    { header: 'Supplies', render: s => productName(s.product_id) },
    { header: 'Lead time', align: 'right', render: s => `${s.avg_lead_time_days.toFixed(1)} ± ${s.lead_time_std_dev.toFixed(1)} d` },
    { header: 'Min order', align: 'right', render: s => num(s.min_order_qty) },
    { header: 'Reliability', className: 'w-48', render: s => (
      <div className="flex items-center gap-3">
        <Progress value={s.reliability_score} tone={s.reliability_score >= 0.85 ? 'success' : s.reliability_score >= 0.7 ? 'warning' : 'danger'} className="flex-1" />
        <span className="num w-10 text-right text-xs">{pct(s.reliability_score)}</span>
      </div>
    ) },
  ];

  return (
    <>
      <PageHeader
        title="Business digital twin"
        description="A single, read-only snapshot of the business that every agent and forecast reads from: stock, supply network, cash, customers, staffing and risk."
      />
      <ErrorNote className="mb-4">{error}</ErrorNote>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-6">
        <StatCard label="Products tracked" value={num(t?.inventory?.length)} hint={`${below} below reorder point`} icon={Boxes} tone="primary" loading={loading} />
        <StatCard label="Sales, last 30 days" value={moneyCompact(t?.sales_30d?.total_revenue)} hint={`${num(t?.sales_30d?.total_units)} units`} icon={Gauge} tone="success" loading={loading} />
        <StatCard label="Cash balance" value={moneyCompact(t?.finance?.cash_balance)} hint={`Period budget ${moneyCompact(t?.finance?.period_budget)}`} icon={Wallet} tone="info" loading={loading} />
        <StatCard label="Supplier reliability" value={pct(avgReliability)} hint={`${t?.supply_network?.length ?? 0} supply links`} icon={Network} tone="violet" loading={loading} />
        <StatCard label="Staff hours today" value={num(t?.staffing?.scheduled_hours_today, 1)} hint={`${t?.staffing?.shift_count ?? 0} shifts`} icon={Users} tone="warning" loading={loading} />
        <StatCard label="Risk level" value={pct(t?.risk_level)} hint={`${t?.monitoring_active_events?.length ?? 0} open alerts`} icon={ShieldAlert} tone={(t?.risk_level || 0) > 0.5 ? 'danger' : 'success'} loading={loading} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-4">
        <Card
          className="xl:col-span-3"
          padded={false}
          title={view === 'inventory' ? 'Inventory state' : 'Supply network'}
          subtitle={view === 'inventory' ? 'Stock position against each reorder point' : 'Supplier lead times and delivery reliability'}
          actions={(
            <>
              <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter…" className="hidden w-44 sm:block" />
              <Segmented value={view} onChange={setView} options={[{ value: 'inventory', label: 'Inventory' }, { value: 'network', label: 'Suppliers' }]} />
            </>
          )}
        >
          {loading ? <div className="p-5"><Skeleton className="h-72" /></div>
            : view === 'inventory'
              ? <Table columns={inventoryCols} rows={inventory} rowKey="product_id" empty={<Empty title="No products match" />} />
              : <Table columns={networkCols} rows={network} rowKey="supplier_id" empty={<Empty title="No suppliers match" />} />}
        </Card>

        <div className="space-y-6">
          <Card title="30-day outlook" icon={Clock}>
            {loading ? <Skeleton className="h-28" /> : (
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between"><dt className="text-muted">Projected revenue</dt><dd className="num font-medium text-ink">{money(t?.outlook_30d?.projected_revenue)}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Net cash flow</dt><dd className={`num font-medium ${(t?.outlook_30d?.net_cash_flow || 0) < 0 ? 'text-danger' : 'text-success'}`}>{money(t?.outlook_30d?.net_cash_flow)}</dd></div>
                <div className="flex justify-between border-t border-line pt-3"><dt className="text-muted">Projected cash</dt><dd className="num font-semibold text-ink">{money(t?.outlook_30d?.projected_cash)}</dd></div>
              </dl>
            )}
          </Card>
          <Card title="Twin snapshot">
            {loading ? <Skeleton className="h-28" /> : (
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between"><dt className="text-muted">Business</dt><dd className="font-medium text-ink">{t?.business_name}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Goal</dt><dd className="font-medium text-ink capitalize">{humanize(t?.business_goal)}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Run date</dt><dd className="font-medium text-ink">{date(t?.run_date)}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Customers</dt><dd className="num font-medium text-ink">{num(t?.customer_count)}</dd></div>
              </dl>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
