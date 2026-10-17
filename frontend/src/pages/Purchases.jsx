import React, { useState, useEffect } from 'react';
import { Card, DataTable, RoleGate, Modal } from '../components/ui';
import { useToast } from '../components/ToastProvider';
import api from '../api';

const fmt = n => `$${Number(n || 0).toFixed(2)}`;

export const Purchases = ({ role }) => {
  const { showToast } = useToast();
  const [pos, setPos]                     = useState([]);
  const [suppliers, setSuppliers]         = useState([]);
  const [products, setProducts]           = useState([]);
  const [loading, setLoading]             = useState(true);
  const [showSupplierModal, setShowSupplierModal] = useState(false);
  const [showPOModal, setShowPOModal]     = useState(false);
  const [receiving, setReceiving]         = useState(null);    // po id being received

  // Supplier form
  const [suppForm, setSuppForm] = useState({ name: '', contact_phone: '', contact_email: '', address: '' });

  // PO form
  const [poSupplierId, setPoSupplierId] = useState('');
  const [poLines, setPoLines]           = useState([{ product_id: '', qty: 1, unit_cost: '' }]);
  const [poSubmitting, setPoSubmitting] = useState(false);

  const fetchAll = async () => {
    try {
      const [p, s, pr] = await Promise.all([
        api.get('/tenants/purchase-orders'),
        api.get('/tenants/supplier-profiles'),
        api.get('/tenants/products'),
      ]);
      setPos(p || []);
      setSuppliers(s || []);
      setProducts(pr || []);
    } catch (e) { showToast(e.message, 'error'); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchAll(); }, []);

  // ── Supplier creation ───────────────────────────────────────────────────────
  const handleAddSupplier = async () => {
    if (!suppForm.name.trim()) { showToast('Supplier name is required', 'error'); return; }
    try {
      await api.post('/tenants/supplier-profiles', suppForm);
      showToast('Supplier added', 'success');
      setShowSupplierModal(false);
      setSuppForm({ name: '', contact_phone: '', contact_email: '', address: '' });
      const s = await api.get('/tenants/supplier-profiles');
      setSuppliers(s || []);
    } catch (e) { showToast(e.message, 'error'); }
  };

  // ── PO creation ─────────────────────────────────────────────────────────────
  const addLine = () => setPoLines(l => [...l, { product_id: '', qty: 1, unit_cost: '' }]);
  const removeLine = (i) => setPoLines(l => l.filter((_, idx) => idx !== i));
  const updateLine = (i, key, val) => setPoLines(l => l.map((ln, idx) => idx === i ? { ...ln, [key]: val } : ln));

  const poTotal = poLines.reduce((s, l) => s + (parseFloat(l.unit_cost) || 0) * (parseInt(l.qty) || 0), 0);

  const handleCreatePO = async () => {
    if (!poSupplierId) { showToast('Select a supplier', 'error'); return; }
    if (poLines.some(l => !l.product_id || !l.qty || !l.unit_cost)) { showToast('Fill all line items', 'error'); return; }
    setPoSubmitting(true);
    try {
      await api.post('/tenants/purchase-orders', {
        supplier_profile_id: poSupplierId,
        items: poLines.map(l => ({ product_id: l.product_id, qty: parseInt(l.qty), unit_cost: parseFloat(l.unit_cost) })),
      });
      showToast('Purchase order created', 'success');
      setShowPOModal(false);
      setPoSupplierId(''); setPoLines([{ product_id: '', qty: 1, unit_cost: '' }]);
      fetchAll();
    } catch (e) { showToast(e.message, 'error'); }
    finally { setPoSubmitting(false); }
  };

  // ── Receive PO ──────────────────────────────────────────────────────────────
  const handleReceive = async (id) => {
    setReceiving(id);
    try {
      await api.post(`/tenants/purchase-orders/${id}/receive`, {});
      showToast('PO received — inventory updated ✓', 'success');
      fetchAll();
    } catch (e) { showToast(e.message, 'error'); }
    finally { setReceiving(null); }
  };

  const statusColor = { ordered: '#60a5fa', received: '#4ade80', cancelled: '#f87171' };

  const columns = [
    { header: 'PO ID', render: r => <span style={{ fontFamily: 'monospace', fontSize: '12px', color: '#94a3b8' }}>{r.id?.slice(0, 8)}…</span> },
    { header: 'Supplier', render: r => {
      const sp = suppliers.find(s => s.id === r.supplier_profile_id);
      return sp?.name || r.supplier_profile_id?.slice(0, 10) || '—';
    }},
    { header: 'Date', render: r => r.created_at ? new Date(r.created_at).toLocaleDateString() : '—' },
    { header: 'Status', render: r => (
      <span style={{ background: `${statusColor[r.status] || '#94a3b8'}22`, color: statusColor[r.status] || '#94a3b8', padding: '3px 10px', borderRadius: '12px', fontSize: '12px', fontWeight: 600 }}>
        {r.status}
      </span>
    )},
    { header: 'Items', render: r => r.items?.length ?? 0 },
    { header: 'Total Cost', render: r => fmt(r.items?.reduce((s, i) => s + (i.qty * i.unit_cost), 0)) },
    {
      header: 'Actions', render: r => r.status === 'ordered' ? (
        <RoleGate allowedRoles={['owner', 'inventory_manager', 'procurement_officer']} currentRole={role}>
          <button
            onClick={() => handleReceive(r.id)}
            disabled={receiving === r.id}
            style={{ padding: '6px 14px', borderRadius: '6px', background: 'rgba(74,222,128,0.15)', color: '#4ade80', border: '1px solid #4ade80', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}
          >
            {receiving === r.id ? 'Receiving…' : '✓ Receive'}
          </button>
        </RoleGate>
      ) : null
    },
  ];

  const selectStyle = { padding: '10px', borderRadius: '6px', background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', width: '100%' };
  const inputStyle  = { padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', width: '100%', boxSizing: 'border-box' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>Purchase Orders</h2>
        <RoleGate allowedRoles={['owner', 'procurement_officer']} currentRole={role}>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button onClick={() => setShowSupplierModal(true)} style={{ padding: '10px 18px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', color: '#e2e8f0', border: '1px solid rgba(255,255,255,0.12)', cursor: 'pointer', fontWeight: 600 }}>+ Add Supplier</button>
            <button onClick={() => setShowPOModal(true)} style={{ padding: '10px 18px', borderRadius: '8px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>Create PO</button>
          </div>
        </RoleGate>
      </div>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: '#64748b' }}>Loading purchase orders…</div>
        ) : pos.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px', color: '#64748b' }}>
            <p>No purchase orders yet.</p>
            <RoleGate allowedRoles={['owner', 'procurement_officer']} currentRole={role}>
              <button onClick={() => setShowPOModal(true)} style={{ padding: '10px 20px', borderRadius: '8px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>Create your first PO →</button>
            </RoleGate>
          </div>
        ) : (
          <DataTable columns={columns} data={pos} />
        )}
      </Card>

      {/* Add Supplier Modal */}
      {showSupplierModal && (
        <Modal title="Add Supplier Profile" onClose={() => setShowSupplierModal(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {[['name', 'Company Name *'], ['contact_phone', 'Contact Phone'], ['contact_email', 'Contact Email'], ['address', 'Address']].map(([k, lbl]) => (
              <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ color: '#94a3b8', fontSize: '12px' }}>{lbl}</label>
                <input value={suppForm[k]} onChange={e => setSuppForm(f => ({ ...f, [k]: e.target.value }))} style={inputStyle} />
              </div>
            ))}
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
              <button onClick={() => setShowSupplierModal(false)} style={cancelBtn}>Cancel</button>
              <button onClick={handleAddSupplier} style={primaryBtn}>Save Supplier</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Create PO Modal */}
      {showPOModal && (
        <Modal title="Create Purchase Order" onClose={() => setShowPOModal(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ color: '#94a3b8', fontSize: '12px' }}>Supplier *</label>
              <select value={poSupplierId} onChange={e => setPoSupplierId(e.target.value)} style={selectStyle}>
                <option value="">— Select supplier —</option>
                {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <label style={{ color: '#94a3b8', fontSize: '12px' }}>Line Items *</label>
                <button onClick={addLine} style={{ ...cancelBtn, fontSize: '12px', padding: '5px 10px' }}>+ Add Line</button>
              </div>
              {poLines.map((ln, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 100px 32px', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
                  <select value={ln.product_id} onChange={e => updateLine(i, 'product_id', e.target.value)} style={selectStyle}>
                    <option value="">— Product —</option>
                    {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <input type="number" min="1" value={ln.qty} onChange={e => updateLine(i, 'qty', e.target.value)} placeholder="Qty" style={inputStyle} />
                  <input type="number" step="0.01" value={ln.unit_cost} onChange={e => updateLine(i, 'unit_cost', e.target.value)} placeholder="Unit Cost" style={inputStyle} />
                  <button onClick={() => removeLine(i)} disabled={poLines.length === 1} style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '18px', padding: 0 }}>✕</button>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', color: '#e2e8f0', fontWeight: 'bold', fontSize: '15px' }}>
              Total: <span style={{ color: '#4ade80', marginLeft: '8px' }}>{fmt(poTotal)}</span>
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowPOModal(false)} style={cancelBtn}>Cancel</button>
              <button onClick={handleCreatePO} disabled={poSubmitting} style={primaryBtn}>{poSubmitting ? 'Creating…' : 'Create PO'}</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

const cancelBtn  = { padding: '10px 18px', borderRadius: '7px', background: 'rgba(255,255,255,0.06)', color: '#94a3b8', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer' };
const primaryBtn = { padding: '10px 22px', borderRadius: '7px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' };
