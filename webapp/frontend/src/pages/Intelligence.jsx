import { useEffect, useState } from 'react';
import { BarChart3, AlertCircle, CheckCircle2, XCircle, TrendingDown, TrendingUp, Database, Lightbulb } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine, LabelList } from 'recharts';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, SourceNote } from '../components/UI.jsx';

const TABS = [
  { id: 'findings',  label: 'Market findings',     Icon: Lightbulb },
  { id: 'cross',     label: 'Cross-tender (CT)',   Icon: BarChart3 },
  { id: 'coverage',  label: 'Coverage matrix',     Icon: Database },
];

export default function Intelligence() {
  const [tab, setTab] = useState('findings');

  return (
    <div className="space-y-8">
      <PageHeader
        Icon={BarChart3}
        eyebrow="Intelligence layer"
        title="Market intelligence"
        subtitle="What the dataset reveals about cost structures — patterns, deflation signals, procurement philosophies, and coverage gaps. Findings that no Western benchmarking tool surfaces."
      />

      {/* Tab nav */}
      <div className="flex gap-1 border-b border-slate-700">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === id
                ? 'border-amber text-amber'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === 'findings' && <FindingsView />}
      {tab === 'cross'    && <CrossTenderView />}
      {tab === 'coverage' && <CoverageView />}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// TAB 1 — Market findings
// ════════════════════════════════════════════════════════════════════════
function FindingsView() {
  const [data, setData] = useState(null);
  const [err,  setErr]  = useState(null);
  useEffect(() => { api.findings().then(setData).catch(e => setErr(e.message)); }, []);

  if (err)  return <Card className="p-6 text-rose-400">Failed to load: {err}</Card>;
  if (!data) return <Card className="p-12 text-center text-slate-500 animate-pulse">Loading findings…</Card>;

  const sevColor = { green: 'emerald', amber: 'amber', red: 'rose' };
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <StatTile num={data.meta.by_severity.green} label="Validated findings"  colour="emerald" />
        <StatTile num={data.meta.by_severity.amber} label="Market signals"      colour="amber" />
        <StatTile num={data.meta.by_severity.red}   label="Risk flags / gaps"   colour="rose" />
      </div>

      <div className="space-y-4">
        {data.findings.map(f => <FindingCard key={f.id} f={f} />)}
      </div>

      <SourceNote>
        Findings are derived from analysis of the cross-operator normalised dataset. Each finding is reproducible from the underlying tender data and the engine's audit trail.
      </SourceNote>
    </div>
  );
}

function FindingCard({ f }) {
  const colourMap = {
    green: { border: 'border-l-emerald-400', tagBg: 'bg-emerald-500/15', tagText: 'text-emerald-300', Icon: CheckCircle2 },
    amber: { border: 'border-l-amber',       tagBg: 'bg-amber/15',       tagText: 'text-amber',       Icon: AlertCircle },
    red:   { border: 'border-l-rose-400',    tagBg: 'bg-rose-500/15',    tagText: 'text-rose-300',    Icon: XCircle },
  };
  const c = colourMap[f.severity] || colourMap.amber;
  const Icon = c.Icon;
  return (
    <Card className={`p-6 border-l-4 ${c.border}`}>
      <div className="flex items-start gap-4 mb-3">
        <Icon className={`w-6 h-6 ${c.tagText} flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${c.tagBg} ${c.tagText}`}>
              {f.tag}
            </span>
            <span className="text-slate-500 text-xs">Finding #{f.id}</span>
          </div>
          <h3 className="text-lg md:text-xl font-bold text-slate-100 leading-tight mb-3">{f.headline}</h3>
          <p className="text-sm text-slate-300 leading-relaxed">{f.body}</p>
        </div>
      </div>

      {f.evidence && f.evidence.length > 0 && <EvidenceTable rows={f.evidence} tag={f.tag} />}

      <div className={`mt-4 p-3 rounded ${c.tagBg}`}>
        <div className={`text-[10px] font-bold uppercase tracking-wider mb-1 ${c.tagText}`}>So what →</div>
        <p className="text-sm text-slate-200">{f.so_what}</p>
      </div>
    </Card>
  );
}

function EvidenceTable({ rows, tag }) {
  // The shape of each row depends on which finding. Detect by keys.
  if (!rows[0]) return null;
  const keys = Object.keys(rows[0]);

  return (
    <div className="mt-4 rounded border border-slate-700/40 overflow-hidden">
      <table className="w-full text-xs">
        <thead className="bg-bg-dark">
          <tr>
            {keys.map(k => (
              <th key={k} className="px-3 py-2 text-left text-slate-400 font-semibold uppercase tracking-wider">
                {prettyKey(k)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-slate-700/30">
              {keys.map(k => (
                <td key={k} className="px-3 py-1.5 text-slate-300 num-tabular">{formatVal(k, r[k])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function prettyKey(k) {
  return k.replace(/_/g, ' ').replace(/\bpct\b/, '%').replace(/\bcagr\b/i, 'CAGR').replace(/\busd\b/i, 'USD').replace(/\bmusd\b/i, '$M');
}
function formatVal(k, v) {
  if (v == null) return '—';
  if (typeof v === 'number') {
    if (k.endsWith('_pct') || k === 'cagr' || k === 'share' || k === 'delta') {
      const pct = v * 100;
      const sign = pct >= 0 ? '+' : '';
      return `${sign}${pct.toFixed(1)}%`;
    }
    if (k === 'price_musd') return `$${v.toFixed(1)}M`;
    if (k === 'rate' || (k.includes('per_day') && k.includes('usd'))) return `$${v.toFixed(2)}`;
    if (k === 'naoc_2021' || k === 'seplat_2024') return `$${v.toLocaleString()}`;
    if (k === 'actual' || k === 'engine') return v >= 1000 ? `$${v.toLocaleString()}` : `$${v.toFixed(0)}`;
    if (k === 'year') return String(v);
    return v.toLocaleString();
  }
  return String(v);
}

function StatTile({ num, label, colour }) {
  const colourMap = {
    emerald: 'text-emerald-400',
    amber: 'text-amber',
    rose: 'text-rose-400',
  };
  return (
    <Card className="p-5">
      <div className={`text-4xl md:text-5xl font-bold ${colourMap[colour]} num-tabular mb-1`}>{num}</div>
      <div className="text-sm text-slate-300">{label}</div>
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════
// TAB 2 — Cross-Tender CT analysis
// ════════════════════════════════════════════════════════════════════════
function CrossTenderView() {
  const [data, setData] = useState(null);
  useEffect(() => { api.ctCrossTender().then(setData); }, []);

  if (!data) return <Card className="p-12 text-center text-slate-500 animate-pulse">Loading…</Card>;

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI value={`${data.seplat_2024.spread_ratio}×`} label="Seplat 2024 spread"  sub="11 vendors, same scope" />
          <KPI value={`#${data.seplat_2024.winner_rank_by_price}`} label="Winner price rank" sub={`$${data.seplat_2024.winner_price_musd}M won, $${data.seplat_2024.cheapest_price_musd}M lowest`} />
          <KPI value={`${data.deflation.vendors_cutting_rates}/${data.deflation.overlapping_vendors}`} label="Vendors cutting rates" sub="Across NAOC 2021 → Seplat 2024" />
          <KPI value={fmt.pct(data.deflation.avg_rate_cut_pct)} label="Avg rate change" sub="3 of 4 deflated, 1 raised" />
        </div>
      </Card>

      <Card className="p-6">
        <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-1">11-vendor price spread — Seplat 2024 CT tender</h3>
        <p className="text-xs text-slate-500 mb-4">Same scope. Same 10-well program. Vendor identities anonymised.</p>
        <div style={{ width: '100%', height: 360 }}>
          <ResponsiveContainer>
          <BarChart data={data.seplat_2024.distribution} margin={{ top: 10, right: 20, left: 10, bottom: 50 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1F3344" />
            <XAxis dataKey="vendor" tick={{ fill: '#94a3b8', fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'USD millions', angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 11 }} />
            <Tooltip contentStyle={{ background: '#162534', border: '1px solid #2A3A4D', color: '#E2E8EF' }}
                     formatter={(v, name) => name === 'price_musd' ? [`$${v}M`, 'Quote'] : v} />
            <Bar dataKey="price_musd" radius={[4,4,0,0]} isAnimationActive={false}>
              {data.seplat_2024.distribution.map((d, i) => (
                <Cell key={i} fill={d.rank === 1 ? '#E5A445' : '#2EB1A4'} />
              ))}
              <LabelList dataKey="price_musd" position="top" fill="#94a3b8" fontSize={10} formatter={(v) => `$${v}M`} />
            </Bar>
          </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
          <div className="flex items-center gap-2"><span className="w-3 h-3 bg-amber rounded-sm"></span>1st place winner (highest priced)</div>
          <div className="flex items-center gap-2"><span className="w-3 h-3 bg-teal rounded-sm"></span>Other bidders</div>
        </div>
      </Card>

      <Card className="p-6">
        <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-1">Cross-tender vendor rate change (2021 → 2024)</h3>
        <p className="text-xs text-slate-500 mb-4">Same 4 vendors bid both tenders. Same scope envelope. 3 cut rates 40-52%, 1 raised them.</p>
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={data.deflation.detail} margin={{ top: 20, right: 20, left: 10, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F3344" />
              <XAxis dataKey="vendor" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v) => `${(v*100).toFixed(0)}%`} />
              <ReferenceLine y={0} stroke="#475569" />
              <Tooltip contentStyle={{ background: '#162534', border: '1px solid #2A3A4D' }}
                       formatter={(v) => `${(v*100).toFixed(1)}%`} />
              <Bar dataKey="delta_pct" radius={[4,4,0,0]} isAnimationActive={false}>
                {data.deflation.detail.map((d, i) => (
                  <Cell key={i} fill={d.delta_pct < 0 ? '#10b981' : '#ef4444'} />
                ))}
                <LabelList dataKey="delta_pct" position="top" fill="#94a3b8" fontSize={11} formatter={(v) => `${(v*100).toFixed(0)}%`} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 rounded border border-slate-700/40 overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-bg-dark">
              <tr>
                <th className="px-3 py-2 text-left text-slate-400 font-semibold uppercase tracking-wider">Vendor</th>
                <th className="px-3 py-2 text-right text-slate-400 font-semibold uppercase tracking-wider">NAOC 2021 ($/day)</th>
                <th className="px-3 py-2 text-right text-slate-400 font-semibold uppercase tracking-wider">Seplat 2024 ($/day)</th>
                <th className="px-3 py-2 text-right text-slate-400 font-semibold uppercase tracking-wider">3-yr Δ</th>
                <th className="px-3 py-2 text-right text-slate-400 font-semibold uppercase tracking-wider">CAGR</th>
              </tr>
            </thead>
            <tbody>
              {data.deflation.detail.map((d, i) => (
                <tr key={i} className="border-t border-slate-700/30">
                  <td className="px-3 py-1.5 text-slate-200">{d.vendor}</td>
                  <td className="px-3 py-1.5 text-right num-tabular text-slate-300">${d.naoc_2021_usd_per_day.toLocaleString()}</td>
                  <td className="px-3 py-1.5 text-right num-tabular text-slate-300">${d.seplat_2024_usd_per_day.toLocaleString()}</td>
                  <td className={`px-3 py-1.5 text-right num-tabular font-bold ${d.delta_pct < 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {fmt.pct(d.delta_pct)}
                  </td>
                  <td className={`px-3 py-1.5 text-right num-tabular font-bold ${d.cagr < 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {fmt.pct(d.cagr)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-5 border-l-4 border-l-amber">
        <div className="text-amber font-bold text-xs uppercase tracking-wider mb-2">Market signal</div>
        <p className="text-sm text-slate-200 leading-relaxed">{data.so_what}</p>
      </Card>
    </div>
  );
}

function KPI({ value, label, sub }) {
  return (
    <div>
      <div className="text-3xl md:text-4xl font-bold text-amber num-tabular leading-none mb-1">{value}</div>
      <div className="text-xs uppercase tracking-wider text-slate-400 mb-0.5">{label}</div>
      <div className="text-xs text-slate-500 leading-snug">{sub}</div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// TAB 3 — Coverage matrix
// ════════════════════════════════════════════════════════════════════════
function CoverageView() {
  const [data, setData] = useState(null);
  useEffect(() => { api.coverage().then(setData); }, []);

  if (!data) return <Card className="p-12 text-center text-slate-500 animate-pulse">Loading…</Card>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-5">
          <div className="text-3xl font-bold text-amber num-tabular mb-1">{data.meta.total_records}</div>
          <div className="text-xs text-slate-400 uppercase tracking-wider">Total records</div>
        </Card>
        <Card className="p-5">
          <div className="text-3xl font-bold text-amber num-tabular mb-1">{data.meta.unique_combinations}</div>
          <div className="text-xs text-slate-400 uppercase tracking-wider">Dia × terrain combos covered</div>
        </Card>
        <Card className="p-5">
          <div className="text-3xl font-bold text-emerald-400 num-tabular mb-1">{data.meta.high_confidence_combinations}</div>
          <div className="text-xs text-slate-400 uppercase tracking-wider">High-confidence cells</div>
        </Card>
        <Card className="p-5">
          <div className="text-3xl font-bold text-rose-400 num-tabular mb-1">{data.meta.gaps}</div>
          <div className="text-xs text-slate-400 uppercase tracking-wider">Coverage gaps</div>
        </Card>
      </div>

      <Card className="p-6">
        <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-1">Pipeline lay/weld coverage heatmap</h3>
        <p className="text-xs text-slate-500 mb-4">Diameter × terrain. Cells show record count and confidence. Empty cells are data gaps.</p>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="px-3 py-2 text-left text-xs text-slate-400 font-semibold uppercase tracking-wider">Diameter</th>
                {data.terrains.map(t => (
                  <th key={t} className="px-3 py-2 text-center text-xs text-slate-400 font-semibold uppercase tracking-wider">{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.diameters.map(dia => (
                <tr key={dia} className="border-t border-slate-700/30">
                  <td className="px-3 py-2 font-mono text-slate-200">{dia}″</td>
                  {data.terrains.map(t => {
                    const cell = data.cells.find(c => c.dia === dia && c.terrain === t);
                    return <HeatCell key={t} cell={cell} />;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex flex-wrap gap-3 text-xs">
          <Legend colour="bg-emerald-500/30" label="HIGH (3+ records)" />
          <Legend colour="bg-amber/30" label="MEDIUM (2 records)" />
          <Legend colour="bg-rose-500/30" label="LOW (1 record)" />
          <Legend colour="bg-slate-700/30" label="NONE (gap)" />
        </div>
      </Card>

      <Card className="p-6">
        <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-4">Module-level coverage</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/40">
              <th className="px-3 py-2 text-left text-xs text-slate-400 font-semibold uppercase tracking-wider">Module</th>
              <th className="px-3 py-2 text-right text-xs text-slate-400 font-semibold uppercase tracking-wider">Records</th>
              <th className="px-3 py-2 text-right text-xs text-slate-400 font-semibold uppercase tracking-wider">Operators</th>
              <th className="px-3 py-2 text-center text-xs text-slate-400 font-semibold uppercase tracking-wider">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.modules).map(([name, m]) => (
              <tr key={name} className="border-t border-slate-700/30">
                <td className="px-3 py-2 font-semibold text-slate-200">{name}</td>
                <td className="px-3 py-2 text-right num-tabular text-slate-300">{m.records}</td>
                <td className="px-3 py-2 text-right num-tabular text-slate-300">{m.operators}</td>
                <td className="px-3 py-2 text-center">
                  <ConfBadge confidence={m.confidence} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <SourceNote>
        Coverage matrix reflects the lay/weld pivot for Pipeline. The Well and CT modules cover separate scopes with their own confidence ratings shown above. Gaps represent diameter/terrain combinations where the dataset has no records — values for these combinations fall back to the nearest available diameter with downgraded confidence.
      </SourceNote>
    </div>
  );
}

function HeatCell({ cell }) {
  if (!cell || cell.count === 0) {
    return <td className="px-3 py-3 text-center bg-slate-800/30 text-slate-600">—</td>;
  }
  const colour = {
    HIGH:   'bg-emerald-500/20 text-emerald-200',
    MEDIUM: 'bg-amber/20 text-amber',
    LOW:    'bg-rose-500/15 text-rose-300',
  }[cell.confidence] || 'bg-slate-700/30 text-slate-400';
  return (
    <td className={`px-3 py-2 text-center ${colour}`}>
      <div className="text-base font-bold num-tabular">{cell.count}</div>
      <div className="text-[10px] opacity-70">{cell.confidence}</div>
      {cell.median && <div className="text-[10px] mt-0.5 text-slate-300">~${cell.median.toFixed(0)}/m</div>}
    </td>
  );
}

function ConfBadge({ confidence }) {
  const map = {
    HIGH:   'bg-emerald-500/15 text-emerald-300 border-emerald-400/40',
    MEDIUM: 'bg-amber/15 text-amber border-amber/40',
    LOW:    'bg-rose-500/15 text-rose-300 border-rose-400/40',
  };
  return (
    <span className={`inline-block px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded ${map[confidence]}`}>
      {confidence}
    </span>
  );
}

function Legend({ colour, label }) {
  return (
    <div className="flex items-center gap-2 text-slate-400">
      <span className={`w-4 h-4 rounded ${colour}`}></span>
      <span>{label}</span>
    </div>
  );
}
