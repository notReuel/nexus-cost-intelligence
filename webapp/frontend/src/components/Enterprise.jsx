import { useState, useRef, useEffect } from 'react';
import { Lock, Info, Database, ChevronRight } from 'lucide-react';

// ─── Money formatting (tabular) ──────────────────────────────────────────
export const money = (n, dp = 0) =>
  n == null || isNaN(n) ? '—' :
  `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
export const moneyK = (n) =>
  n == null || isNaN(n) ? '—' :
  Math.abs(n) >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` :
  Math.abs(n) >= 1e3 ? `$${(n / 1e3).toFixed(1)}k` : `$${n.toFixed(0)}`;

// ─── Confidence pill — the product's evidence signature ──────────────────
const CONF = {
  HIGH:     { bg: 'bg-emerald-50', tx: 'text-emerald-700', dot: 'bg-emerald-500', ring: 'ring-emerald-600/20' },
  MEDIUM:   { bg: 'bg-amber-50',   tx: 'text-amber-700',   dot: 'bg-amber-500',   ring: 'ring-amber-600/20' },
  LOW:      { bg: 'bg-orange-50',  tx: 'text-orange-700',  dot: 'bg-orange-500',  ring: 'ring-orange-600/20' },
  NONE:     { bg: 'bg-slate-100',  tx: 'text-slate-500',   dot: 'bg-slate-400',   ring: 'ring-slate-300' },
  MODELLED: { bg: 'bg-sky-50',     tx: 'text-sky-700',     dot: 'bg-sky-500',     ring: 'ring-sky-600/20' },
};
export function ConfidencePill({ level = 'NONE', count }) {
  const c = CONF[level] || CONF.NONE;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm ${c.bg} ${c.tx} ring-1 ${c.ring} text-[10px] font-semibold uppercase tracking-wide whitespace-nowrap`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {level}{count != null && count > 0 ? ` · n=${count}` : ''}
    </span>
  );
}

// ─── Source popover — hover any modelled line to see its provenance ──────
export function SourcePopover({ source }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  if (!source) return null;
  const ops = source.operator_used?.length ? source.operator_used : source.operators;
  return (
    <div className="relative inline-block" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="text-slate-500 hover:text-accent transition-colors p-0.5 rounded-sm"
        title="Show sources"
      >
        <Database className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-6 z-50 w-72 bg-[#FFFFFF] border border-slate-200 rounded-sm shadow-2xl p-3 text-left">
          <div className="flex items-center justify-between mb-2 pb-2 border-b border-slate-200">
            <span className="text-[10px] font-bold uppercase tracking-widest text-accent">Evidence</span>
            <ConfidencePill level={source.confidence} count={source.n_obs} />
          </div>
          {source.note && <p className="text-[11px] text-slate-600 mb-2 italic">{source.note}</p>}
          <dl className="space-y-1.5 text-[11px]">
            <Row label="Observations" value={source.n_obs != null ? `${source.n_obs}` : '—'} />
            <Row label="Operators" value={ops?.length ? ops.join(', ') : '—'} />
            <Row label="Years" value={source.year_range || '—'} />
            {source.median != null && <Row label="Median (USD 2024)"
              value={`$${source.median.toLocaleString('en-US', { maximumFractionDigits: 2 })}`} />}
            {source.low != null && <Row label="Range"
              value={`$${source.low.toLocaleString()} – $${source.high.toLocaleString()}`} />}
          </dl>
        </div>
      )}
    </div>
  );
}
function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500 shrink-0">{label}</dt>
      <dd className="text-slate-800 text-right num-tabular">{value}</dd>
    </div>
  );
}

// ─── Locked / roadmap pill — visible but non-selectable ──────────────────
export function LockedPill({ label, tooltip }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm border border-dashed border-slate-300 bg-slate-100 text-slate-500 text-xs cursor-not-allowed select-none"
      title={tooltip || 'Coming with Phase 3 data acquisition — this option requires additional operator data currently being collected'}
    >
      <Lock className="w-3 h-3" />
      {label}
    </span>
  );
}

// ─── Panel — the dense enterprise container ──────────────────────────────
export function Panel({ title, subtitle, right, children, className = '', num }) {
  return (
    <section className={`bg-[#FFFFFF] border border-slate-200 rounded-sm ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200">
          <div className="flex items-baseline gap-2.5 min-w-0">
            {num && <span className="font-mono text-[11px] text-accent/50">{num}</span>}
            <h3 className="text-[13px] font-semibold text-slate-900 tracking-wide truncate">{title}</h3>
            {subtitle && <span className="text-[11px] text-slate-500 truncate">{subtitle}</span>}
          </div>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

// ─── Segmented control ───────────────────────────────────────────────────
export function Segmented({ label, value, options, onChange, locked = [] }) {
  return (
    <div>
      {label && <label className="block text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-1.5">{label}</label>}
      <div className="flex flex-wrap gap-1">
        {options.map(opt => {
          const v = typeof opt === 'object' ? opt.value : opt;
          const lbl = typeof opt === 'object' ? opt.label : opt;
          const active = v === value;
          return (
            <button key={v} onClick={() => onChange(v)}
              className={`px-2.5 py-1 rounded-sm text-xs font-medium transition-colors border ${
                active ? 'bg-accent text-[#F8FAFC] border-accent font-semibold'
                       : 'bg-slate-100 text-slate-700 border-slate-300 hover:border-accent/50 hover:text-accent'}`}>
              {lbl}
            </button>
          );
        })}
        {locked.map(l => <LockedPill key={l.label} label={l.label} tooltip={l.tooltip} />)}
      </div>
    </div>
  );
}

// ─── Labelled input ──────────────────────────────────────────────────────
export function Field({ label, children, hint }) {
  return (
    <div>
      <label className="block text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-[10px] text-slate-500 mt-1">{hint}</p>}
    </div>
  );
}
export function TextIn(props) {
  return <input {...props}
    className="w-full bg-[#F8FAFC] border border-slate-300 rounded-sm px-2.5 py-1.5 text-sm text-slate-900 num-tabular focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40 transition-colors" />;
}

// ─── Coverage meter ──────────────────────────────────────────────────────
export function CoverageBar({ pct }) {
  const color = pct >= 80 ? 'bg-emerald-400' : pct >= 50 ? 'bg-accent' : 'bg-orange-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold num-tabular text-slate-800">{pct}%</span>
    </div>
  );
}

// ─── Verdict pill for bid ranking ────────────────────────────────────────
export function VerdictPill({ colour, children }) {
  const map = {
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    amber: 'bg-amber-50 text-amber-700 ring-amber-600/20',
    red:   'bg-red-50 text-red-700 ring-red-600/20',
  };
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase tracking-wide ring-1 ${map[colour] || map.amber}`}>{children}</span>;
}
