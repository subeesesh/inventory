import React, { useState, useEffect } from 'react';
import { Card, DataTable, Modal } from '../components/ui';
import { useToast } from '../components/ToastProvider';
import api from '../api';

export const Customers = () => {
  const { showToast } = useToast();
  const [customers, setCustomers]       = useState([]);
  const [loading, setLoading]           = useState(true);
  const [search, setSearch]             = useState('');
  const [showNew, setShowNew]           = useState(false);
  const [form, setForm]                 = useState({ name: '', phone: '', email: '' });
  const [nameErr, setNameErr]           = useState('');
  const [submitting, setSubmitting]     = useState(false);
  const [detailCustomer, setDetailCustomer] = useState(null);
  const [custSales, setCustSales]       = useState([]);
  const [salesLoading, setSalesLoading] = useState(false);

  const fetchCustomers = async () => {
    try {
      const d = await api.get('/tenants/customers');
      setCustomers(d || []);
    } catch (e) { showToast(e.message, 'error'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchCustomers(); }, []);

  const filtered = customers.filter(c => {
    const q = search.toLowerCase();
    return !search || c.name?.toLowerCase().includes(q) || c.phone?.includes(search);
  });

  const handleAdd = async () => {
    if (!form.name.trim()) { setNameErr('Name is required'); return; }
    setSubmitting(true);
    try {
      await api.post('/tenants/customers', { name: form.name, phone: form.phone || null, email: form.email || null });
      showToast('Customer added', 'success');
      setShowNew(false);
      setForm({ name: '', phone: '', email: '' });
      setNameErr('');
      fetchCustomers();
    } catch (e) { showToast(e.message, 'error'); }
    finally { setSubmitting(false); }
  };

  const openDetail = async (c) => {
    setDetailCustomer(c);
    setSalesLoading(true);
    try {
      const sales = await api.get('/tenants/sales');
      setCustSales((sales || []).filter(s => s.customer_id === c.id));
    } catch (_) { setCustSales([]); }
    finally { setSalesLoading(false); }
  };

  const columns = [
    { header: 'Name', accessor: 'name' },
    { header: 'Phone', render: r => r.phone || '—' },
    { header: 'Email', render: r => r.email || '—' },
    { header: 'Added', render: r => r.created_at ? new Date(r.created_at).toLocaleDateString() : '—' },
  ];

  const salesCols = [
    { header: 'Date', render: r => r.created_at ? new Date(r.created_at).toLocaleDateString() : '—' },
    { header: 'Total', render: r => `$${Number(r.total || 0).toFixed(2)}` },
    { header: 'Payment', accessor: 'payment_method' },
    { header: 'Items', render: r => r.items?.length ?? '—' },
  ];

  const inputStyle = { padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', width: '100%', boxSizing: 'border-box' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
        <h2 style={{ margin: 0 }}>Customers</h2>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="🔍  Search by name or phone…"
            style={{ padding: '10px 14px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', width: '240px' }} />
          <button onClick={() => { setShowNew(true); setForm({ name: '', phone: '', email: '' }); setNameErr(''); }}
            style={{ padding: '10px 20px', borderRadius: '8px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>
            + New Customer
          </button>
        </div>
      </div>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: '#64748b' }}>Loading customers…</div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px', color: '#64748b' }}>
            {customers.length === 0
              ? <><p>No customers yet.</p><button onClick={() => setShowNew(true)} style={{ padding: '10px 20px', borderRadius: '8px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>Add your first customer →</button></>
              : 'No customers match that search.'}
          </div>
        ) : (
          <DataTable columns={columns} data={filtered} onRowClick={openDetail} />
        )}
      </Card>

      {/* New Customer Modal */}
      {showNew && (
        <Modal title="New Customer" onClose={() => setShowNew(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ color: '#94a3b8', fontSize: '12px' }}>Name * {nameErr && <span style={{ color: '#f87171' }}>{nameErr}</span>}</label>
              <input value={form.name} onChange={e => { setForm(f => ({ ...f, name: e.target.value })); setNameErr(''); }} style={{ ...inputStyle, borderColor: nameErr ? '#f87171' : 'rgba(255,255,255,0.12)' }} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ color: '#94a3b8', fontSize: '12px' }}>Phone</label>
              <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ color: '#94a3b8', fontSize: '12px' }}>Email</label>
              <input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
              <button onClick={() => setShowNew(false)} style={cancelBtn}>Cancel</button>
              <button onClick={handleAdd} disabled={submitting} style={primaryBtn}>{submitting ? 'Saving…' : 'Add Customer'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Customer Detail Modal */}
      {detailCustomer && (
        <Modal title={detailCustomer.name} onClose={() => { setDetailCustomer(null); setCustSales([]); }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', padding: '16px' }}>
              {[['Phone', detailCustomer.phone || '—'], ['Email', detailCustomer.email || '—'], ['Customer Since', detailCustomer.created_at ? new Date(detailCustomer.created_at).toLocaleDateString() : '—']].map(([l, v]) => (
                <div key={l}>
                  <div style={{ color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{l}</div>
                  <div style={{ color: '#e2e8f0', marginTop: '4px' }}>{v}</div>
                </div>
              ))}
            </div>
            <h4 style={{ margin: 0, color: '#94a3b8', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Purchase History</h4>
            {salesLoading
              ? <div style={{ color: '#64748b', textAlign: 'center', padding: '20px' }}>Loading…</div>
              : custSales.length === 0
                ? <p style={{ color: '#64748b', textAlign: 'center' }}>No purchases on record.</p>
                : <DataTable columns={salesCols} data={custSales} />}
          </div>
        </Modal>
      )}
    </div>
  );
};

const cancelBtn  = { padding: '10px 18px', borderRadius: '7px', background: 'rgba(255,255,255,0.06)', color: '#94a3b8', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer' };
const primaryBtn = { padding: '10px 22px', borderRadius: '7px', background: '#4ade80', color: '#0f172a', border: 'none', fontWeight: 'bold', cursor: 'pointer' };
