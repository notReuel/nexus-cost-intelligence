import { useState, useRef, useMemo } from 'react';
import { Upload, FileText, CheckCircle2, AlertCircle, XCircle, HelpCircle, ChevronDown, ChevronRight, DollarSign, TrendingUp, TrendingDown, Layers } from 'lucide-react';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, TextInput, RunButton, SourceNote } from '../components/UI.jsx';

const VERDICT_STYLES = {
  GREEN:     { bg: 'bg-emerald-500/15', border: 'border-emerald-400/40', text: 'text-emerald-300', Icon: CheckCircle2 },
  AMBER:     { bg: 'bg-amber/15',       border: 'border-amber/40',       text: 'text-amber',       Icon: AlertCircle },
  RED:       { bg: 'bg-rose-500/15',    border: 'border-rose-400/40',    text: 'text-rose-300',    Icon: XCircle },
  UNMATCHED: { bg: 'bg-slate-700/20',   border: 'border-slate-600/40',   text: 'text-slate-400',   Icon: HelpCircle },
};

function VerdictPill({ verdict }) {
  const s = VERDICT_STYLES[verdict] || VERDICT_STYLES.UNMATCHED;
  const Icon = s.Icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${s.bg} ${s.border} ${s.text}`}>
      <Icon className="w-3 h-3" />
      {verdict}
    </span>
  );
}

export default function TenderUpload() {
  const [file, setFile] = useState(null);
  const [projectName, setProjectName] = useState('');
  const [vendorName, setVendorName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const handleFile = (f) => {
    setError(null);
    setReport(null);
    if (!f) return;
    if (!f.name.match(/\.(xlsx|xls|csv)$/i)) {
      setError('File must be .xlsx, .xls, or .csv');
      return;
    }
    if (f.size > 20 * 1024 * 1024) {
      setError('File too large (max 20 MB)');
      return;
    }
    setFile(f);
  };

  const runAnalysis = async () => {
    if (!file) { setError('Choose a file first'); return; }
    setLoading(true); setError(null);
    try {
      const r = await api.tenderUpload(file, projectName, vendorName);
      setReport(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        Icon={Upload}
        eyebrow="Phase 1B · Tender intelligence"
        title="Tender Upload & Variance Report"
        subtitle="Upload a vendor BOQ. The platform parses every line, matches it to the benchmark catalogue, and returns line-by-line variance with executive and procurement summaries."
      />

      {!report && (
        <>
          {/* Upload zone */}
          <Card className="p-8">
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault(); setDragOver(false);
                handleFile(e.dataTransfer.files[0]);
              }}
              onClick={() => inputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                dragOver ? 'border-amber bg-amber/5' : 'border-slate-700 hover:border-amber/50'
              }`}>
              <Upload className={`w-12 h-12 mx-auto mb-4 ${dragOver ? 'text-amber' : 'text-slate-500'}`} />
              <div className="text-lg font-bold text-slate-100 mb-1">
                {file ? file.name : 'Drop BOQ here, or click to browse'}
              </div>
              <div className="text-xs text-slate-500">
                {file ? `${(file.size / 1024).toFixed(1)} KB · ready to analyze` : '.xlsx, .xls, .csv — max 20 MB'}
              </div>
              <input
                ref={inputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={(e) => handleFile(e.target.files[0])}
              />
            </div>

            {file && (
              <>
                <div className="grid md:grid-cols-2 gap-4 mt-6">
                  <TextInput
                    label="Project name (optional)"
                    value={projectName}
                    onChange={setProjectName}
                    placeholder="e.g. EGWA-2 Bypass"
                  />
                  <TextInput
                    label="Vendor name (optional)"
                    value={vendorName}
                    onChange={setVendorName}
                    placeholder="e.g. ABC Engineering Ltd"
                  />
                </div>
                <div className="mt-6">
                  <RunButton onClick={runAnalysis} loading={loading} label="Analyze tender" />
                </div>
              </>
            )}
            {error && <p className="text-rose-400 text-sm mt-4">{error}</p>}
          </Card>

          {/* What this does */}
          <Card className="p-6 border-l-4 border-l-amber">
            <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-3">How this works</h3>
            <ol className="space-y-2 text-sm text-slate-300">
              <li><span className="text-amber font-bold">1.</span> Your BOQ is parsed (header row auto-detected, columns auto-mapped).</li>
              <li><span className="text-amber font-bold">2.</span> Each line description is normalized — diameter, schedule, material grade, unit extracted.</li>
              <li><span className="text-amber font-bold">3.</span> Each normalized line is matched to the closest catalogue benchmark (369 items, USD 2024 normalised).</li>
              <li><span className="text-amber font-bold">4.</span> Vendor rates are compared to the catalogue Mid → GREEN (±15%), AMBER (±15–30%), RED (&gt;±30%), or UNMATCHED.</li>
              <li><span className="text-amber font-bold">5.</span> Executive summary, procurement summary, and a line-by-line variance table are returned.</li>
            </ol>
          </Card>
        </>
      )}

      {report && <Report report={report} onReset={() => { setReport(null); setFile(null); setError(null); }} />}
    </div>
  );
}

// ─── Report view ─────────────────────────────────────────────────────────
function Report({ report, onReset }) {
  const { header, executive_summary: es, procurement_summary: ps, line_items: items } = report;
  const [filter, setFilter] = useState('ALL'); // ALL, GREEN, AMBER, RED, UNMATCHED
  const [expanded, setExpanded] = useState({});

  const filtered = useMemo(() => {
    if (filter === 'ALL') return items;
    return items.filter(l => l.verdict === filter);
  }, [items, filter]);

  return (
    <div className="space-y-6">
      {/* Header strip */}
      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-widest text-amber mb-1">Analysis result</div>
            <h2 className="text-xl font-bold text-slate-100">
              {header.project_name || 'Untitled Project'}
              {header.vendor_name && <span className="text-slate-400"> · {header.vendor_name}</span>}
            </h2>
            <div className="text-xs text-slate-500 mt-1">
              Sheet: <span className="font-mono">{header.sheet}</span> · header row {header.header_row} · {header.total_lines} line items
            </div>
          </div>
          <button onClick={onReset} className="text-xs uppercase tracking-wider text-slate-400 hover:text-amber border border-slate-700 px-3 py-1.5 rounded">
            Upload another
          </button>
        </div>
      </Card>

      {/* Executive Summary */}
      <div>
        <SectionHeader num="01" label="Executive summary" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiTile
            Icon={DollarSign} colour="amber"
            value={fmt.usdFull(es.total_vendor_value_usd)}
            label="Total vendor value"
            sub="Sum of all line items in BOQ"
          />
          <KpiTile
            Icon={Layers} colour="teal"
            value={fmt.usdFull(es.total_benchmark_value_usd)}
            label="Total benchmark value"
            sub={`${(ps.benchmark_coverage_pct * 100).toFixed(1)}% catalogue coverage`}
          />
          <KpiTile
            Icon={es.total_savings_opportunity_usd >= 0 ? TrendingUp : TrendingDown}
            colour={es.total_savings_opportunity_usd > 0 ? 'rose' : 'emerald'}
            value={fmt.usdFull(Math.abs(es.total_savings_opportunity_usd))}
            label={es.total_savings_opportunity_usd >= 0 ? 'Savings opportunity' : 'Below-benchmark value'}
            sub={`${(es.savings_opportunity_pct * 100).toFixed(1)}% of vendor value`}
          />
          <KpiTile
            Icon={AlertCircle} colour="rose"
            value={ps.verdict_counts.RED}
            label="High-risk items"
            sub={`${ps.verdict_counts.AMBER} amber · ${ps.verdict_counts.GREEN} green`}
          />
        </div>
      </div>

      {/* Top overpriced + underpriced */}
      {(es.top_overpriced_items.length > 0 || es.top_savings_items.length > 0) && (
        <div className="grid md:grid-cols-2 gap-4">
          {es.top_overpriced_items.length > 0 && (
            <Card className="p-5">
              <h3 className="text-rose-300 font-bold uppercase text-xs tracking-wider mb-3 flex items-center gap-2">
                <TrendingUp className="w-4 h-4" />
                Top overpriced lines
              </h3>
              <div className="space-y-2">
                {es.top_overpriced_items.slice(0, 5).map((item, i) => (
                  <div key={i} className="flex items-start justify-between gap-3 text-sm">
                    <div className="flex-1 min-w-0">
                      <div className="text-slate-200 truncate" title={item.description}>
                        L{item.line_index}: {item.description}
                      </div>
                      <div className="text-[10px] text-slate-500">{item.catalogue_id}</div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="text-rose-300 font-bold num-tabular">+{(item.delta_pct*100).toFixed(0)}%</div>
                      <div className="text-[10px] text-slate-500">${item.overpriced_by_usd.toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {es.top_savings_items.length > 0 && (
            <Card className="p-5">
              <h3 className="text-emerald-300 font-bold uppercase text-xs tracking-wider mb-3 flex items-center gap-2">
                <TrendingDown className="w-4 h-4" />
                Lines below benchmark
              </h3>
              <div className="space-y-2">
                {es.top_savings_items.slice(0, 5).map((item, i) => (
                  <div key={i} className="flex items-start justify-between gap-3 text-sm">
                    <div className="flex-1 min-w-0">
                      <div className="text-slate-200 truncate" title={item.description}>
                        L{item.line_index}: {item.description}
                      </div>
                      <div className="text-[10px] text-slate-500">{item.catalogue_id}</div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="text-emerald-300 font-bold num-tabular">{(item.delta_pct*100).toFixed(0)}%</div>
                      <div className="text-[10px] text-slate-500">${item.underpriced_by_usd.toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Procurement Summary */}
      <div>
        <SectionHeader num="02" label="Procurement summary" />
        <Card className="p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-slate-700/30 rounded overflow-hidden">
            <Stat val={ps.items_total} lbl="Total items" />
            <Stat val={ps.items_matched} lbl="Matched" />
            <Stat val={ps.items_unmatched} lbl="Unmatched" />
            <Stat val={`${(ps.benchmark_coverage_pct*100).toFixed(1)}%`} lbl="Coverage" />
            <Stat val={ps.items_above_benchmark} lbl="Above benchmark" colour="rose" />
            <Stat val={ps.items_in_band} lbl="In band" colour="emerald" />
            <Stat val={ps.items_below_benchmark} lbl="Below benchmark" colour="amber" />
            <Stat val={ps.verdict_counts.RED} lbl="RED verdict" colour="rose" />
          </div>
        </Card>
      </div>

      {/* Line item table */}
      <div>
        <SectionHeader num="03" label="Detailed line item report" />
        <Card className="overflow-hidden">
          {/* Filter pills */}
          <div className="flex flex-wrap gap-2 p-4 border-b border-slate-700/50">
            {['ALL', 'GREEN', 'AMBER', 'RED', 'UNMATCHED'].map(v => {
              const count = v === 'ALL' ? items.length : (ps.verdict_counts[v] || 0);
              const active = filter === v;
              return (
                <button key={v} onClick={() => setFilter(v)}
                  className={`text-xs uppercase tracking-wider px-3 py-1.5 rounded border transition-colors ${
                    active
                      ? 'bg-amber/20 border-amber text-amber font-bold'
                      : 'border-slate-700 text-slate-400 hover:text-slate-200'
                  }`}>
                  {v}  <span className="ml-1 text-[10px] opacity-70">{count}</span>
                </button>
              );
            })}
          </div>

          <table className="w-full text-xs">
            <thead className="bg-bg-dark">
              <tr>
                <th className="px-3 py-2 text-left text-slate-400 uppercase tracking-wider w-8">#</th>
                <th className="px-3 py-2 text-left text-slate-400 uppercase tracking-wider">Description</th>
                <th className="px-3 py-2 text-right text-slate-400 uppercase tracking-wider">Qty</th>
                <th className="px-3 py-2 text-left text-slate-400 uppercase tracking-wider">Unit</th>
                <th className="px-3 py-2 text-right text-slate-400 uppercase tracking-wider">Vendor</th>
                <th className="px-3 py-2 text-right text-amber uppercase tracking-wider">Bench Mid</th>
                <th className="px-3 py-2 text-right text-slate-400 uppercase tracking-wider">Δ%</th>
                <th className="px-3 py-2 text-center text-slate-400 uppercase tracking-wider">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((l) => {
                const isOpen = expanded[l.line_index];
                return (
                  <FragmentRow key={l.line_index} line={l} isOpen={isOpen}
                    onToggle={() => setExpanded(p => ({ ...p, [l.line_index]: !p[l.line_index] }))} />
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-slate-500">No items match this filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>

      <SourceNote>
        Variance computed against the catalogue Mid (USD 2024 real). Match score &lt; 0.50 → UNMATCHED (line excluded from variance totals).
        Coverage gaps (e.g. raw pipe materials, fittings, valves) reflect that some BOQ categories aren't yet in the catalogue — these need to be added via Phase 3 data acquisition.
      </SourceNote>
    </div>
  );
}

function FragmentRow({ line, isOpen, onToggle }) {
  const v = line.variance;
  const hasMatches = line.matches && line.matches.length > 0;
  return (
    <>
      <tr
        className={`border-t border-slate-700/30 ${hasMatches ? 'cursor-pointer hover:bg-bg-panel/50' : ''}`}
        onClick={hasMatches ? onToggle : undefined}>
        <td className="px-3 py-2 text-slate-500 font-mono">
          {hasMatches ? (isOpen ? <ChevronDown className="w-3.5 h-3.5 inline" /> : <ChevronRight className="w-3.5 h-3.5 inline" />) : null}
          {' '}{line.line_index}
        </td>
        <td className="px-3 py-2 text-slate-200" title={line.description}>
          <div className="max-w-md truncate">{line.description}</div>
          {line.normalized?.category_hint && (
            <div className="text-[10px] text-slate-500 mt-0.5">
              {line.normalized.category_hint} → {line.normalized.sub_category_hint || '—'}
              {line.normalized.spec?.dia && ` · ${line.normalized.spec.dia}″`}
              {line.normalized.spec?.sched && ` · ${line.normalized.spec.sched}`}
            </div>
          )}
        </td>
        <td className="px-3 py-2 text-right text-slate-300 num-tabular">{line.qty?.toLocaleString() || '—'}</td>
        <td className="px-3 py-2 text-slate-400 text-[11px]">{line.unit || '—'}</td>
        <td className="px-3 py-2 text-right text-slate-200 num-tabular font-semibold">
          {line.vendor_rate != null ? `$${line.vendor_rate.toFixed(2)}` : '—'}
        </td>
        <td className="px-3 py-2 text-right text-amber num-tabular">
          {v?.benchmark_mid != null ? `$${v.benchmark_mid.toFixed(2)}` : '—'}
        </td>
        <td className={`px-3 py-2 text-right num-tabular font-bold ${
          v?.delta_pct == null ? 'text-slate-500' :
          v.delta_pct > 0.15 ? 'text-rose-300' :
          v.delta_pct < -0.15 ? 'text-emerald-300' : 'text-slate-300'
        }`}>
          {v?.delta_pct != null ? `${(v.delta_pct * 100).toFixed(0)}%` : '—'}
        </td>
        <td className="px-3 py-2 text-center">
          <VerdictPill verdict={line.verdict} />
        </td>
      </tr>
      {isOpen && hasMatches && (
        <tr className="bg-bg-dark/40">
          <td colSpan={8} className="px-6 py-3">
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
                Top {Math.min(3, line.matches.length)} catalogue matches
              </div>
              {line.matches.slice(0, 3).map((m, i) => (
                <div key={i} className="flex justify-between gap-3 text-[11px] py-1 border-b border-slate-700/30 last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="text-slate-200">
                      [{m.catalogue_id}] {m.item}
                    </div>
                    <div className="text-slate-500 mt-0.5">{m.reasons.join(' · ')}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-slate-300 num-tabular">Score {m.score.toFixed(2)}</div>
                    <div className={`text-[10px] ${m.verdict === 'HIGH' ? 'text-emerald-300' : m.verdict === 'MEDIUM' ? 'text-amber' : 'text-rose-300'}`}>
                      {m.verdict} match
                    </div>
                  </div>
                </div>
              ))}
              {line.normalized && (
                <div className="text-[10px] text-slate-500 mt-2">
                  Normalized: {Object.entries(line.normalized.tokens_extracted || {}).map(([k,v]) => `${k}=${v}`).join(' · ')}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function KpiTile({ Icon, value, label, sub, colour = 'amber' }) {
  const colours = {
    amber:   'text-amber',
    teal:    'text-teal',
    emerald: 'text-emerald-300',
    rose:    'text-rose-300',
  };
  return (
    <Card className="p-5">
      <Icon className={`w-5 h-5 ${colours[colour]} mb-2`} />
      <div className={`text-2xl md:text-3xl font-bold num-tabular ${colours[colour]} leading-none mb-1`}>{value}</div>
      <div className="text-sm font-semibold text-slate-200 mb-0.5">{label}</div>
      <div className="text-[11px] text-slate-500">{sub}</div>
    </Card>
  );
}

function Stat({ val, lbl, colour }) {
  const colourMap = { rose: 'text-rose-300', emerald: 'text-emerald-300', amber: 'text-amber' };
  return (
    <div className="bg-bg-panel p-4 text-center">
      <div className={`text-2xl font-bold num-tabular ${colourMap[colour] || 'text-slate-100'}`}>{val}</div>
      <div className="text-[10px] uppercase tracking-wider text-slate-400 mt-1">{lbl}</div>
    </div>
  );
}
