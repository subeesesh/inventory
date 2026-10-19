import { useState } from 'react';
import { Building2, ClipboardList, PackageCheck, Plus, Trash2, Truck } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { useSession } from '../core/session';
import { date, money, num, pct } from '../core/format';
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Modal, PageHeader, Progress, Segmented, Select, Skeleton, StatCard, Table } from '../components/ui';
import { useToast } from '../components/Toast';

const CREATE_ROLES = ['owner', 'procurement_officer'];
const RECEIVE_ROLES = ['owner', 'inventory_manager', 'procurement_officer'];
const PO_TONE = { ordered: 'info', received: 'success', cancelled: 'neutral' };
const EMPTY_SUPPLIER = { name: '', contact_phone: '', contact_email: '', address: '' };
const newLine = () => ({ product_id: '', qty: 1, unit_cost: '' });

export default function Purchases() {
  const { role } = useSession();
  const { showToast } = useToast();
  const pos = useApi('/tenants/purchase-orders', { initial: [] });
  const profiles = useApi('/tenants/supplier-profiles', { initial: [] });
  const network = useApi('/tenants/suppliers', { initial: [] });
  const products = useApi(CREATE_ROLES.includes(role) || role === 'inventory_manager' ? '/tenants/products' : null, { initial: [] });
  const twin = useApi('/tenants/twin');

  const [tab, setTab] = useState('orders');
  const [poOpen, setPoOpen] = useState(false);
  const [poSupplier, setPoSupplier] = useState('');
  const [lines, setLines] = useState([newLine()]);
  const [supplierForm, setSupplierForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [receiving, setReceiving] = useState(null);

  const canCreate = CREATE_ROLES.includes(role);
  const productName = (id) => products.data.find(p => p.id === id)?.name || twin.data?.inventory?.find(p => p.product_id === id)?.name || id;
  const supplierName = (id) => profiles.data.find(s => s.id === id)?.name || '—';
  const poTotal = (po) => (po.items || []).reduce((s, i) => s + i.qty * i.unit_cost, 0);
  const open = pos.data.filter(p => p.status === 'ordered');
  const draftTotal = lines.reduce((s, l) => s + (parseFloat(l.unit_cost) || 0) * (parseInt(l.qty, 10) || 0), 0);

  const setLine = (i, key, value) => setLines(ls => ls.map((l, idx) => {
    if (idx !== i) return l;
    const next = { ...l, [key]: value };
    if (key === 'product_id' && !l.unit_cost) {
      const p = products.data.find(x => x.id === value);
      if (p?.unit_cost) next.unit_cost = String(p.unit_cost);
    }
    return next;
  }));

  const createPO = async () => {
    if (!poSupplier || lines.some(l => !l.product_id || !(parseInt(l.qty, 10) > 0) || l.unit_cost === '')) {
      showToast('Choose a supplier and complete every line', 'error');
      return;
    }
    setSaving(true);
    try {
      await api.post('/tenants/purchase-orders', {
        supplier_profile_id: poSupplier,
        items: lines.map(l => ({ product_id: l.product_id, qty: parseInt(l.qty, 10), unit_cost: parseFloat(l.unit_cost) })),
      });
      showToast('Purchase order created', 'success');
      setPoOpen(false); setPoSupplier(''); setLines([newLine()]);
      pos.reload();
    } catch (e) { showToast(e.message, 'error'); } finally { setSaving(false); }
  };

  const saveSupplier = async () => {
    if (!supplierForm.name.trim()) return;
    setSaving(true);
    try {
      await api.post('/tenants/supplier-profiles', supplierForm);
      showToast('Supplier added', 'success');
      setSupplierForm(null);
      profiles.reload();
    } catch (e) { showToast(e.message, 'error'); } finally { setSaving(false); }
  };

  const receive = async (id) => {
    setReceiving(id);
    try {
      await api.post(`/tenants/purchase-orders/${id}/receive`, {});
      showToast('Delivery received — stock updated', 'success');
      pos.reload();
    } catch (e) { showToast(e.message, 'error'); } finally { setReceiving(null); }
  };

  const poColumns = [
    { header: 'Order', render: p => <span className="font-mono text-xs text-ink">PO-{p.id.slice(0, 6).toUpperCase()}</span> },
    { header: 'Supplier', render: p => <span className="text-ink">{supplierName(p.supplier_profile_id)}</span> },
    { header: 'Items', wrap: true, render: p => (
      <span className="text-xs">{(p.items || []).slice(0, 2).map(i => `${i.qty} × ${productName(i.product_id)}`).join(', ')}{p.items?.length > 2 ? ` +${p.items.length - 2} more` : ''}</span>
    ) },
    { header: 'Ordered', render: p => <span className="text-xs whitespace-nowrap">{date(p.created_at)}</span> },
    { header: 'Total', align: 'right', render: p => <span className="font-medium text-ink">{money(poTotal(p))}</span> },
    { header: 'Status', render: p => <Badge tone={PO_TONE[p.status] || 'neutral'} dot>{p.status}</Badge> },
    { header: '', render: p => p.status === 'ordered' && RECEIVE_ROLES.includes(role) && (
      <Button size="sm" variant="secondary" icon={PackageCheck} loading={receiving === p.id} onClick={() => receive(p.id)}>Receive</Button>
    ) },
  ];

  const profileColumns = [
    { header: 'Supplier', render: s => <span className="font-medium text-ink">{s.name}</span> },
    { header: 'Phone', render: s => s.contact_phone || '—' },
    { header: 'Email', render: s => s.contact_email || '—' },
    { header: 'Address', wrap: true, render: s => <span className="text-xs">{s.address || '—'}</span> },
  ];

  const networkColumns = [
    { header: 'Supplier', render: s => <span className="font-medium text-ink">{s.name}</span> },
    { header: 'Product', render: s => productName(s.product_id) },
    { header: 'Lead time', align: 'right', render: s => `${s.avg_lead_time_days.toFixed(1)} ± ${s.lead_time_std_dev.toFixed(1)} d` },
    { header: 'Min order', align: 'right', render: s => num(s.min_order_qty) },
    { header: 'Reliability', className: 'w-44', render: s => (
      <div className="flex items-center gap-2">
        <Progress value={s.reliability_score} tone={s.reliability_score >= 0.85 ? 'success' : s.reliability_score >= 0.7 ? 'warning' : 'danger'} className="flex-1" />
        <span className="num w-9 text-right text-xs">{pct(s.reliability_score)}</span>
      </div>
    ) },
  ];

  const current = { orders: pos, profiles, network }[tab];

  return (
    <>
      <PageHeader
        title="Purchases & suppliers"
        description="Purchase orders, supplier contacts, and the supply network the procurement agent uses to judge lead times and reliability."
        actions={canCreate && (
          <>
            <Button variant="secondary" icon={Building2} onClick={() => setSupplierForm(EMPTY_SUPPLIER)}>Add supplier</Button>
            <Button icon={Plus} onClick={() => setPoOpen(true)}>New purchase order</Button>
          </>
        )}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Open orders" value={num(open.length)} icon={Truck} tone="info" loading={pos.loading} />
        <StatCard label="Value on order" value={money(open.reduce((s, p) => s + poTotal(p), 0))} icon={ClipboardList} tone="primary" loading={pos.loading} />
        <StatCard label="Supplier profiles" value={num(profiles.data.length)} icon={Building2} tone="violet" loading={profiles.loading} />
        <StatCard
          label="Avg. supplier reliability"
          value={network.data.length ? pct(network.data.reduce((s, x) => s + x.reliability_score, 0) / network.data.length) : '—'}
          icon={PackageCheck} tone="success" loading={network.loading}
        />
      </div>

      <Card
        className="mt-6"
        padded={false}
        title={{ orders: 'Purchase orders', profiles: 'Supplier profiles', network: 'Supply network' }[tab]}
        actions={<Segmented value={tab} onChange={setTab} options={[{ value: 'orders', label: 'Orders' }, { value: 'profiles', label: 'Suppliers' }, { value: 'network', label: 'Supply network' }]} />}
      >
        <ErrorNote className="m-4">{current.error}</ErrorNote>
        {current.loading ? <div className="p-5"><Skeleton className="h-64" /></div>
          : tab === 'orders' ? <Table columns={poColumns} rows={pos.data} empty={<Empty icon={Truck} title="No purchase orders yet" action={canCreate && <Button icon={Plus} onClick={() => setPoOpen(true)}>Create the first one</Button>}>Orders you raise appear here until they are received.</Empty>} />
          : tab === 'profiles' ? <Table columns={profileColumns} rows={profiles.data} empty={<Empty icon={Building2} title="No supplier profiles yet" action={canCreate && <Button variant="secondary" onClick={() => setSupplierForm(EMPTY_SUPPLIER)}>Add a supplier</Button>}>Add a supplier before raising a purchase order.</Empty>} />
          : <Table columns={networkColumns} rows={network.data} empty={<Empty title="No supply links" />} />}
      </Card>

      {poOpen && (
        <Modal size="lg" title="New purchase order" onClose={() => setPoOpen(false)}
          footer={(
            <div className="flex w-full items-center justify-between">
              <span className="text-sm text-muted">Total <span className="num ml-1 font-semibold text-ink">{money(draftTotal)}</span></span>
              <div className="flex gap-2"><Button variant="secondary" onClick={() => setPoOpen(false)}>Cancel</Button><Button onClick={createPO} loading={saving}>Create order</Button></div>
            </div>
          )}
        >
          <div className="space-y-5">
            <Field label="Supplier" hint={profiles.data.length ? null : 'Add a supplier profile first.'}>
              <Select value={poSupplier} onChange={e => setPoSupplier(e.target.value)}>
                <option value="">Select a supplier…</option>
                {profiles.data.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
            <div>
              <div className="mb-2 grid grid-cols-[1fr_80px_110px_36px] gap-2 text-xs font-medium text-muted">
                <span>Product</span><span>Qty</span><span>Unit cost</span><span />
              </div>
              <div className="space-y-2">
                {lines.map((l, i) => (
                  <div key={i} className="grid grid-cols-[1fr_80px_110px_36px] gap-2">
                    <Select value={l.product_id} onChange={e => setLine(i, 'product_id', e.target.value)}>
                      <option value="">Product…</option>
                      {products.data.filter(p => p.is_active).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </Select>
                    <Input type="number" min="1" value={l.qty} onChange={e => setLine(i, 'qty', e.target.value)} />
                    <Input type="number" step="0.01" min="0" value={l.unit_cost} onChange={e => setLine(i, 'unit_cost', e.target.value)} placeholder="0.00" />
                    <Button size="icon" variant="ghost" disabled={lines.length === 1} onClick={() => setLines(ls => ls.filter((_, idx) => idx !== i))} aria-label="Remove line"><Trash2 className="size-4" /></Button>
                  </div>
                ))}
              </div>
              <Button size="sm" variant="ghost" icon={Plus} className="mt-2" onClick={() => setLines(ls => [...ls, newLine()])}>Add line</Button>
            </div>
          </div>
        </Modal>
      )}

      {supplierForm && (
        <Modal title="Add supplier" onClose={() => setSupplierForm(null)}
          footer={<><Button variant="secondary" onClick={() => setSupplierForm(null)}>Cancel</Button><Button onClick={saveSupplier} loading={saving} disabled={!supplierForm.name.trim()}>Save supplier</Button></>}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Company name" className="sm:col-span-2"><Input autoFocus value={supplierForm.name} onChange={e => setSupplierForm(f => ({ ...f, name: e.target.value }))} /></Field>
            <Field label="Phone"><Input value={supplierForm.contact_phone} onChange={e => setSupplierForm(f => ({ ...f, contact_phone: e.target.value }))} /></Field>
            <Field label="Email"><Input type="email" value={supplierForm.contact_email} onChange={e => setSupplierForm(f => ({ ...f, contact_email: e.target.value }))} /></Field>
            <Field label="Address" className="sm:col-span-2"><Input value={supplierForm.address} onChange={e => setSupplierForm(f => ({ ...f, address: e.target.value }))} /></Field>
          </div>
        </Modal>
      )}
    </>
  );
}
