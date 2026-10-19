import { useEffect, useId } from 'react';
import clsx from 'clsx';
import { AlertTriangle, Inbox, Loader2, X } from 'lucide-react';

// ── Buttons ────────────────────────────────────────────────────────────────

const BTN_VARIANTS = {
  primary:   'bg-primary text-on-primary hover:bg-primary-hover shadow-card',
  secondary: 'bg-surface text-ink border border-line hover:bg-surface-2 hover:border-line-strong',
  ghost:     'text-ink-2 hover:bg-surface-2 hover:text-ink',
  danger:    'bg-danger text-white hover:opacity-90',
  'danger-ghost': 'text-danger hover:bg-danger-soft',
  success:   'bg-success text-white hover:opacity-90',
};
const BTN_SIZES = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-9 px-4 text-sm gap-2',
  lg: 'h-11 px-5 text-sm gap-2',
  icon: 'h-9 w-9 justify-center',
};

export function Button({ variant = 'primary', size = 'md', loading = false, icon: Icon, className, children, disabled, ...props }) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={clsx(
        'inline-flex shrink-0 items-center justify-center rounded-lg font-medium whitespace-nowrap transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        BTN_VARIANTS[variant], BTN_SIZES[size], className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : Icon && <Icon className="size-4" />}
      {children}
    </button>
  );
}

// ── Surfaces ───────────────────────────────────────────────────────────────

export function Card({ title, subtitle, icon: Icon, actions, className, bodyClassName, children, padded = true }) {
  return (
    <section className={clsx('min-w-0 rounded-xl border border-line bg-surface shadow-card', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-2.5">
            {Icon && <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary"><Icon className="size-4" /></span>}
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-ink">{title}</h3>
              {subtitle && <p className="truncate text-xs text-muted">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx(padded && 'p-5', bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const TONES = {
  neutral: 'bg-surface-2 text-ink-2',
  primary: 'bg-primary-soft text-primary',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger:  'bg-danger-soft text-danger',
  info:    'bg-info-soft text-info',
  violet:  'bg-violet-soft text-violet',
};

export function Badge({ tone = 'neutral', className, children, dot = false }) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap', TONES[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function IconTile({ icon: Icon, tone = 'primary', className }) {
  return (
    <span className={clsx('grid size-10 shrink-0 place-items-center rounded-xl', TONES[tone], className)}>
      <Icon className="size-5" />
    </span>
  );
}

export function StatCard({ label, value, hint, icon, tone = 'primary', loading }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">{label}</p>
          {loading
            ? <div className="skeleton mt-2 h-7 w-24 rounded" />
            : <p className="num mt-1 truncate text-2xl font-semibold tracking-tight text-ink">{value}</p>}
          {hint && <p className="mt-1 truncate text-xs text-muted">{hint}</p>}
        </div>
        {icon && <IconTile icon={icon} tone={tone} />}
      </div>
    </div>
  );
}

export function Progress({ value, tone = 'primary', className }) {
  const bar = { primary: 'bg-primary', success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger', info: 'bg-info', violet: 'bg-violet' }[tone];
  return (
    <div className={clsx('h-2 w-full overflow-hidden rounded-full bg-surface-2', className)}>
      <div className={clsx('h-full rounded-full transition-all', bar)} style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

// ── Feedback ───────────────────────────────────────────────────────────────

export function Empty({ icon: Icon = Inbox, title, children, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <span className="mb-3 grid size-11 place-items-center rounded-full bg-surface-2 text-muted"><Icon className="size-5" /></span>
      <p className="text-sm font-medium text-ink">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children, className }) {
  if (!children) return null;
  return (
    <div className={clsx('flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2.5 text-sm text-danger', className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function Skeleton({ className }) {
  return <div className={clsx('skeleton rounded-lg', className)} />;
}

export function Spinner({ className }) {
  return <Loader2 className={clsx('size-5 animate-spin text-muted', className)} />;
}

// ── Forms ──────────────────────────────────────────────────────────────────

export function Field({ label, error, hint, children, className }) {
  return (
    <label className={clsx('block', className)}>
      {label && (
        <span className="label">
          {label}
          {error && <span className="ml-2 font-normal text-danger">{error}</span>}
        </span>
      )}
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Input({ className, invalid, ...props }) {
  return <input className={clsx('input', invalid && 'border-danger', className)} {...props} />;
}

export function Select({ className, children, ...props }) {
  return <select className={clsx('input pr-8', className)} {...props}>{children}</select>;
}

export function Segmented({ options, value, onChange, className }) {
  return (
    <div className={clsx('inline-flex rounded-lg border border-line bg-surface-2 p-0.5', className)}>
      {options.map(o => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={clsx(
            'flex-1 rounded-md px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors',
            value === o.value ? 'bg-surface text-ink shadow-card dark:bg-line-strong' : 'text-muted hover:text-ink',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ── Table ──────────────────────────────────────────────────────────────────

/** columns: [{ header, accessor | render(row), align, className, wrap }] — cells don't wrap unless wrap is set */
export function Table({ columns, rows, onRowClick, rowKey = 'id', empty, dense = false }) {
  if (!rows?.length) return empty ?? <Empty title="Nothing here yet" />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line">
            {columns.map((c, i) => (
              <th key={i} className={clsx('px-3 py-2.5 first:pl-5 last:pr-5 text-left text-xs font-medium whitespace-nowrap text-muted', c.align === 'right' && 'text-right', c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr
              key={r[rowKey] ?? ri}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={clsx('border-b border-line last:border-0', onRowClick && 'cursor-pointer hover:bg-surface-2')}
            >
              {columns.map((c, ci) => (
                <td key={ci} className={clsx('px-3 text-ink-2 first:pl-5 last:pr-5', dense ? 'py-2' : 'py-3', !c.wrap && 'whitespace-nowrap', c.align === 'right' && 'num text-right', c.className)}>
                  {c.render ? c.render(r) : (r[c.accessor] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Overlays ───────────────────────────────────────────────────────────────

export function Modal({ open = true, onClose, title, description, children, footer, size = 'md' }) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  const width = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }[size];
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onMouseDown={e => e.stopPropagation()}
        className={clsx('animate-in flex max-h-[92vh] w-full flex-col rounded-t-2xl border border-line bg-surface shadow-pop sm:rounded-2xl', width)}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-ink">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close"><X className="size-4" /></Button>
        </header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</footer>}
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, description, children, footer }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onMouseDown={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        onMouseDown={e => e.stopPropagation()}
        className="animate-in flex h-full w-full max-w-xl flex-col border-l border-line bg-surface shadow-pop"
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-ink">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close"><X className="size-4" /></Button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</footer>}
      </aside>
    </div>
  );
}

// Renders the backend's lightweight markdown (headings, bold, bullets) safely
export function Markdown({ text, className }) {
  if (!text) return null;
  const inline = (s, key) => s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={`${key}-${i}`} className="font-semibold text-ink">{part.slice(2, -2)}</strong>
      : part);
  return (
    <div className={clsx('space-y-1.5 text-sm leading-relaxed text-ink-2', className)}>
      {text.split('\n').map((line, i) => {
        const t = line.trim();
        if (!t) return null;
        if (t.startsWith('#')) return <p key={i} className="pt-2 text-sm font-semibold text-ink">{inline(t.replace(/^#+\s*/, ''), i)}</p>;
        const bullet = t.match(/^(\*|-)\s+(.*)/);
        if (bullet) {
          const nested = /^\s+/.test(line);
          return (
            <p key={i} className={clsx('flex gap-2', nested && 'pl-5')}>
              <span className="text-muted">•</span>
              <span>{inline(bullet[2], i)}</span>
            </p>
          );
        }
        return <p key={i}>{inline(t, i)}</p>;
      })}
    </div>
  );
}
