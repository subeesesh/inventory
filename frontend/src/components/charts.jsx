import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useChartColors } from '../core/session';
import { shortDate } from '../core/format';

function ChartTooltip({ active, payload, label, formatter, labelFormatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-pop">
      <p className="mb-1 font-medium text-ink">{labelFormatter ? labelFormatter(label) : label}</p>
      {payload.map(p => (
        <p key={p.dataKey} className="flex items-center gap-2 text-ink-2">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          <span className="num">{formatter ? formatter(p.value, p.dataKey) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Single-series trend over time */
export function TrendChart({ data, dataKey, xKey = 'date', height = 260, color = 'primary', formatter, yFormatter }) {
  const c = useChartColors();
  const stroke = c[color] || color;
  const gradId = `grad-${dataKey}-${color}`;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={xKey} tickFormatter={shortDate} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={28} />
        <YAxis stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={56} tickFormatter={yFormatter} />
        <Tooltip content={<ChartTooltip formatter={formatter} labelFormatter={shortDate} />} cursor={{ stroke: c.grid }} />
        <Area type="monotone" dataKey={dataKey} stroke={stroke} strokeWidth={2} fill={`url(#${gradId})`} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars, one per category; `highlight` gets the primary colour, the rest muted */
export function HBarChart({ data, dataKey, labelKey = 'label', height, formatter, highlight, domain }) {
  const c = useChartColors();
  const h = height || Math.max(120, data.length * 38);
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 96, left: 0, bottom: 0 }}>
        <XAxis type="number" hide domain={domain || [0, 'dataMax']} />
        <YAxis type="category" dataKey={labelKey} width={96} stroke={c.axis} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
        <Tooltip content={<ChartTooltip formatter={formatter} />} cursor={{ fill: c.grid, opacity: 0.4 }} />
        <Bar dataKey={dataKey} radius={[0, 6, 6, 0]} barSize={18} label={{ position: 'right', fill: c.axis, fontSize: 11, formatter }}>
          {data.map((d, i) => (
            <Cell key={i} fill={highlight === undefined || highlight(d) ? c.primary : c.grid} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
