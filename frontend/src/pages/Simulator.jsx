import { useState } from 'react';
import clsx from 'clsx';
import { ArrowDownRight, ArrowUpRight, FlaskConical, Info, Minus, Play } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { humanize, money, num } from '../core/format';
import { Button, Card, Empty, ErrorNote, Field, Input, PageHeader, Select } from '../components/ui';

const SCENARIOS = {
  price_change:    { label: 'Price change', hint: 'Raise or cut the selling price; demand responds through price elasticity.', usesPct: true },
  demand_shock:    { label: 'Demand shock', hint: 'A sudden rise or fall in customer demand.', usesPct: true },
  supplier_delay:  { label: 'Supplier delay', hint: 'Deliveries arrive later than usual.', usesPct: false },
  staffing_change: { label: 'Staffing change', hint: 'More or fewer staff hours, which changes labour cost.', usesPct: true },
};

function Delta({ value, format }) {
  const v = Number(value) || 0;
  const Icon = v > 0 ? ArrowUpRight : v < 0 ? ArrowDownRight : Minus;
  return (
    <span className={clsx('inline-flex items-center gap-1 font-medium', v > 0 ? 'text-success' : v < 0 ? 'text-danger' : 'text-muted')}>
      <Icon className="size-4" />{v > 0 ? '+' : ''}{format(v)}
    </span>
  );
}

function CompareRow({ label, base, sim, delta, format }) {
  const max = Math.max(Math.abs(base), Math.abs(sim), 1e-9);
  return (
    <div className="grid grid-cols-[140px_1fr_auto] items-center gap-4 border-b border-line py-4 last:border-0">
      <p className="text-sm font-medium text-ink-2">{label}</p>
      <div className="space-y-1.5">
        {[['Baseline', base, 'bg-line-strong'], ['Scenario', sim, 'bg-primary']].map(([name, v, color]) => (
          <div key={name} className="flex items-center gap-3">
            <span className="w-16 text-xs text-muted">{name}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
              <div className={clsx('h-full rounded-full', color)} style={{ width: `${(Math.abs(v) / max) * 100}%` }} />
            </div>
            <span className="num w-28 text-right text-xs text-ink">{format(v)}</span>
          </div>
        ))}
      </div>
      <span className="num w-28 text-right text-sm"><Delta value={delta} format={format} /></span>
    </div>
  );
}

export default function Simulator() {
  const twin = useApi('/tenants/twin');
  const products = twin.data?.inventory || [];
  const [form, setForm] = useState({ type: 'price_change', product: '', pct: 10, delay: 5, horizon: 30 });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const scenario = SCENARIOS[form.type];
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const simulate = async () => {
    setLoading(true); setError(null);
    try {
      setResult(await api.post('/tenants/scenarios/simulate', {
        type: form.type,
        product_id: form.product || null,
        delta_pct: Number(form.pct) / 100,
        delay_days: parseInt(form.delay, 10) || 0,
        horizon_days: parseInt(form.horizon, 10) || 30,
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const cur = result?.current_trajectory;
  const sim = result?.simulated_trajectory;

  return (
    <>
      <PageHeader
        title="What-if simulator"
        description="Test a decision before you make it. Simulations run on an in-memory copy of the business twin and never change live data."
      />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_1fr]">
        <Card title="Scenario" icon={FlaskConical} className="self-start">
          <div className="space-y-4">
            <Field label="What changes?" hint={scenario.hint}>
              <Select value={form.type} onChange={set('type')}>
                {Object.entries(SCENARIOS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
              </Select>
            </Field>
            <Field label="Product">
              <Select value={form.product} onChange={set('product')}>
                <option value="">Whole business</option>
                {products.map(p => <option key={p.product_id} value={p.product_id}>{p.name}</option>)}
              </Select>
            </Field>
            {scenario.usesPct ? (
              <Field label={`Change: ${Number(form.pct) > 0 ? '+' : ''}${form.pct}%`}>
                <input type="range" min="-50" max="50" step="5" value={form.pct} onChange={set('pct')} className="w-full accent-[var(--primary)]" />
                <div className="mt-1 flex justify-between text-[11px] text-muted"><span>−50%</span><span>0</span><span>+50%</span></div>
              </Field>
            ) : (
              <Field label="Delay (days)">
                <Input type="number" min="1" max="60" value={form.delay} onChange={set('delay')} />
              </Field>
            )}
            <Field label="Horizon (days)">
              <Input type="number" min="7" max="180" value={form.horizon} onChange={set('horizon')} />
            </Field>
            <ErrorNote>{error}</ErrorNote>
            <Button icon={Play} onClick={simulate} loading={loading} className="w-full">Run simulation</Button>
          </div>
        </Card>

        <div className="space-y-6">
          <Card
            title="Baseline vs scenario"
            subtitle={result ? `${SCENARIOS[result.scenario_type]?.label || humanize(result.scenario_type)} over ${result.horizon_days} days` : 'Run a simulation to compare outcomes'}
          >
            {!result ? (
              <Empty icon={FlaskConical} title="No simulation yet">Pick a scenario on the left and run it to see how demand, revenue and cash would move.</Empty>
            ) : (
              <div>
                <CompareRow label="Demand" base={cur.forecast_demand_units} sim={sim.forecast_demand_units} delta={result.delta.demand_delta_units} format={(v) => `${num(v, 1)} units`} />
                <CompareRow label="Revenue" base={cur.projected_revenue} sim={sim.projected_revenue} delta={result.delta.revenue_delta} format={money} />
                <CompareRow label="Cash balance" base={cur.projected_cash_balance} sim={sim.projected_cash_balance} delta={result.delta.cash_delta} format={money} />
              </div>
            )}
          </Card>

          {result?.assumptions && (
            <Card title="Assumptions behind this result" icon={Info}>
              <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                {Object.entries(result.assumptions).map(([k, v]) => (
                  <div key={k} className="border-b border-line pb-2">
                    <dt className="text-xs text-muted capitalize">{humanize(k)}</dt>
                    <dd className="mt-0.5 text-sm text-ink">{typeof v === 'number' ? num(v, Number.isInteger(v) ? 0 : 2) : String(v)}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
