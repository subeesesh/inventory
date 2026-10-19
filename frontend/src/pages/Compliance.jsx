import { CheckCircle2, ClipboardCheck, Database, Download, FileClock, Plug, Receipt, ScrollText } from 'lucide-react';
import { useApi } from '../core/useApi';
import { useSession } from '../core/session';
import { DECISION_TYPES } from '../core/constants';
import { date, formatRecommendation, humanize, num } from '../core/format';
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, Skeleton, StatCard, Table } from '../components/ui';

const CONNECTOR_STATUS = {
  interface_ready_future_extension: { tone: 'neutral', label: 'Interface ready' },
  connected: { tone: 'success', label: 'Connected' },
};

function downloadCsv(filename, rows) {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const header = Object.keys(rows[0]);
  const body = rows.map(r => header.map(k => esc(r[k])).join(','));
  const blob = new Blob([[header.join(','), ...body].join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function Compliance() {
  const { role } = useSession();
  const audit = useApi('/tenants/compliance/audit');
  const integration = useApi(role === 'owner' ? '/tenants/integration/summary' : null);
  const decisions = useApi('/tenants/decisions', { initial: [] });
  const a = audit.data;
  const active = a?.compliance_status === 'AUDIT_LOGS_ACTIVE';

  const exportTrail = () => downloadCsv(`decision-audit-${a?.audit_timestamp || 'export'}.csv`, decisions.data.map(d => ({
    decision_id: d.id,
    date: d.date,
    decision_type: d.decision_type,
    product_id: d.product_id,
    business_goal: d.business_goal_applied,
    fused_recommendation: d.fused_recommendation,
    conflict_detected: d.conflict_detected,
    conflict_score: d.conflict_score,
    actual_outcome: d.actual_outcome ?? '',
  })));

  const columns = [
    { header: 'Date', render: d => <span className="text-xs whitespace-nowrap">{date(d.date)}</span> },
    { header: 'Decision', render: d => <Badge tone={DECISION_TYPES[d.decision_type]?.tone}>{DECISION_TYPES[d.decision_type]?.label || humanize(d.decision_type)}</Badge> },
    { header: 'Product', render: d => <span className="font-mono text-xs">{d.product_id}</span> },
    { header: 'Goal applied', render: d => <span className="text-xs capitalize">{humanize(d.business_goal_applied)}</span> },
    { header: 'Recommendation', align: 'right', render: d => formatRecommendation(d.fused_recommendation, d.decision_type) },
    { header: 'Conflict', render: d => d.conflict_detected ? <Badge tone="warning">{Number(d.conflict_score).toFixed(2)}</Badge> : <Badge tone="success">none</Badge> },
    { header: 'Outcome', align: 'right', render: d => d.actual_outcome == null ? <span className="text-xs text-muted">pending</span> : num(d.actual_outcome, 1) },
  ];

  return (
    <>
      <PageHeader
        title="Compliance & audit"
        description="Every AMDIE decision, sale and ledger entry is logged. Use this page to check that audit logging is active and to export the decision trail."
        actions={<Button variant="secondary" icon={Download} disabled={!decisions.data.length} onClick={exportTrail}>Export decision trail (CSV)</Button>}
      />
      <ErrorNote className="mb-4">{audit.error}</ErrorNote>

      <div className={`mb-6 flex items-center gap-4 rounded-xl border p-4 ${active ? 'border-success/30 bg-success-soft' : 'border-warning/30 bg-warning-soft'}`}>
        {audit.loading ? <Skeleton className="h-10 w-full" /> : (
          <>
            <CheckCircle2 className={`size-6 shrink-0 ${active ? 'text-success' : 'text-warning'}`} />
            <div className="min-w-0 flex-1">
              <p className={`font-semibold ${active ? 'text-success' : 'text-warning'}`}>{active ? 'Audit logging is active' : humanize(a?.compliance_status || 'unknown')}</p>
              <p className="text-sm text-ink-2">Audit snapshot taken {date(a?.audit_timestamp)}. Tax filing export: {humanize(a?.tax_filing_export_status || '').toLowerCase()}.</p>
            </div>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Logged AI decisions" value={num(a?.logged_decisions_audit_count)} icon={ScrollText} tone="violet" loading={audit.loading} />
        <StatCard label="Sales transactions" value={num(a?.sales_transactions_audit_count)} icon={Receipt} tone="success" loading={audit.loading} />
        <StatCard label="Finance ledger entries" value={num(a?.financial_ledgers_audit_count)} icon={FileClock} tone="info" loading={audit.loading} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Decision audit trail" subtitle="Who decided what, under which business goal, and what actually happened" icon={ClipboardCheck} padded={false}>
          {decisions.loading ? <div className="p-5"><Skeleton className="h-64" /></div>
            : <Table columns={columns} rows={decisions.data} dense empty={<Empty title="No decisions logged yet" />} />}
        </Card>

        {role === 'owner' && (
          <Card title="Data integration" subtitle="Sources feeding the business twin" icon={Database}>
            {integration.loading ? <Skeleton className="h-48" /> : integration.error ? <ErrorNote>{integration.error}</ErrorNote> : (
              <div className="space-y-5">
                <dl className="space-y-2.5 text-sm">
                  {[
                    ['POS transactions', integration.data?.pos_records_count],
                    ['Inventory items tracked', integration.data?.inventory_tracked_items],
                    ['CRM contacts', integration.data?.crm_contacts_count],
                    ['Supplier profiles', integration.data?.supplier_profiles_count],
                  ].map(([l, v]) => (
                    <div key={l} className="flex justify-between"><dt className="text-muted">{l}</dt><dd className="num font-medium text-ink">{num(v)}</dd></div>
                  ))}
                </dl>
                <div>
                  <p className="label flex items-center gap-1.5"><Plug className="size-3.5" /> External connectors</p>
                  <ul className="space-y-2">
                    {Object.entries(integration.data?.external_connectors || {}).map(([name, st]) => {
                      const s = CONNECTOR_STATUS[st] || { tone: 'neutral', label: humanize(st) };
                      return (
                        <li key={name} className="flex items-center justify-between rounded-lg border border-line px-3 py-2">
                          <span className="text-sm font-medium text-ink capitalize">{name}</span>
                          <Badge tone={s.tone}>{s.label}</Badge>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </div>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
