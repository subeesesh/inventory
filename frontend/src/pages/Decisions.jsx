import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import clsx from 'clsx';
import { AlertTriangle, BrainCircuit, CheckCircle2, Play, Scale, Sparkles } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { useSession } from '../core/session';
import { AGENT_LABELS, DECISION_TYPES, TRIGGER_ROLES } from '../core/constants';
import { date, formatRecommendation, humanize, num, pct, todayISO } from '../core/format';
import {
  Badge, Button, Card, Drawer, Empty, ErrorNote, Field, Input, Markdown, PageHeader, Progress, Select, Skeleton, Table,
} from '../components/ui';
import { useToast } from '../components/Toast';

const OUTCOME_ROLES = ['owner', 'inventory_manager', 'procurement_officer'];

function AgentBreakdown({ agents, decisionType }) {
  const max = Math.max(...agents.map(a => a.weight), 0.0001);
  const sorted = [...agents].sort((a, b) => b.weight - a.weight);
  return (
    <div className="space-y-3">
      {sorted.map((a, i) => (
        <div key={a.agent} className={clsx('rounded-xl border p-3', i === 0 ? 'border-primary/40 bg-primary-soft/50' : 'border-line')}>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-ink">{AGENT_LABELS[a.agent] || humanize(a.agent)}</span>
              {i === 0 && <Badge tone="primary">most trusted</Badge>}
            </div>
            <span className="num text-sm font-medium text-ink">{formatRecommendation(a.recommendation, decisionType)}</span>
          </div>
          <div className="mt-2 flex items-center gap-3">
            <Progress value={a.weight / max} className="flex-1" tone={i === 0 ? 'primary' : 'info'} />
            <span className="num w-14 text-right text-xs text-muted">{pct(a.weight, 1)}</span>
          </div>
          {a.rationale && <p className="mt-2 text-xs leading-relaxed text-ink-2">{a.rationale}</p>}
        </div>
      ))}
    </div>
  );
}

function DecisionDetail({ id, onClose, productName, onOutcome }) {
  const { role } = useSession();
  const { showToast } = useToast();
  const { data, error, loading } = useApi(id ? `/tenants/decisions/${id}/explain` : null);
  const [outcome, setOutcome] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => { setOutcome(''); }, [id]);

  const saveOutcome = async () => {
    const value = parseFloat(outcome);
    if (Number.isNaN(value)) return;
    setSaving(true);
    try {
      await api.post(`/tenants/decisions/${id}/outcome`, { actual_outcome: value });
      showToast('Outcome logged — agent reliability updated', 'success');
      onOutcome?.();
      setOutcome('');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const type = data && (DECISION_TYPES[data.decision_type] || { label: humanize(data.decision_type), tone: 'neutral', axis: 'Value' });

  return (
    <Drawer
      open={Boolean(id)}
      onClose={onClose}
      title={data ? `${type.label} · ${productName(data.product_id)}` : 'Decision'}
      description={data ? `Decision ${data.decision_id.slice(0, 8)}` : null}
    >
      {loading ? <Skeleton className="h-96" />
        : error ? <ErrorNote>{error}</ErrorNote>
        : data && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-primary p-4 text-on-primary">
                <p className="text-xs opacity-80">Fused recommendation</p>
                <p className="num mt-1 text-2xl font-semibold">{formatRecommendation(data.recommendation, data.decision_type)}</p>
                <p className="mt-1 text-xs opacity-80">{type.axis}</p>
              </div>
              <div className={clsx('rounded-xl p-4', data.conflict_detected ? 'bg-warning-soft text-warning' : 'bg-success-soft text-success')}>
                <p className="text-xs opacity-80">Agent agreement</p>
                <p className="mt-1 flex items-center gap-2 text-lg font-semibold">
                  {data.conflict_detected ? <AlertTriangle className="size-5" /> : <CheckCircle2 className="size-5" />}
                  {data.conflict_detected ? 'Conflict' : 'Agreed'}
                </p>
                <p className="num mt-1 text-xs opacity-80">Divergence score {Number(data.conflict_score || 0).toFixed(2)}</p>
              </div>
            </div>

            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink"><Scale className="size-4 text-muted" /> How each agent voted</h3>
              <AgentBreakdown agents={data.contributing_agents || []} decisionType={data.decision_type} />
              {data.conflict_resolution_notes && <p className="mt-3 text-xs text-muted">{data.conflict_resolution_notes}</p>}
            </section>

            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink"><Sparkles className="size-4 text-muted" /> Explanation</h3>
              <div className="rounded-xl border border-line bg-surface-2 p-4">
                <Markdown text={data.natural_language_summary} />
              </div>
            </section>

            {OUTCOME_ROLES.includes(role) && (
              <section className="rounded-xl border border-line p-4">
                <h3 className="text-sm font-semibold text-ink">Log the real outcome</h3>
                <p className="mt-1 mb-3 text-xs text-muted">
                  Enter what actually happened (e.g. the quantity that turned out to be needed). AMDIE scores every agent against it and adjusts their reliability.
                </p>
                <div className="flex gap-2">
                  <Input type="number" step="any" value={outcome} onChange={e => setOutcome(e.target.value)} placeholder={type.axis} />
                  <Button onClick={saveOutcome} loading={saving} disabled={outcome === ''}>Log outcome</Button>
                </div>
              </section>
            )}
          </div>
        )}
    </Drawer>
  );
}

export default function Decisions() {
  const { role } = useSession();
  const { showToast } = useToast();
  const [params, setParams] = useSearchParams();
  const twin = useApi('/tenants/twin');
  const decisions = useApi('/tenants/decisions', { initial: [] });
  const registry = useApi('/tenants/decision-types');

  const allowedTypes = Object.keys(TRIGGER_ROLES).filter(t => TRIGGER_ROLES[t].includes(role));
  const [form, setForm] = useState({ product: '', type: allowedTypes[0] || 'reorder_quantity', date: todayISO() });
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [filter, setFilter] = useState('all');

  const products = twin.data?.inventory || [];
  const productName = (id) => products.find(p => p.product_id === id)?.name || id;
  const selectedId = params.get('id');
  const openDecision = (id) => setParams(id ? { id } : {});

  const run = async () => {
    if (!form.product) { setRunError('Choose a product first.'); return; }
    setRunning(true); setRunError(null);
    try {
      const r = await api.post('/tenants/decisions/trigger', { product_id: form.product, date_str: form.date, decision_type: form.type });
      showToast('AMDIE analysis complete', 'success');
      await decisions.reload();
      openDecision(r.decision_id);
    } catch (e) {
      setRunError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const rows = useMemo(
    () => decisions.data.filter(d => filter === 'all' || d.decision_type === filter),
    [decisions.data, filter],
  );
  const participating = registry.data?.[form.type]?.agents || [];

  const columns = [
    { header: 'Date', render: d => <span className="text-xs whitespace-nowrap">{date(d.date)}</span> },
    { header: 'Type', render: d => { const t = DECISION_TYPES[d.decision_type]; return <Badge tone={t?.tone}>{t?.label || humanize(d.decision_type)}</Badge>; } },
    { header: 'Product', render: d => <span className="text-ink">{productName(d.product_id)}</span> },
    { header: 'Recommendation', align: 'right', render: d => <span className="font-medium text-ink">{formatRecommendation(d.fused_recommendation, d.decision_type)}</span> },
    { header: 'Agents', render: d => d.conflict_detected ? <Badge tone="warning" dot>conflict</Badge> : <Badge tone="success" dot>agreed</Badge> },
    { header: 'Outcome', align: 'right', render: d => d.actual_outcome == null ? <span className="text-xs text-muted">not logged</span> : num(d.actual_outcome, 1) },
  ];

  return (
    <>
      <PageHeader
        title="Decision Studio"
        description="Ask AMDIE for a decision. The relevant agents each recommend a value, AMDIE weights them by learned reliability and fuses them with a constrained linear program."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_1fr]">
        <Card title="Run an analysis" icon={BrainCircuit} className="self-start">
          {allowedTypes.length === 0 ? (
            <Empty title="Not available for your role" />
          ) : (
            <div className="space-y-4">
              <Field label="Decision type">
                <Select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
                  {allowedTypes.map(t => <option key={t} value={t}>{DECISION_TYPES[t].label}</option>)}
                </Select>
              </Field>
              <Field label="Product">
                <Select value={form.product} onChange={e => setForm(f => ({ ...f, product: e.target.value }))}>
                  <option value="">Select a product…</option>
                  {products.map(p => <option key={p.product_id} value={p.product_id}>{p.name}</option>)}
                </Select>
              </Field>
              <Field label="Decision date" hint="Forecasts use sales history up to this date.">
                <Input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} />
              </Field>
              {participating.length > 0 && (
                <div>
                  <p className="label">Agents that will vote</p>
                  <div className="flex flex-wrap gap-1.5">
                    {participating.map(a => <Badge key={a} tone="primary">{AGENT_LABELS[a] || a}</Badge>)}
                  </div>
                </div>
              )}
              <ErrorNote>{runError}</ErrorNote>
              <Button icon={Play} onClick={run} loading={running} className="w-full">Run AMDIE</Button>
            </div>
          )}
        </Card>

        <Card
          title="Decision history"
          subtitle={`${rows.length} decision${rows.length === 1 ? '' : 's'} · click one to see how it was made`}
          padded={false}
          actions={(
            <Select value={filter} onChange={e => setFilter(e.target.value)} className="w-44">
              <option value="all">All types</option>
              {Object.entries(DECISION_TYPES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Select>
          )}
        >
          {decisions.loading ? <div className="p-5"><Skeleton className="h-72" /></div>
            : <Table columns={columns} rows={rows} onRowClick={d => openDecision(d.id)} empty={<Empty title="No decisions yet">Run your first analysis on the left.</Empty>} />}
        </Card>
      </div>

      <DecisionDetail id={selectedId} onClose={() => openDecision(null)} productName={productName} onOutcome={decisions.reload} />
    </>
  );
}
