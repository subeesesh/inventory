import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { Banknote, CreditCard, Minus, Plus, Printer, Search, ShoppingCart, Smartphone, Trash2, UserPlus, X } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { money } from '../core/format';
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Modal, Skeleton } from '../components/ui';
import { useToast } from '../components/Toast';

const TAX_RATE = Number(import.meta.env.VITE_DEFAULT_TAX_RATE ?? 0.05);
const PAYMENTS = [
  { value: 'card', label: 'Card', icon: CreditCard },
  { value: 'cash', label: 'Cash', icon: Banknote },
  { value: 'upi', label: 'UPI', icon: Smartphone },
];

export default function POS() {
  const { showToast } = useToast();
  const products = useApi('/tenants/products', { initial: [] });
  const customers = useApi('/tenants/customers', { initial: [] });
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('all');
  const [cart, setCart] = useState([]);
  const [payment, setPayment] = useState('card');
  const [customer, setCustomer] = useState(null);
  const [custQuery, setCustQuery] = useState('');
  const [newCust, setNewCust] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState(null);
  const [receipt, setReceipt] = useState(null);

  const active = products.data.filter(p => p.is_active !== false);
  const categories = useMemo(() => ['all', ...new Set(active.map(p => p.category).filter(Boolean))], [active]);
  const shown = active.filter(p =>
    (category === 'all' || p.category === category) &&
    (!q || `${p.name} ${p.sku || ''} ${p.barcode || ''}`.toLowerCase().includes(q.toLowerCase())));
  const custMatches = custQuery.length >= 2 && !customer
    ? customers.data.filter(c => `${c.name} ${c.phone || ''}`.toLowerCase().includes(custQuery.toLowerCase())).slice(0, 6)
    : [];

  const inCart = (id) => cart.find(i => i.product_id === id)?.qty || 0;
  const add = (p) => {
    if (inCart(p.id) >= (p.stock_level ?? 0)) return;
    setCart(c => c.some(i => i.product_id === p.id)
      ? c.map(i => (i.product_id === p.id ? { ...i, qty: i.qty + 1 } : i))
      : [...c, { product_id: p.id, name: p.name, unit_price: p.unit_price, qty: 1, discount: 0, stock: p.stock_level }]);
  };
  const changeQty = (id, d) => setCart(c => c.map(i => (i.product_id === id ? { ...i, qty: Math.min(i.stock, Math.max(1, i.qty + d)) } : i)));
  const remove = (id) => setCart(c => c.filter(i => i.product_id !== id));

  const subtotal = cart.reduce((s, i) => s + i.unit_price * i.qty - i.discount, 0);
  const tax = subtotal * TAX_RATE;
  const total = subtotal + tax;

  const checkout = async () => {
    setChecking(true); setError(null);
    try {
      const r = await api.post('/tenants/pos/checkout', {
        customer_id: customer?.id || null,
        payment_method: payment,
        discount: 0, tax, subtotal, total,
        items: cart.map(i => ({ product_id: i.product_id, qty: i.qty, unit_price: i.unit_price, discount: i.discount })),
      });
      setReceipt({ id: r?.sale_id || r?.id, items: cart, subtotal, tax, total, payment, customer, at: new Date() });
      products.reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setChecking(false);
    }
  };

  const finish = () => {
    setReceipt(null); setCart([]); setCustomer(null); setCustQuery('');
    showToast('Sale completed', 'success');
  };

  const saveCustomer = async () => {
    if (!newCust?.name?.trim()) return;
    try {
      const c = await api.post('/tenants/customers', { name: newCust.name.trim(), phone: newCust.phone || null });
      customers.setData(list => [c, ...list]);
      setCustomer(c); setCustQuery(c.name); setNewCust(null);
      showToast('Customer added', 'success');
    } catch (e) { showToast(e.message, 'error'); }
  };

  return (
    <div className="grid grid-cols-1 gap-6 xl:h-[calc(100vh-8.5rem)] xl:grid-cols-[1fr_400px]">
      {/* Catalogue */}
      <Card padded={false} className="flex min-h-0 flex-col" bodyClassName="flex min-h-0 flex-1 flex-col">
        <div className="space-y-3 border-b border-line p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
            <Input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Scan a barcode or search products…" className="pl-9" />
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {categories.map(c => (
              <button
                key={c}
                onClick={() => setCategory(c)}
                className={clsx('rounded-full border px-3 py-1 text-xs font-medium whitespace-nowrap capitalize transition-colors',
                  category === c ? 'border-primary bg-primary-soft text-primary' : 'border-line text-ink-2 hover:bg-surface-2')}
              >
                {c === 'all' ? 'All products' : c}
              </button>
            ))}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <ErrorNote>{products.error}</ErrorNote>
          {products.loading ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-28" />)}</div>
          ) : shown.length === 0 ? <Empty icon={Search} title="No products found" /> : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-4">
              {shown.map(p => {
                const left = (p.stock_level ?? 0) - inCart(p.id);
                const out = left <= 0;
                const low = !out && p.reorder_point != null && p.stock_level <= p.reorder_point;
                return (
                  <button
                    key={p.id}
                    onClick={() => add(p)}
                    disabled={out}
                    className={clsx('flex flex-col rounded-xl border border-line p-3.5 text-left transition-all',
                      out ? 'cursor-not-allowed opacity-50' : 'hover:-translate-y-0.5 hover:border-primary hover:shadow-card')}
                  >
                    <span className="line-clamp-2 min-h-10 text-sm font-medium text-ink">{p.name}</span>
                    <span className="mt-0.5 truncate text-xs text-muted">{p.category}</span>
                    <span className="mt-3 flex items-end justify-between gap-2">
                      <span className="num text-base font-semibold text-ink">{money(p.unit_price)}</span>
                      {out ? <Badge tone="danger">Out</Badge> : low ? <Badge tone="warning">{left} left</Badge> : <span className="num text-xs text-muted">{left} in stock</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </Card>

      {/* Order */}
      <Card padded={false} className="flex min-h-0 flex-col" bodyClassName="flex min-h-0 flex-1 flex-col" title="Current order" icon={ShoppingCart}
        actions={cart.length > 0 && <Button size="sm" variant="ghost" onClick={() => setCart([])}>Clear</Button>}
      >
        <div className="relative border-b border-line p-4">
          {customer ? (
            <div className="flex items-center justify-between rounded-lg bg-primary-soft px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-primary">{customer.name}</p>
                {customer.phone && <p className="text-xs text-primary/80">{customer.phone}</p>}
              </div>
              <button onClick={() => { setCustomer(null); setCustQuery(''); }} className="text-primary" aria-label="Remove customer"><X className="size-4" /></button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Input value={custQuery} onChange={e => setCustQuery(e.target.value)} placeholder="Attach a customer (optional)" />
              <Button variant="secondary" size="icon" onClick={() => setNewCust({ name: custQuery, phone: '' })} aria-label="New customer"><UserPlus className="size-4" /></Button>
            </div>
          )}
          {custMatches.length > 0 && (
            <div className="absolute inset-x-4 top-[calc(100%-0.5rem)] z-10 overflow-hidden rounded-lg border border-line bg-surface shadow-pop">
              {custMatches.map(c => (
                <button key={c.id} onClick={() => { setCustomer(c); setCustQuery(c.name); }} className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-2">
                  {c.name} {c.phone && <span className="text-muted">· {c.phone}</span>}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="min-h-[160px] flex-1 overflow-y-auto">
          {cart.length === 0 ? <Empty icon={ShoppingCart} title="Cart is empty">Tap a product to add it.</Empty> : (
            <ul className="divide-y divide-line">
              {cart.map(i => (
                <li key={i.product_id} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{i.name}</p>
                    <p className="num text-xs text-muted">{money(i.unit_price)} each</p>
                  </div>
                  <div className="flex items-center rounded-lg border border-line">
                    <button onClick={() => changeQty(i.product_id, -1)} className="grid size-7 place-items-center text-ink-2 hover:text-ink" aria-label="Decrease"><Minus className="size-3.5" /></button>
                    <span className="num w-7 text-center text-sm">{i.qty}</span>
                    <button onClick={() => changeQty(i.product_id, 1)} className="grid size-7 place-items-center text-ink-2 hover:text-ink" aria-label="Increase"><Plus className="size-3.5" /></button>
                  </div>
                  <span className="num w-20 text-right text-sm font-medium text-ink">{money(i.unit_price * i.qty)}</span>
                  <button onClick={() => remove(i.product_id)} className="text-muted hover:text-danger" aria-label="Remove"><Trash2 className="size-4" /></button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-3 border-t border-line p-4">
          <dl className="space-y-1.5 text-sm">
            <div className="flex justify-between text-muted"><dt>Subtotal</dt><dd className="num">{money(subtotal)}</dd></div>
            <div className="flex justify-between text-muted"><dt>Tax ({(TAX_RATE * 100).toFixed(0)}%)</dt><dd className="num">{money(tax)}</dd></div>
            <div className="flex justify-between pt-1 text-lg font-semibold text-ink"><dt>Total</dt><dd className="num">{money(total)}</dd></div>
          </dl>
          <div className="grid grid-cols-3 gap-2">
            {PAYMENTS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => setPayment(value)}
                className={clsx('flex items-center justify-center gap-1.5 rounded-lg border py-2 text-xs font-medium transition-colors',
                  payment === value ? 'border-primary bg-primary-soft text-primary' : 'border-line text-ink-2 hover:bg-surface-2')}
              >
                <Icon className="size-4" />{label}
              </button>
            ))}
          </div>
          <ErrorNote>{error}</ErrorNote>
          <Button size="lg" className="w-full" onClick={checkout} loading={checking} disabled={!cart.length}>
            Charge {money(total)}
          </Button>
        </div>
      </Card>

      {newCust && (
        <Modal title="New customer" size="sm" onClose={() => setNewCust(null)}
          footer={<><Button variant="secondary" onClick={() => setNewCust(null)}>Cancel</Button><Button onClick={saveCustomer} disabled={!newCust.name?.trim()}>Save customer</Button></>}
        >
          <div className="space-y-4">
            <Field label="Name"><Input autoFocus value={newCust.name} onChange={e => setNewCust(c => ({ ...c, name: e.target.value }))} /></Field>
            <Field label="Phone"><Input value={newCust.phone} onChange={e => setNewCust(c => ({ ...c, phone: e.target.value }))} /></Field>
          </div>
        </Modal>
      )}

      {receipt && (
        <Modal title="Payment received" description={receipt.id ? `Receipt ${String(receipt.id).slice(0, 8).toUpperCase()}` : null} size="sm" onClose={finish}
          footer={<><Button variant="secondary" icon={Printer} onClick={() => window.print()}>Print</Button><Button onClick={finish}>New sale</Button></>}
        >
          <div className="space-y-3 text-sm">
            <ul className="divide-y divide-line">
              {receipt.items.map(i => (
                <li key={i.product_id} className="flex justify-between gap-3 py-2">
                  <span className="text-ink">{i.qty} × {i.name}</span>
                  <span className="num text-ink">{money(i.unit_price * i.qty)}</span>
                </li>
              ))}
            </ul>
            <dl className="space-y-1 border-t border-line pt-3">
              <div className="flex justify-between text-muted"><dt>Subtotal</dt><dd className="num">{money(receipt.subtotal)}</dd></div>
              <div className="flex justify-between text-muted"><dt>Tax</dt><dd className="num">{money(receipt.tax)}</dd></div>
              <div className="flex justify-between text-base font-semibold text-ink"><dt>Total</dt><dd className="num">{money(receipt.total)}</dd></div>
            </dl>
            <p className="text-xs text-muted uppercase">Paid by {receipt.payment}{receipt.customer ? ` · ${receipt.customer.name}` : ''} · {receipt.at.toLocaleString()}</p>
          </div>
        </Modal>
      )}
    </div>
  );
}
