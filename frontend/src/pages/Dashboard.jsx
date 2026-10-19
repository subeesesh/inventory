import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, BrainCircuit, Gauge, PackageX, Receipt, Truck, Wallet,
} from 'lucide-react';
import { useApi } from '../core/useApi';
import { useSession } from '../core/session';
import { AGENT_LABELS, DECISION_TYPES, SEVERITY_TONE } from '../core/constants';
import { date, formatRecommendation, humanize, money, moneyCompact, num, pct } from '../core/format';
import { Badge, Card, Empty, ErrorNote, PageHeader, Progress, Segmented, Skeleton, StatCard } from '../components/ui';
import { HBarChart, TrendChart } from '../components/charts';

export default function Dashboard() {
  const { role } = useSession();
  const metrics = useApi('/tenants/metrics');
  const twin = useApi('/tenants/twin');
  const history = useApi('/tenants/sales-history?days=90');
  const decisions = useApi('/tenants/decisions', { initial: [] });
  const events = useApi('/tenants/monitoring/events', { initial: [] });
  const [series, setSeries] = useState('revenue');

  const m = metrics.data;
  const t = twin.data;
  const productName = (id) => t?.inventory?.find(p => p.product_id === id)?.name || id;
  const lowStock = (t?.inventory || []).filter(p => p.stock_level <= p.reorder_point);
  const reliability = Object.entries(m?.agent_reliability || {})
    .map(([agent, score]) => ({ label: AGENT_LABELS[agent] || agent, score }))
    .sort((a, b) => b.score - a.score);

  const historyData = history.data?.data || [];
  const periodTotal = historyData.reduce((s, d) => s + (series === 'revenue' ? d.revenue : d.units), 0);
  const staleDays = history.data?.as_of
    ? Math.round((Date.now() - new Date(history.data.as_of).getTime()) / 86400000)
    : 0;

  return (
    <>
      <PageHeader
        title="Control tower"
        description={t ? `${t.business_name} · goal: ${humanize(t.business_goal)} · as of ${date(t.run_date)}` : 'Live overview of your business.'}
      />
      <ErrorNote className="mb-4">{metrics.error || twin.error}</ErrorNote>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-6">
        <StatCard label="Revenue today" value={money(m?.total_revenue_today)} icon={Receipt} tone="success" loading={metrics.loading} />
        <StatCard label="Transactions today" value={num(m?.total_transactions_today)} icon={Receipt} tone="info" loading={metrics.loading} />
        <StatCard label="Cash balance" value={moneyCompact(t?.finance?.cash_balance)} hint={t ? `Budget ${moneyCompact(t.finance.period_budget)}` : null} icon={Wallet} tone="primary" loading={twin.loading} />
        <StatCard label="Below reorder point" value={num(lowStock.length)} hint={t ? `of ${t.inventory.length} products` : null} icon={PackageX} tone={lowStock.length ? 'danger' : 'success'} loading={twin.loading} />
        <StatCard label="Pending POs" value={num(m?.pending_po_count)} icon={Truck} tone="warning" loading={metrics.loading} />
        <StatCard label="AI accuracy" value={pct(m?.cumulative_accuracy, 1)} hint={m ? `${m.total_decisions} decisions logged` : null} icon={BrainCircuit} tone="violet" loading={metrics.loading} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Sales history"
          subtitle={history.data?.as_of ? `90 days to ${date(history.data.as_of)} · ${series === 'revenue' ? money(periodTotal) : `${num(periodTotal)} units`}` : 'Daily sales from the business twin'}
          actions={<Segmented value={series} onChange={setSeries} options={[{ value: 'revenue', label: 'Revenue' }, { value: 'units', label: 'Units' }]} />}
        >
          {history.loading ? <Skeleton className="h-[260px]" />
            : historyData.length === 0 ? <Empty title="No sales recorded yet" />
            : (
              <>
                {staleDays > 7 && (
                  <p className="mb-3 flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">
                    <AlertTriangle className="size-3.5 shrink-0" />
                    The latest recorded sale is {staleDays} days old, so forecasts that use today’s date will see little recent demand.
                  </p>
                )}
                <TrendChart
                  data={historyData}
                  dataKey={series}
                  color={series === 'revenue' ? 'primary' : 'violet'}
                  formatter={(v) => (series === 'revenue' ? money(v) : `${num(v)} units`)}
                  yFormatter={(v) => (series === 'revenue' ? moneyCompact(v) : num(v))}
                />
              </>
            )}
        </Card>

        <Card title="Agent reliability" subtitle="Learned from logged outcomes; drives AMDIE weights" icon={Gauge}>
          {metrics.loading ? <Skeleton className="h-40" />
            : reliability.length === 0 ? <Empty title="No reliability scores yet" />
            : (
              <div className="space-y-3.5">
                {reliability.map(r => (
                  <div key={r.label}>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="font-medium text-ink-2">{r.label}</span>
                      <span className="num text-muted">{pct(r.score)}</span>
                    </div>
                    <Progress value={r.score} tone={r.score >= 0.8 ? 'success' : r.score >= 0.6 ? 'warning' : 'danger'} />
                  </div>
                ))}
                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 text-center">
                  <div>
                    <p className="num text-lg font-semibold text-ink">{pct((m?.conflict_percentage || 0) / 100)}</p>
                    <p className="text-xs text-muted">decisions with conflict</p>
                  </div>
                  <div>
                    <p className="num text-lg font-semibold text-ink">{pct(t?.risk_level)}</p>
                    <p className="text-xs text-muted">business risk level</p>
                  </div>
                </div>
              </div>
            )}
        </Card>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Recent AMDIE decisions"
          padded={false}
          actions={<Link to="/decisions" className="flex items-center gap-1 text-xs font-medium text-primary hover:underline">Decision Studio <ArrowRight className="size-3.5" /></Link>}
        >
          {decisions.loading ? <div className="p-5"><Skeleton className="h-40" /></div>
            : decisions.data.length === 0 ? <Empty title="No decisions yet">Run an analysis from the Decision Studio.</Empty>
            : (
              <ul className="divide-y divide-line">
                {decisions.data.slice(0, 6).map(d => {
                  const type = DECISION_TYPES[d.decision_type] || { label: humanize(d.decision_type), tone: 'neutral' };
                  return (
                    <li key={d.id}>
                      <Link to={`/decisions?id=${d.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-surface-2">
                        <Badge tone={type.tone} className="hidden sm:inline-flex">{type.label}</Badge>
                        <span className="min-w-0 flex-1 truncate text-sm text-ink">{productName(d.product_id)}</span>
                        {d.conflict_detected && <Badge tone="warning" dot className="hidden sm:inline-flex">conflict</Badge>}
                        <span className="num shrink-0 text-right text-sm font-medium text-ink sm:w-36">{formatRecommendation(d.fused_recommendation, d.decision_type)}</span>
                        <span className="hidden w-24 text-right text-xs text-muted sm:block">{date(d.date)}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
        </Card>

        <Card
          title="Open alerts"
          padded={false}
          actions={<Link to="/monitoring" className="flex items-center gap-1 text-xs font-medium text-primary hover:underline">All alerts <ArrowRight className="size-3.5" /></Link>}
        >
          {events.loading ? <div className="p-5"><Skeleton className="h-40" /></div>
            : events.data.length === 0 ? <Empty title="All clear">No open monitoring alerts.</Empty>
            : (
              <ul className="divide-y divide-line">
                {events.data.slice(0, 6).map(e => (
                  <li key={e.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink capitalize">{humanize(e.event_type)}</p>
                      <p className="truncate text-xs text-muted">
                        {e.entity_type === 'product' ? productName(e.entity_id) : (t?.supply_network?.find(s => s.supplier_id === e.entity_id)?.name || e.entity_type)}
                      </p>
                    </div>
                    <Badge tone={SEVERITY_TONE[e.severity] || 'neutral'}>{e.severity}</Badge>
                  </li>
                ))}
              </ul>
            )}
        </Card>
      </div>

      {m?.decision_type_stats && (
        <Card className="mt-6" title="Decision types" subtitle="How each AMDIE decision type has performed so far">
          <HBarChart
            data={Object.entries(m.decision_type_stats).map(([k, s]) => ({ label: DECISION_TYPES[k]?.label || s.label, total: s.total_decisions }))}
            dataKey="total"
            formatter={(v) => `${v} decisions`}
          />
          {role === 'owner' && (
            <p className="mt-2 text-xs text-muted">Log real outcomes in the Decision Studio so AMDIE can keep learning which agents to trust.</p>
          )}
        </Card>
      )}
    </>
  );
}
