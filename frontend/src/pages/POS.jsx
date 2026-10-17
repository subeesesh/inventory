import React, { useState, useEffect, useRef } from 'react';
import { Card, DataTable, Modal } from '../components/ui';
import { useToast } from '../components/ToastProvider';
import api from '../api';

const fmt = (n) => `$${Number(n || 0).toFixed(2)}`;

export const POS = ({ role }) => {
  const { showToast } = useToast();
  const [products, setProducts]               = useState([]);
  const [cart, setCart]                       = useState([]);
  const [paymentMethod, setPaymentMethod]     = useState('card');
  const [isCheckingOut, setIsCheckingOut]     = useState(false);
  const [checkoutError, setCheckoutError]     = useState(null);
  const [receipt, setReceipt]                 = useState(null);   // non-null → show receipt modal
  const [productsLoading, setProductsLoading] = useState(true);
  const [searchTerm, setSearchTerm]           = useState('');

  // Customer picker
  const [customers, setCustomers]             = useState([]);
  const [customerSearch, setCustomerSearch]   = useState('');
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [customerDropdown, setCustomerDropdown] = useState([]);
  const [newCustName, setNewCustName]         = useState('');
  const [newCustPhone, setNewCustPhone]       = useState('');
  const [showNewCust, setShowNewCust]         = useState(false);
  const customerRef = useRef(null);

  useEffect(() => {
    api.get('/tenants/products')
      .then(d => setProducts((d || []).filter(p => p.is_active !== false)))
      .catch(e => showToast(e.message, 'error'))
      .finally(() => setProductsLoading(false));
    api.get('/tenants/customers')
      .then(d => setCustomers(d || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (customerSearch.length >= 2) {
      setCustomerDropdown(customers.filter(c =>
        c.name.toLowerCase().includes(customerSearch.toLowerCase())
      ));
    } else {
      setCustomerDropdown([]);
    }
  }, [customerSearch, customers]);

  const filteredProducts = products.filter(p =>
    !searchTerm ||
    p.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.sku?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.barcode?.includes(searchTerm)
  );

  // ── Cart helpers ────────────────────────────────────────────────────────────
  const addToCart = (product) => {
    if ((product.stock_level ?? 0) === 0) return;
    setCart(prev => {
      const existing = prev.find(i => i.product_id === product.id);
      if (existing) return prev.map(i => i.product_id === product.id ? { ...i, qty: i.qty + 1 } : i);
      return [...prev, { product_id: product.id, name: product.name, unit_price: product.unit_price, qty: 1, discount: 0, stock_level: product.stock_level }];
    });
  };
  const updateQty = (id, delta) => setCart(prev => prev.map(i => i.product_id === id ? { ...i, qty: Math.max(1, i.qty + delta) } : i));
  const removeFromCart = (id) => setCart(prev => prev.filter(i => i.product_id !== id));

  const DEFAULT_TAX_RATE = Number(import.meta.env.VITE_DEFAULT_TAX_RATE ?? 0.05);
  const subtotal = cart.reduce((s, i) => s + i.unit_price * i.qty - i.discount, 0);
  const tax      = subtotal * DEFAULT_TAX_RATE;
  const total    = subtotal + tax;

  // ── Checkout ────────────────────────────────────────────────────────────────
  const handleCheckout = async () => {
    if (cart.length === 0) return;
    setIsCheckingOut(true); setCheckoutError(null);
    try {
      const result = await api.post('/tenants/pos/checkout', {
        customer_id: selectedCustomer?.id || null,
        payment_method: paymentMethod,
        discount: 0, tax, subtotal, total,
        items: cart.map(i => ({ product_id: i.product_id, qty: i.qty, unit_price: i.unit_price, discount: i.discount })),
      });
      setReceipt({ ...result, items: cart, subtotal, tax, total, payment_method: paymentMethod });
    } catch (e) {
      setCheckoutError(e.message);
    } finally {
      setIsCheckingOut(false);
    }
  };

  const closeReceipt = () => { setReceipt(null); setCart([]); setSelectedCustomer(null); setCustomerSearch(''); showToast('Transaction complete!', 'success'); };

  const handleNewCustomer = async () => {
    if (!newCustName.trim()) return;
    try {
      const c = await api.post('/tenants/customers', { name: newCustName, phone: newCustPhone });
      setCustomers(prev => [c, ...prev]);
      setSelectedCustomer(c); setCustomerSearch(c.name);
      setShowNewCust(false); setNewCustName(''); setNewCustPhone('');
      showToast('Customer added', 'success');
    } catch (e) { showToast(e.message, 'error'); }
  };

  const cartCols = [
    { header: 'Item', accessor: 'name' },
    { header: 'Price', render: r => fmt(r.unit_price) },
    { header: 'Qty', render: r => (
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
        <button onClick={() => updateQty(r.product_id, -1)} style={btnStyle}>−</button>
        <span style={{ minWidth: '24px', textAlign: 'center' }}>{r.qty}</span>
        <button onClick={() => updateQty(r.product_id, 1)} style={btnStyle}>+</button>
      </div>
    )},
    { header: 'Total', render: r => fmt(r.unit_price * r.qty - r.discount) },
    { header: '', render: r => <button onClick={() => removeFromCart(r.product_id)} style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '16px' }}>✕</button> },
  ];

  return (
    <div style={{ display: 'flex', gap: '24px', height: 'calc(100vh - 120px)' }}>
      {/* ── Left: Catalog ── */}
      <div style={{ flex: 2, display: 'flex', flexDirection: 'column', gap: '16px', overflow: 'hidden' }}>
        <Card title="Product Catalog" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <input
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="🔍  Scan barcode or search by name / SKU…"
            style={{ width: '100%', padding: '12px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', marginBottom: '16px', boxSizing: 'border-box' }}
          />
          {productsLoading ? (
            <div style={{ color: '#64748b', textAlign: 'center', padding: '40px' }}>Loading products…</div>
          ) : filteredProducts.length === 0 ? (
            <div style={{ color: '#64748b', textAlign: 'center', padding: '40px' }}>No products found.</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '12px', overflowY: 'auto', flex: 1 }}>
              {filteredProducts.map(p => {
                const oos = (p.stock_level ?? 0) === 0;
                const low = !oos && p.min_stock && p.stock_level <= p.min_stock;
                return (
                  <div
                    key={p.id}
                    onClick={() => addToCart(p)}
                    style={{
                      background: oos ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '10px', padding: '14px', cursor: oos ? 'not-allowed' : 'pointer',
                      opacity: oos ? 0.45 : 1, textAlign: 'center', transition: 'background 0.15s',
                    }}
                    onMouseOver={e => { if (!oos) e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; }}
                    onMouseOut={e => { e.currentTarget.style.background = oos ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.05)'; }}
                  >
                    <div style={{ fontWeight: 500, color: '#e2e8f0', marginBottom: '6px', fontSize: '13px', wordBreak: 'break-word' }}>{p.name}</div>
                    <div style={{ color: '#4ade80', fontWeight: 'bold' }}>{fmt(p.unit_price)}</div>
                    {oos && <div style={{ color: '#f87171', fontSize: '11px', marginTop: '4px' }}>Out of Stock</div>}
                    {low && <div style={{ color: '#fbbf24', fontSize: '11px', marginTop: '4px' }}>Low Stock ({p.stock_level})</div>}
                    {!oos && !low && <div style={{ color: '#64748b', fontSize: '11px', marginTop: '4px' }}>Stock: {p.stock_level}</div>}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* ── Right: Cart ── */}
      <div style={{ flex: 1, minWidth: '340px', display: 'flex', flexDirection: 'column', gap: '0' }}>
        <Card title="Order" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* Customer picker */}
          <div style={{ marginBottom: '16px', position: 'relative' }} ref={customerRef}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                value={customerSearch}
                onChange={e => { setCustomerSearch(e.target.value); setSelectedCustomer(null); }}
                placeholder={selectedCustomer ? selectedCustomer.name : 'Customer (optional)…'}
                style={{ flex: 1, padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: '13px' }}
              />
              <button onClick={() => setShowNewCust(v => !v)} style={{ ...btnStyle, whiteSpace: 'nowrap', padding: '10px 12px' }}>+ New</button>
            </div>
            {customerDropdown.length > 0 && (
              <div style={{ position: 'absolute', top: '42px', left: 0, right: 0, background: '#1e1e2c', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '8px', zIndex: 100, maxHeight: '160px', overflowY: 'auto' }}>
                {customerDropdown.map(c => (
                  <div key={c.id} onClick={() => { setSelectedCustomer(c); setCustomerSearch(c.name); setCustomerDropdown([]); }}
                    style={{ padding: '10px 14px', cursor: 'pointer', color: '#e2e8f0', fontSize: '13px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}
                    onMouseOver={e => e.currentTarget.style.background = 'rgba(255,255,255,0.08)'}
                    onMouseOut={e => e.currentTarget.style.background = ''}
                  >
                    {c.name} {c.phone && `· ${c.phone}`}
                  </div>
                ))}
              </div>
            )}
            {showNewCust && (
              <div style={{ marginTop: '8px', background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <input value={newCustName} onChange={e => setNewCustName(e.target.value)} placeholder="Name *" style={inputStyle} />
                <input value={newCustPhone} onChange={e => setNewCustPhone(e.target.value)} placeholder="Phone" style={inputStyle} />
                <button onClick={handleNewCustomer} style={{ ...btnStyle, background: '#4ade80', color: '#0f172a', fontWeight: 'bold' }}>Save Customer</button>
              </div>
            )}
          </div>

          {/* Cart items */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {cart.length === 0
              ? <p style={{ color: '#475569', textAlign: 'center', padding: '30px 0' }}>Cart is empty. Tap a product to add it.</p>
              : <DataTable columns={cartCols} data={cart} />}
          </div>

          {/* Totals & checkout */}
          <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px', marginTop: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b', marginBottom: '6px', fontSize: '14px' }}>
              <span>Subtotal</span><span>{fmt(subtotal)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b', marginBottom: '12px', fontSize: '14px' }}>
              <span>Tax (5%)</span><span>{fmt(tax)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#fff', fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>
              <span>Total</span><span style={{ color: '#4ade80' }}>{fmt(total)}</span>
            </div>

            {/* Payment toggle */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
              {['card', 'cash', 'upi'].map(m => (
                <button key={m} onClick={() => setPaymentMethod(m)} style={{
                  flex: 1, padding: '9px', borderRadius: '6px', textTransform: 'uppercase', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer', transition: 'all 0.15s',
                  background: paymentMethod === m ? 'rgba(74,222,128,0.2)' : 'rgba(255,255,255,0.04)',
                  color: paymentMethod === m ? '#4ade80' : '#64748b',
                  border: `1px solid ${paymentMethod === m ? '#4ade80' : 'rgba(255,255,255,0.1)'}`,
                }}>{m}</button>
              ))}
            </div>

            {checkoutError && (
              <div style={{ background: 'rgba(248,113,113,0.15)', border: '1px solid #f87171', color: '#fca5a5', padding: '10px 14px', borderRadius: '6px', fontSize: '13px', marginBottom: '12px' }}>
                {checkoutError}
              </div>
            )}

            <button
              onClick={handleCheckout}
              disabled={cart.length === 0 || isCheckingOut}
              style={{
                width: '100%', padding: '16px', borderRadius: '10px', fontSize: '17px', fontWeight: 'bold', border: 'none', cursor: cart.length === 0 ? 'not-allowed' : 'pointer',
                background: cart.length === 0 ? 'rgba(255,255,255,0.06)' : (isCheckingOut ? 'rgba(74,222,128,0.5)' : '#4ade80'),
                color: cart.length === 0 ? '#475569' : '#0f172a',
              }}
            >
              {isCheckingOut ? 'Processing…' : '✓  Complete Checkout'}
            </button>
          </div>
        </Card>
      </div>

      {/* ── Receipt Modal ── */}
      {receipt && (
        <Modal title="Receipt" onClose={closeReceipt}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <p style={{ color: '#64748b', fontSize: '12px', margin: 0 }}>Transaction ID: <code style={{ color: '#94a3b8' }}>{receipt.sale_id || receipt.id}</code></p>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                  <th style={{ padding: '8px 0', textAlign: 'left', color: '#64748b' }}>Item</th>
                  <th style={{ padding: '8px 0', textAlign: 'right', color: '#64748b' }}>Qty</th>
                  <th style={{ padding: '8px 0', textAlign: 'right', color: '#64748b' }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {receipt.items.map((it, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '8px 0', color: '#e2e8f0' }}>{it.name}</td>
                    <td style={{ padding: '8px 0', textAlign: 'right', color: '#94a3b8' }}>{it.qty}</td>
                    <td style={{ padding: '8px 0', textAlign: 'right', color: '#e2e8f0' }}>{fmt(it.unit_price * it.qty)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b', fontSize: '13px' }}><span>Subtotal</span><span>{fmt(receipt.subtotal)}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b', fontSize: '13px' }}><span>Tax</span><span>{fmt(receipt.tax)}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#fff', fontSize: '18px', fontWeight: 'bold' }}><span>Total</span><span style={{ color: '#4ade80' }}>{fmt(receipt.total)}</span></div>
              <div style={{ color: '#64748b', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Payment: {receipt.payment_method}</div>
            </div>
            <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
              <button onClick={() => window.print()} style={{ flex: 1, padding: '12px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', color: '#fff', border: '1px solid rgba(255,255,255,0.12)', cursor: 'pointer' }}>🖨 Print</button>
              <button onClick={closeReceipt} style={{ flex: 1, padding: '12px', borderRadius: '8px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>Done</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

// Shared micro-styles
const btnStyle = { padding: '6px 10px', borderRadius: '6px', background: 'rgba(255,255,255,0.08)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer', fontSize: '14px' };
const inputStyle = { padding: '9px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: '13px', width: '100%', boxSizing: 'border-box' };
