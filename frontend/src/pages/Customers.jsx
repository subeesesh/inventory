import { useState } from 'react';
import { Plus, Search, UserRound, Users, Wallet } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { useSession } from '../core/session';
import { date, dateTime, money, num } from '../core/format';
import { Badge, Button, Card, Drawer, Empty, ErrorNote, Field, Input, Modal, PageHeader, Skeleton, StatCard, Table } from '../components/ui';
import { useToast } from '../components/Toast';

const ANALYTICS_ROLES = ['owner', 'finance_officer'];
const CREATE_ROLES = ['owner', 'cashier'];

export default function Customers() {
  const { role } = useSession();
  const { showToast } = useToast();
  const analytics = ANALYTICS_ROLES.includes(role);
  // Owners and finance see lifetime spend from the customers report; cashiers get the plain list
  const list = useApi(analytics ? '/tenants/reports?type=customers' : '/tenants/customers');
  const sales = useApi(analytics ? '/tenants/sales' : null, { initial: [] });
  const customers = (analytics ? list.data?.data : list.data) || [];

  const [q, setQ] = useState('');
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState(null);

  const rows = customers.filter(c => !q || `${c.name} ${c.phone || ''} ${c.email || ''}`.toLowerCase().includes(q.toLowerCase()));
  const totalSpend = customers.reduce((s, c) => s + (c.lifetime_spend || 0), 0);
  const history = selected ? sales.data.filter(s => s.customer_id === selected.id) : [];

  const save = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await api.post('/tenants/customers', { name: form.name.trim(), phone: form.phone || null, email: form.email || null });
      showToast('Customer added', 'success');
      setForm(null);
      list.reload();
    } catch (e) { showToast(e.message, 'error'); } finally { setSaving(false); }
  };

  const columns = [
    { header: 'Customer', render: c => (
      <div className="flex items-center gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary-soft text-xs font-semibold text-primary uppercase">{c.name.slice(0, 2)}</span>
        <span className="font-medium text-ink">{c.name}</span>
      </div>
    ) },
    { header: 'Phone', render: c => c.phone || '—' },
    { header: 'Email', render: c => c.email || '—' },
    ...(analytics ? [
      { header: 'Orders', align: 'right', render: c => num(c.transaction_count) },
      { header: 'Lifetime spend', align: 'right', render: c => <span className="font-medium text-ink">{money(c.lifetime_spend)}</span> },
      { header: 'Last purchase', render: c => <span className="text-xs">{date(c.last_purchase)}</span> },
    ] : []),
  ];

  return (
    <>
      <PageHeader
        title="Customers"
        description="Your customer list. Purchases made at the POS are linked to the customer attached to the sale."
        actions={CREATE_ROLES.includes(role) && <Button icon={Plus} onClick={() => setForm({ name: '', phone: '', email: '' })}>Add customer</Button>}
      />

      {analytics && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-3">
          <StatCard label="Customers" value={num(customers.length)} icon={Users} tone="primary" loading={list.loading} />
          <StatCard label="Lifetime spend" value={money(totalSpend)} icon={Wallet} tone="success" loading={list.loading} />
          <StatCard label="Average per customer" value={money(customers.length ? totalSpend / customers.length : 0)} icon={UserRound} tone="violet" loading={list.loading} />
        </div>
      )}

      <Card
        padded={false}
        title="Customer list"
        actions={(
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Name, phone or email…" className="w-56 pl-9" />
          </div>
        )}
      >
        <ErrorNote className="m-4">{list.error}</ErrorNote>
        {list.loading ? <div className="p-5"><Skeleton className="h-64" /></div>
          : <Table columns={columns} rows={rows} onRowClick={analytics ? setSelected : undefined}
              empty={<Empty icon={Users} title={customers.length ? 'No customers match' : 'No customers yet'}>Customers you add here or at the POS appear in this list.</Empty>} />}
      </Card>

      <Drawer open={Boolean(selected)} onClose={() => setSelected(null)} title={selected?.name} description={[selected?.phone, selected?.email].filter(Boolean).join(' · ') || null}>
        {selected && (
          <div className="space-y-5">
            <div className="grid grid-cols-3 gap-3">
              {[['Orders', num(selected.transaction_count)], ['Lifetime spend', money(selected.lifetime_spend)], ['Last purchase', date(selected.last_purchase)]].map(([l, v]) => (
                <div key={l} className="rounded-xl bg-surface-2 p-3">
                  <p className="text-xs text-muted">{l}</p>
                  <p className="num mt-1 text-sm font-semibold text-ink">{v}</p>
                </div>
              ))}
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">Purchase history</h3>
              {sales.loading ? <Skeleton className="h-32" />
                : history.length === 0 ? <Empty title="No purchases on record" />
                : (
                  <ul className="divide-y divide-line rounded-xl border border-line">
                    {history.map(s => (
                      <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                        <span className="text-ink-2">{dateTime(s.created_at)}</span>
                        <Badge>{s.payment_method}</Badge>
                        <span className="num font-medium text-ink">{money(s.total)}</span>
                      </li>
                    ))}
                  </ul>
                )}
            </div>
          </div>
        )}
      </Drawer>

      {form && (
        <Modal size="sm" title="Add customer" onClose={() => setForm(null)}
          footer={<><Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button><Button onClick={save} loading={saving} disabled={!form.name.trim()}>Save customer</Button></>}
        >
          <div className="space-y-4">
            <Field label="Name"><Input autoFocus value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} /></Field>
            <Field label="Phone"><Input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} /></Field>
            <Field label="Email"><Input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} /></Field>
          </div>
        </Modal>
      )}
    </>
  );
}
