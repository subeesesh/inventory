const currencyFmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compactFmt = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 });

export const money = (n) => currencyFmt.format(Number(n) || 0);

export const moneyCompact = (n) => {
  const v = Number(n) || 0;
  return Math.abs(v) >= 10000 ? `$${compactFmt.format(v)}` : money(v);
};

export const num = (n, digits = 0) =>
  (Number(n) || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const pct = (ratio, digits = 0) => `${((Number(ratio) || 0) * 100).toFixed(digits)}%`;

export const humanize = (s) => (s || '').replace(/_/g, ' ');

export const titleCase = (s) => humanize(s).replace(/\b\w/g, c => c.toUpperCase());

// The API returns naive UTC timestamps ("2026-10-19T06:21:34"); mark them as UTC
// so they display in local time. Plain dates ("2026-10-19") are left alone.
const parse = (d) => (typeof d === 'string' && /T\d{2}:\d{2}/.test(d) && !/(Z|[+-]\d{2}:?\d{2})$/.test(d) ? new Date(`${d}Z`) : new Date(d));

export const date = (d) => {
  if (!d) return '—';
  const v = parse(d);
  return Number.isNaN(v.getTime()) ? '—' : v.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};

export const dateTime = (d) => {
  if (!d) return '—';
  const v = parse(d);
  return Number.isNaN(v.getTime()) ? '—' : v.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

export const shortDate = (d) => {
  const v = new Date(d);
  return Number.isNaN(v.getTime()) ? '' : v.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
};

export const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// A fused recommendation, shown on its decision type's axis
export const formatRecommendation = (value, decisionType) => {
  if (typeof value !== 'number') return '—';
  switch (decisionType) {
    case 'price_adjustment':          return `${value >= 0 ? '+' : '−'}${money(Math.abs(value))}`;
    case 'promotion_trigger':         return `${(value * 100).toFixed(1)}% discount`;
    case 'customer_retention_action': return `${(value * 100).toFixed(0)}% retention level`;
    case 'staffing_adjustment':       return `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)} h`;
    default:                          return `${value.toFixed(1)} units`;
  }
};
