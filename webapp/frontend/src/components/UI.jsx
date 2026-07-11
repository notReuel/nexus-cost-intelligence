import { useState } from 'react';
import { fmt } from '../lib/api.js';
import { TrendingUp, TrendingDown, AlertCircle, CheckCircle2, XCircle, Info, ChevronDown, ChevronRight } from 'lucide-react';

// ─── Module page header ──────────────────────────────────────────────────
export function PageHeader({ eyebrow, title, subtitle, icon: Icon }) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-2 text-amber text-xs font-bold tracking-[0.2em] uppercase mb-2">
        {Icon && <Icon className="w-4 h-4" />}
        <span>{eyebrow}</span>
      </div>
      <h1 className="text-4xl md:text-5xl font-bold text-balance mb-3 leading-tight">
        {title}
      </h1>
      {subtitle && (
        <p className="text-lg text-slate-300 max-w-3xl leading-relaxed">{subtitle}</p>
      )}
    </div>
  );
}

// ─── Section heading inside a page ──────────────────────────────────────
export function SectionHeader({ label, num }) {
  return (
    <div className="flex items-baseline gap-3 mb-4 mt-8 first:mt-0">
      {num && <span className="font-mono text-amber/60 text-sm">{num}</span>}
      <h2 className="text-amber font-semibold tracking-wide uppercase text-sm">{label}</h2>
      <div className="flex-1 h-px bg-amber/20" />
    </div>
  );
}

// ─── Card wrapper ────────────────────────────────────────────────────────
export function Card({ children, className = '', accent = false }) {
  return (
    <div className={`relative bg-bg-panel rounded-lg border border-slate-700/50 shadow-xl ${className}`}>
      {accent && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-amber rounded-t-lg" />
      )}
      {children}
    </div>
  );
}

// ─── Form input controls (custom, styled) ────────────────────────────────
export function NumberInput({ label, value, onChange, hint, unit, min, max, step = 1 }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-300 mb-1.5 uppercase tracking-wide">
        {label}
      </label>
      <div className="relative">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={min}
          max={max}
          step={step}
          className="w-full bg-bg-dark border border-slate-700 rounded-md px-3 py-2 text-slate-100 font-mono
                     focus:border-amber focus:outline-none focus:ring-1 focus:ring-amber transition-colors"
        />
        {unit && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm pointer-events-none">
            {unit}
          </span>
        )}
      </div>
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  );
}

export function SelectInput({ label, value, onChange, options, hint }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-300 mb-1.5 uppercase tracking-wide">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-bg-dark border border-slate-700 rounded-md px-3 py-2 text-slate-100
                   focus:border-amber focus:outline-none focus:ring-1 focus:ring-amber transition-colors"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  );
}

export function TextInput({ label, value, onChange, placeholder }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-300 mb-1.5 uppercase tracking-wide">
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-bg-dark border border-slate-700 rounded-md px-3 py-2 text-slate-100
                   focus:border-amber focus:outline-none focus:ring-1 focus:ring-amber transition-colors"
      />
    </div>
  );
}

// ─── Result band card (Low/Mid/High display) ────────────────────────────
export function CostBandCard({ band, label, confidence, unit = '' }) {
  const confColor = {
    HIGH: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/5',
    MEDIUM: 'text-amber border-amber/30 bg-amber/5',
    LOW: 'text-rose-400 border-rose-400/30 bg-rose-400/5',
  }[confidence] || 'text-slate-400 border-slate-400/30';

  return (
    <Card accent className="overflow-hidden">
      <div className="px-6 pt-5 pb-3 flex justify-between items-start">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-400 mb-1">{label}</div>
          <div className="text-xs text-slate-500">Low / Mid / High estimate</div>
        </div>
        {confidence && (
          <div className={`px-2 py-1 rounded text-xs font-bold uppercase tracking-wider border ${confColor}`}>
            {confidence} confidence
          </div>
        )}
      </div>
      <div className="grid grid-cols-3 gap-px bg-slate-700/50">
        <div className="bg-bg-panel px-4 py-5 text-center">
          <div className="text-xs text-slate-500 mb-1 uppercase tracking-wide">Low</div>
          <div className="text-2xl md:text-3xl font-bold text-slate-300 num-tabular">{fmt.usd(band.low)}</div>
        </div>
        <div className="bg-amber/10 px-4 py-5 text-center">
          <div className="text-xs text-amber mb-1 uppercase tracking-wide font-bold">Mid</div>
          <div className="text-2xl md:text-3xl font-bold text-amber num-tabular">{fmt.usd(band.mid)}</div>
        </div>
        <div className="bg-bg-panel px-4 py-5 text-center">
          <div className="text-xs text-slate-500 mb-1 uppercase tracking-wide">High</div>
          <div className="text-2xl md:text-3xl font-bold text-slate-300 num-tabular">{fmt.usd(band.high)}</div>
        </div>
      </div>
      {unit && (
        <div className="px-6 py-2 text-xs text-slate-500 border-t border-slate-700/50">
          {unit}
        </div>
      )}
    </Card>
  );
}

// ─── Verdict pill — GREEN/AMBER/RED traffic light ────────────────────────
export function VerdictBadge({ colour, text }) {
  const map = {
    green: { bg: 'bg-emerald-500/15', border: 'border-emerald-400', text: 'text-emerald-300', icon: CheckCircle2 },
    amber: { bg: 'bg-amber/15',       border: 'border-amber',       text: 'text-amber',       icon: AlertCircle },
    red:   { bg: 'bg-rose-500/15',    border: 'border-rose-400',    text: 'text-rose-300',    icon: XCircle },
  };
  const c = map[colour] || map.amber;
  const Icon = c.icon;
  return (
    <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-md border ${c.bg} ${c.border} ${c.text} font-bold`}>
      <Icon className="w-5 h-5 flex-shrink-0" />
      <span>{text}</span>
    </div>
  );
}

// ─── Diagnostic notes box ─────────────────────────────────────────────────
export function DiagnosticsList({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <Card className="border-l-4 border-l-amber">
      <div className="p-5">
        <div className="flex items-center gap-2 text-amber font-bold text-sm mb-3 uppercase tracking-wide">
          <Info className="w-4 h-4" />
          <span>Engine Diagnostics</span>
        </div>
        <ul className="space-y-2">
          {items.map((d, i) => (
            <li key={i} className="text-sm text-slate-300 flex gap-2">
              <span className="text-amber mt-1">•</span>
              <span>{d}</span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

// ─── Breakdown table row ──────────────────────────────────────────────────
export function BreakdownTable({ rows }) {
  // Track which group rows are expanded
  const [expanded, setExpanded] = useState(() => {
    // Default: collapse all groups that have children
    const init = {};
    rows.forEach((r, i) => { if (r.children && r.children.length) init[i] = false; });
    return init;
  });

  const allExpanded = rows.every((r, i) => !r.children?.length || expanded[i]);
  const toggleAll = () => {
    const next = {};
    rows.forEach((r, i) => { if (r.children?.length) next[i] = !allExpanded; });
    setExpanded(next);
  };
  const toggle = (i) => setExpanded((p) => ({ ...p, [i]: !p[i] }));

  return (
    <div className="rounded-lg border border-slate-700/50 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-bg-dark">
          <tr>
            <th className="text-left px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">
              <button onClick={toggleAll} className="flex items-center gap-1.5 hover:text-amber transition-colors">
                {allExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                Component
              </button>
            </th>
            <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Low</th>
            <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-amber font-semibold">Mid</th>
            <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">High</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const hasKids = r.children && r.children.length > 0;
            const isOpen = expanded[i];
            return (
              <FragmentRow
                key={i}
                row={r}
                hasKids={hasKids}
                isOpen={isOpen}
                onToggle={() => toggle(i)}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FragmentRow({ row, hasKids, isOpen, onToggle }) {
  return (
    <>
      <tr
        className={`border-t border-slate-700/30 transition-colors ${hasKids ? 'cursor-pointer hover:bg-bg-panel/70' : 'hover:bg-bg-panel/50'}`}
        onClick={hasKids ? onToggle : undefined}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            {hasKids ? (
              isOpen ? <ChevronDown className="w-4 h-4 text-amber flex-shrink-0" />
                     : <ChevronRight className="w-4 h-4 text-slate-500 flex-shrink-0" />
            ) : <span className="w-4 inline-block" />}
            <span className="text-slate-200 font-medium">{row.component}</span>
            {hasKids && (
              <span className="text-[10px] text-slate-500 bg-bg-dark px-1.5 py-0.5 rounded ml-1">
                {row.children.length} items
              </span>
            )}
          </div>
          {row.note && <div className="text-xs text-slate-500 mt-0.5 ml-5">{row.note}</div>}
        </td>
        <td className="px-4 py-3 text-right text-slate-300 num-tabular">{fmt.usdFull(row.low)}</td>
        <td className="px-4 py-3 text-right text-amber font-semibold num-tabular">{fmt.usdFull(row.mid)}</td>
        <td className="px-4 py-3 text-right text-slate-300 num-tabular">{fmt.usdFull(row.high)}</td>
      </tr>
      {hasKids && isOpen && row.children.map((c, j) => (
        <tr key={j} className="bg-bg-dark/40 border-t border-slate-800/40">
          <td className="px-4 py-2 pl-12">
            <div className="text-slate-400 text-[13px]">{c.label}</div>
            <div className="text-[11px] text-slate-600 mt-0.5 flex gap-2">
              {c.qty != null && <span>{c.qty.toLocaleString()} {c.qty_unit}</span>}
              {c.unit_rate_mid != null && <span>@ ${c.unit_rate_mid.toLocaleString(undefined, {maximumFractionDigits: 2})}{c.unit_rate_unit}</span>}
              {c.note && <span className="italic">{c.note}</span>}
            </div>
          </td>
          <td className="px-4 py-2 text-right text-slate-500 num-tabular text-[13px]">{fmt.usdFull(c.low)}</td>
          <td className="px-4 py-2 text-right text-slate-300 num-tabular text-[13px]">{fmt.usdFull(c.mid)}</td>
          <td className="px-4 py-2 text-right text-slate-500 num-tabular text-[13px]">{fmt.usdFull(c.high)}</td>
        </tr>
      ))}
    </>
  );
}

// ─── Run button ───────────────────────────────────────────────────────────
export function RunButton({ onClick, loading, label = 'Run estimate' }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="w-full bg-amber hover:bg-amber/90 disabled:bg-slate-700 disabled:cursor-not-allowed
                 text-bg-dark font-bold py-3 px-6 rounded-md transition-all
                 uppercase tracking-wider text-sm shadow-lg shadow-amber/20 hover:shadow-amber/40"
    >
      {loading ? 'Computing…' : label}
    </button>
  );
}

// ─── Tiny inline source-anonymous attribution ────────────────────────────
export function SourceNote({ children }) {
  return (
    <p className="text-xs text-slate-500 italic">{children}</p>
  );
}
