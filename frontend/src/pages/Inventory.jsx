import React, { useState, useEffect } from 'react';
import { Card, DataTable, StatusBadge, RoleGate, Modal } from '../components/ui';
import { useToast } from '../components/ToastProvider';
import api from '../api';

const EMPTY_FORM = { id: '', name: '', category: '', sku: '', barcode: '', unit_price: '', unit_cost: '', min_stock: '', max_stock: '' };

export const Inventory = ({ role }) => {
  const { showToast } = useToast();
  const [products, setProducts]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState('');
  const [showAdd, setShowAdd]     = useState(false);
  const [editProd, setEditProd]   = useState(null);   // product being edited
  const [form, setForm]           = useState(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(null);  // product id pending confirm

  const fetchProducts = async () => {
    try {
      const d = await api.get('/tenants/products');
      setProducts(d || []);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchProducts(); }, []);

  const filtered = products.filter(p => {
    if (!search) return true;
    const q = search.toLowerCase();
    return p.name?.toLowerCase().includes(q) || p.sku?.toLowerCase().includes(q) || p.category?.toLowerCase().includes(q);
  });

  // ── Validation ──────────────────────────────────────────────────────────────
  const validate = (f, isEdit) => {
    const errs = {};
    if (!isEdit && !f.id.trim()) errs.id = 'Required';
    if (!f.name.trim())         errs.name = 'Required';
    if (!f.category.trim())     errs.category = 'Required';
    if (!f.unit_price)          errs.unit_price = 'Required';
    return errs;
  };

  // ── Add ─────────────────────────────────────────────────────────────────────
  const openAdd = () => { setForm(EMPTY_FORM); setFormErrors({}); setShowAdd(true); };

  const handleAdd = async () => {
    const errs = validate(form, false);
    if (Object.keys(errs).length) { setFormErrors(errs); return; }
    setSubmitting(true);
    try {
      await api.post('/tenants/products', {
        id: form.id, name: form.name, category: form.category,
        sku: form.sku || null, barcode: form.barcode || null,
        unit_price: parseFloat(form.unit_price),
        unit_cost: parseFloat(form.unit_cost) || 0,
        min_stock: parseInt(form.min_stock) || 0,
        max_stock: parseInt(form.max_stock) || null,
      });
      showToast('Product added', 'success');
      setShowAdd(false);
      fetchProducts();
    } catch (e) { showToast(e.message, 'error'); }
    finally { setSubmitting(false); }
  };

  // ── Edit ────────────────────────────────────────────────────────────────────
  const openEdit = (p) => {
    setForm({ id: p.id, name: p.name, category: p.category, sku: p.sku || '', barcode: p.barcode || '', unit_price: String(p.unit_price || ''), unit_cost: String(p.unit_cost || ''), min_stock: String(p.min_stock || ''), max_stock: String(p.max_stock || '') });
    setFormErrors({});
    setEditProd(p);
  };

  const handleEdit = async () => {
    const errs = validate(form, true);
    if (Object.keys(errs).length) { setFormErrors(errs); return; }
    setSubmitting(true);
    try {
      await api.put(`/tenants/products/${editProd.id}`, {
        name: form.name, category: form.category,
        sku: form.sku || null, barcode: form.barcode || null,
        unit_price: parseFloat(form.unit_price),
        unit_cost: parseFloat(form.unit_cost) || 0,
        min_stock: parseInt(form.min_stock) || 0,
        max_stock: parseInt(form.max_stock) || null,
      });
      showToast('Product updated', 'success');
      setEditProd(null);
      fetchProducts();
    } catch (e) { showToast(e.message, 'error'); }
    finally { setSubmitting(false); }
  };

  // ── Deactivate ───────────────────────────────────────────────────────────────
  const handleDeactivate = async (id) => {
    try {
      await api.del(`/tenants/products/${id}`);
      showToast('Product deactivated', 'info');
      setConfirmDeactivate(null);
      fetchProducts();
    } catch (e) { showToast(e.message, 'error'); }
  };

  // ── Form field helper ───────────────────────────────────────────────────────
  const field = (key, label, type = 'text') => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label style={{ color: '#94a3b8', fontSize: '12px' }}>{label}{formErrors[key] && <span style={{ color: '#f87171', marginLeft: '6px' }}>{formErrors[key]}</span>}</label>
      <input
        type={type} value={form[key]}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
        style={{ padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: `1px solid ${formErrors[key] ? '#f87171' : 'rgba(255,255,255,0.12)'}`, color: '#fff' }}
      />
    </div>
  );

  const columns = [
    { header: 'SKU',      render: r => <span style={{ fontFamily: 'monospace', fontSize: '12px', color: '#94a3b8' }}>{r.sku || '—'}</span> },
    { header: 'Name',     accessor: 'name' },
    { header: 'Category', accessor: 'category' },
    { header: 'Price',    render: r => `$${Number(r.unit_price || 0).toFixed(2)}` },
    { header: 'Cost',     render: r => `$${Number(r.unit_cost || 0).toFixed(2)}` },
    {
      header: 'Stock', render: r => {
        const isLow = r.min_stock != null && r.stock_level <= r.min_stock;
        return (
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span style={{ color: isLow ? '#f87171' : '#e2e8f0' }}>{r.stock_level ?? 0}</span>
            {isLow && <span style={{ background: 'rgba(248,113,113,0.2)', color: '#f87171', fontSize: '10px', fontWeight: 'bold', padding: '2px 6px', borderRadius: '10px' }}>LOW</span>}
          </div>
        );
      }
    },
    { header: 'Status', render: r => <StatusBadge status={r.is_active !== false ? 'active' : 'inactive'} /> },
    {
      header: 'Actions', render: r => (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button onClick={() => openEdit(r)} style={actionBtn}>Edit</button>
          <RoleGate allowedRoles={['owner', 'inventory_manager']} currentRole={role}>
            {confirmDeactivate === r.id ? (
              <>
                <button onClick={() => handleDeactivate(r.id)} style={{ ...actionBtn, color: '#f87171', borderColor: '#f87171' }}>Yes</button>
                <button onClick={() => setConfirmDeactivate(null)} style={actionBtn}>Cancel</button>
              </>
            ) : (
              r.is_active !== false && <button onClick={() => setConfirmDeactivate(r.id)} style={{ ...actionBtn, color: '#fbbf24', borderColor: '#fbbf24' }}>Deactivate</button>
            )}
          </RoleGate>
        </div>
      )
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
        <h2 style={{ margin: 0 }}>Inventory &amp; Products</h2>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="🔍  Filter by name, SKU, category…"
            style={{ padding: '10px 14px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', width: '260px' }} />
          <RoleGate allowedRoles={['owner', 'inventory_manager']} currentRole={role}>
            <button onClick={openAdd} style={{ padding: '10px 20px', borderRadius: '8px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>+ Add Product</button>
          </RoleGate>
        </div>
      </div>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: '#64748b' }}>Loading inventory…</div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px', color: '#64748b' }}>
            {products.length === 0
              ? <><p>No products yet.</p><RoleGate allowedRoles={['owner','inventory_manager']} currentRole={role}><button onClick={openAdd} style={{ padding: '10px 20px', borderRadius: '8px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>Add your first product →</button></RoleGate></>
              : 'No results for that search.'}
          </div>
        ) : (
          <DataTable columns={columns} data={filtered} />
        )}
      </Card>

      {/* Add Modal */}
      {showAdd && (
        <Modal title="Add Product" onClose={() => setShowAdd(false)}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            {field('id', 'Product ID *')}
            {field('name', 'Name *')}
            {field('category', 'Category *')}
            {field('sku', 'SKU')}
            {field('barcode', 'Barcode')}
            {field('unit_price', 'Unit Price *', 'number')}
            {field('unit_cost', 'Unit Cost', 'number')}
            {field('min_stock', 'Min Stock', 'number')}
            {field('max_stock', 'Max Stock', 'number')}
          </div>
          <div style={{ display: 'flex', gap: '10px', marginTop: '20px', justifyContent: 'flex-end' }}>
            <button onClick={() => setShowAdd(false)} style={cancelBtn}>Cancel</button>
            <button onClick={handleAdd} disabled={submitting} style={submitBtn}>{submitting ? 'Saving…' : 'Add Product'}</button>
          </div>
        </Modal>
      )}

      {/* Edit Modal */}
      {editProd && (
        <Modal title={`Edit: ${editProd.name}`} onClose={() => setEditProd(null)}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            {field('name', 'Name *')}
            {field('category', 'Category *')}
            {field('sku', 'SKU')}
            {field('barcode', 'Barcode')}
            {field('unit_price', 'Unit Price *', 'number')}
            {field('unit_cost', 'Unit Cost', 'number')}
            {field('min_stock', 'Min Stock', 'number')}
            {field('max_stock', 'Max Stock', 'number')}
          </div>
          <div style={{ display: 'flex', gap: '10px', marginTop: '20px', justifyContent: 'flex-end' }}>
            <button onClick={() => setEditProd(null)} style={cancelBtn}>Cancel</button>
            <button onClick={handleEdit} disabled={submitting} style={submitBtn}>{submitting ? 'Saving…' : 'Save Changes'}</button>
          </div>
        </Modal>
      )}
    </div>
  );
};

const actionBtn = { padding: '5px 12px', borderRadius: '5px', background: 'transparent', border: '1px solid rgba(255,255,255,0.15)', color: '#94a3b8', cursor: 'pointer', fontSize: '12px' };
const cancelBtn = { padding: '10px 20px', borderRadius: '7px', background: 'rgba(255,255,255,0.06)', color: '#94a3b8', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer' };
const submitBtn = { padding: '10px 24px', borderRadius: '7px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' };
