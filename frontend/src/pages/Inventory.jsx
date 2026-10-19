import { useMemo, useState } from 'react';
import { Boxes, PackageCheck, PackageX, Pencil, Plus, Power, Search, TriangleAlert } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { useSession } from '../core/session';
import { money, num, pct } from '../core/format';
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Modal, PageHeader, Segmented, Skeleton, StatCard, Table } from '../components/ui';
import { useToast } from '../components/Toast';

const EDIT_ROLES = ['owner', 'inventory_manager'];
const EMPTY = { id: '', name: '', category: '', sku: '', barcode: '', unit_price: '', unit_cost: '', min_stock: '', max_stock: '' };

function status(p) {
  if (!p.is_active) return { tone: 'neutral', label: 'Inactive', key: 'inactive' };
  if (p.stock_level <= 0) return { tone: 'danger', label: 'Out of stock', key: 'out' };
  if (p.stock_level <= p.reorder_point) return { tone: 'warning', label: 'Reorder', key: 'low' };
  return { tone: 'success', label: 'In stock', key: 'ok' };
}

function ProductForm({ form, setForm, errors, isEdit }) {
  const f = (key, label, type = 'text', hint) => (
    <Field label={label} error={errors[key]} hint={hint}>
      <Input type={type} step={type === 'number' ? 'any' : undefined} value={form[key]} invalid={Boolean(errors[key])}
        onChange={e => setForm(v => ({ ...v, [key]: e.target.value }))} />
    </Field>
  );
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {!isEdit && f('id', 'Product ID', 'text', 'A unique code, e.g. PROD-021')}
      {f('name', 'Name')}
      {f('category', 'Category')}
      {f('sku', 'SKU')}
      {f('barcode', 'Barcode')}
      {f('unit_price', 'Selling price', 'number')}
      {f('unit_cost', 'Unit cost', 'number')}
      {f('min_stock', 'Minimum stock', 'number')}
      {f('max_stock', 'Maximum stock', 'number')}
    </div>
  );
}

export default function Inventory() {
  const { role } = useSession();
  const { showToast } = useToast();
  const { data, error, loading, reload } = useApi('/tenants/products', { initial: [] });
  const canEdit = EDIT_ROLES.includes(role);
  const [q, setQ] = useState('');
  const [view, setView] = useState('all');
  const [editing, setEditing] = useState(null); // null | 'new' | product
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(null);

  const counts = useMemo(() => {
    const c = { ok: 0, low: 0, out: 0, inactive: 0 };
    data.forEach(p => { c[status(p).key] += 1; });
    return c;
  }, [data]);
  const stockValue = data.filter(p => p.is_active).reduce((s, p) => s + (p.unit_cost || 0) * (p.stock_level || 0), 0);

  const rows = data.filter(p => {
    const s = status(p).key;
    if (view === 'attention' && !(s === 'low' || s === 'out')) return false;
    if (view === 'inactive' && s !== 'inactive') return false;
    if (view === 'all' && s === 'inactive') return false;
    return !q || `${p.name} ${p.category} ${p.sku || ''} ${p.id}`.toLowerCase().includes(q.toLowerCase());
  });

  const open = (p) => {
    setErrors({});
    if (p === 'new') { setForm(EMPTY); setEditing('new'); return; }
    setForm({
      id: p.id, name: p.name, category: p.category, sku: p.sku || '', barcode: p.barcode || '',
      unit_price: String(p.unit_price ?? ''), unit_cost: String(p.unit_cost ?? ''),
      min_stock: String(p.min_stock ?? ''), max_stock: String(p.max_stock ?? ''),
    });
    setEditing(p);
  };

  const save = async () => {
    const isNew = editing === 'new';
    const errs = {};
    if (isNew && !form.id.trim()) errs.id = 'required';
    if (!form.name.trim()) errs.name = 'required';
    if (!form.category.trim()) errs.category = 'required';
    if (form.unit_price === '' || Number(form.unit_price) < 0) errs.unit_price = 'required';
    setErrors(errs);
    if (Object.keys(errs).length) return;

    const body = {
      name: form.name.trim(), category: form.category.trim(),
      sku: form.sku || null, barcode: form.barcode || null,
      unit_price: parseFloat(form.unit_price),
      unit_cost: parseFloat(form.unit_cost) || 0,
      min_stock: parseInt(form.min_stock, 10) || 0,
      max_stock: parseInt(form.max_stock, 10) || 1000,
    };
    setSaving(true);
    try {
      if (isNew) await api.post('/tenants/products', { id: form.id.trim(), ...body });
      else await api.put(`/tenants/products/${editing.id}`, body);
      showToast(isNew ? 'Product added' : 'Product updated', 'success');
      setEditing(null);
      reload();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (p) => {
    try {
      if (p.is_active) await api.del(`/tenants/products/${p.id}`);
      else await api.put(`/tenants/products/${p.id}`, { is_active: true });
      showToast(p.is_active ? 'Product deactivated' : 'Product reactivated', 'success');
      setConfirm(null);
      reload();
    } catch (e) {
      showToast(e.message, 'error');
    }
  };

  const columns = [
    { header: 'Product', render: p => (
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{p.name}</p>
        <p className="font-mono text-xs text-muted">{p.sku || p.id}</p>
      </div>
    ) },
    { header: 'Category', accessor: 'category' },
    { header: 'Price', align: 'right', render: p => money(p.unit_price) },
    { header: 'Cost', align: 'right', render: p => money(p.unit_cost) },
    { header: 'Margin', align: 'right', render: p => p.unit_price ? pct((p.unit_price - (p.unit_cost || 0)) / p.unit_price) : '—' },
    { header: 'Stock', align: 'right', render: p => <span className="font-medium text-ink">{num(p.stock_level)}</span> },
    { header: 'Reorder at', align: 'right', render: p => num(p.reorder_point) },
    { header: 'Status', render: p => { const s = status(p); return <Badge tone={s.tone} dot>{s.label}</Badge>; } },
    ...(canEdit ? [{ header: '', className: 'w-24', render: p => (
      <div className="flex justify-end gap-1" onClick={e => e.stopPropagation()}>
        <Button size="icon" variant="ghost" onClick={() => open(p)} aria-label={`Edit ${p.name}`} title="Edit"><Pencil className="size-4" /></Button>
        <Button size="icon" variant={p.is_active ? 'danger-ghost' : 'ghost'} onClick={() => setConfirm(p)} aria-label={p.is_active ? 'Deactivate' : 'Reactivate'} title={p.is_active ? 'Deactivate' : 'Reactivate'}><Power className="size-4" /></Button>
      </div>
    ) }] : []),
  ];

  return (
    <>
      <PageHeader
        title="Inventory"
        description="Products, stock on hand and reorder points. Reorder points come from the inventory agent and drive monitoring alerts."
        actions={canEdit && <Button icon={Plus} onClick={() => open('new')}>Add product</Button>}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Active products" value={num(data.length - counts.inactive)} icon={Boxes} tone="primary" loading={loading} />
        <StatCard label="In stock" value={num(counts.ok)} icon={PackageCheck} tone="success" loading={loading} />
        <StatCard label="Need reorder" value={num(counts.low + counts.out)} hint={`${counts.out} out of stock`} icon={TriangleAlert} tone={counts.low + counts.out ? 'warning' : 'success'} loading={loading} />
        <StatCard label="Stock value at cost" value={money(stockValue)} icon={PackageX} tone="info" loading={loading} />
      </div>

      <Card
        className="mt-6"
        padded={false}
        title="Products"
        actions={(
          <>
            <div className="relative hidden sm:block">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
              <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Search…" className="w-52 pl-9" />
            </div>
            <Segmented value={view} onChange={setView} options={[
              { value: 'all', label: 'Active' },
              { value: 'attention', label: 'Needs attention' },
              { value: 'inactive', label: 'Inactive' },
            ]} />
          </>
        )}
      >
        <ErrorNote className="m-4">{error}</ErrorNote>
        {loading ? <div className="p-5"><Skeleton className="h-80" /></div>
          : <Table columns={columns} rows={rows} onRowClick={canEdit ? open : undefined}
              empty={<Empty icon={Boxes} title={data.length ? 'No products match' : 'No products yet'} action={canEdit && !data.length && <Button icon={Plus} onClick={() => open('new')}>Add your first product</Button>} />} />}
      </Card>

      {editing && (
        <Modal
          size="lg"
          title={editing === 'new' ? 'Add product' : `Edit ${editing.name}`}
          onClose={() => setEditing(null)}
          footer={<><Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button><Button onClick={save} loading={saving}>{editing === 'new' ? 'Add product' : 'Save changes'}</Button></>}
        >
          <ProductForm form={form} setForm={setForm} errors={errors} isEdit={editing !== 'new'} />
        </Modal>
      )}

      {confirm && (
        <Modal
          size="sm"
          title={confirm.is_active ? 'Deactivate product?' : 'Reactivate product?'}
          onClose={() => setConfirm(null)}
          footer={<><Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button><Button variant={confirm.is_active ? 'danger' : 'primary'} onClick={() => toggleActive(confirm)}>{confirm.is_active ? 'Deactivate' : 'Reactivate'}</Button></>}
        >
          <p className="text-sm text-ink-2">
            {confirm.is_active
              ? <><strong className="text-ink">{confirm.name}</strong> will be hidden from the POS. Its history is kept and you can reactivate it later.</>
              : <><strong className="text-ink">{confirm.name}</strong> will be available for sale again.</>}
          </p>
        </Modal>
      )}
    </>
  );
}
