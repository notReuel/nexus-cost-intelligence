import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { UploadCloud, Loader2, Trophy, AlertTriangle, X, Sparkles, Users, BarChart3, ArrowRight } from 'lucide-react';
import { api } from '../lib/api.js';
import { Panel, VerdictPill, CoverageBar, money, moneyK } from '../components/Enterprise.jsx';

export default function BidIntake() {
  const [files, setFiles] = useState([]);      // {name, file}
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [drill, setDrill] = useState(null);
  const [budget, setBudget] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => { try { const s = localStorage.getItem('ncmp:budget'); if (s) setBudget(JSON.parse(s)); } catch {} }, []);

  const addFiles = (fl) => setFiles(f => [...f, ...Array.from(fl).map(file => ({ name: file.name.replace(/\.[^.]+$/, ''), file }))].slice(0, 10));
  const rename = (i, name) => setFiles(f => f.map((x, j) => j === i ? { ...x, name } : x));
  const remove = (i) => setFiles(f => f.filter((_, j) => j !== i));

  const genDemo = (n) => {
    if (!budget) { alert('Model a budget first to generate demo bids.'); return; }
    const lines = budget.result.lines;
    const vendors = [];
    const names = ['Geoplex', 'Hydroserve', 'Weafri', 'Netcore', 'IHE Emval', 'Oildata', 'Sowsco', 'Broadway', 'Kenmore', 'Deepwater'];
    for (let v = 0; v < n; v++) {
      // Most vendors cluster near benchmark (recommendation can fire); a couple stray for spread.
      const stray = v % 4 === 3;
      const bias = stray ? (0.68 + Math.random() * 0.15) + (Math.random() < 0.5 ? 0 : 0.55)
                         : 0.9 + Math.random() * 0.22;   // 0.90 – 1.12
      const rows = [['Description', 'Unit', 'Qty', 'Rate', 'Amount']];
      lines.forEach(l => {
        const dev = bias * (0.93 + Math.random() * 0.14);
        const rate = +(l.rate_mid * dev).toFixed(2);
        rows.push([l.description, l.unit, l.qty, rate, +(rate * l.qty).toFixed(2)]);
      });
      const csv = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n');
      vendors.push({ name: names[v] || `Vendor ${v + 1}`, file: new File([csv], `${names[v] || 'vendor'}.csv`, { type: 'text/csv' }) });
    }
    setFiles(vendors);
  };

  const compare = async () => {
    if (files.length < 2) { setErr('Upload at least 2 vendor BOQs.'); return; }
    setLoading(true); setErr(null); setDrill(null);
    try {
      const renamed = files.map(f => new File([f.file], `${f.name}.csv`, { type: f.file.type || 'text/csv' }));
      setResult(await api.bidComparison(renamed, budget?.scope?.project_name || 'Bid comparison'));
    } catch (e) { setErr(String(e.message || e)); }
    finally { setLoading(false); }
  };

  const modelledMid = budget?.result?.total?.mid;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Cost Benchmarking &amp; Ranking</h1>
        <p className="text-[13px] text-slate-500">Upload up to 10 vendor BOQs and rank them against your generated cost benchmark, line by line.</p>
      </div>

      {/* generated cost benchmark */}
      {budget ? (
        <div className="rounded-sm border border-accent/30 bg-accent-light/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-accent-dim">
              <BarChart3 className="w-4 h-4" />Generated cost benchmark
            </div>
            <span className="text-[11px] text-slate-500 num-tabular">
              {budget.scope.dia}" {budget.scope.sched} {budget.scope.terrain} · {Number(budget.scope.length_m).toLocaleString()}m · {budget.scope.operator}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            <BenchStat label="Benchmark total (Mid)" value={money(budget.result.total.mid)} accent />
            <BenchStat label="Range (Low–High)" value={`${moneyK(budget.result.total.low)} – ${moneyK(budget.result.total.high)}`} />
            <BenchStat label="Per metre" value={`${money(budget.result.per_m.mid)}/m`} />
            <BenchStat label="Evidence coverage" value={`${budget.result.coverage_pct}%`} />
          </div>
        </div>
      ) : (
        <div className="rounded-sm border border-slate-200 bg-slate-50 p-4 text-[13px] text-slate-600 flex items-center justify-between gap-3 flex-wrap">
          <span>No benchmark yet — model a project first so bids can be ranked against a real total.</span>
          <Link to="/model" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-accent text-white font-semibold text-[12px] hover:bg-accent-glow">Open Project Model<ArrowRight className="w-3.5 h-3.5" /></Link>
        </div>
      )}

      {/* intake */}
      <Panel title="Vendor intake" subtitle={`${files.length}/10`}>
        <div
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); addFiles(e.dataTransfer.files); }}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-slate-300 rounded-sm py-8 text-center cursor-pointer hover:border-accent/50 transition-colors">
          <UploadCloud className="w-8 h-8 mx-auto text-slate-500 mb-2" />
          <p className="text-[13px] text-slate-700">Drop vendor BOQs here or click to browse</p>
          <p className="text-[11px] text-slate-500 mt-0.5">.xlsx or .csv · up to 10 vendors</p>
          <input ref={inputRef} type="file" multiple accept=".xlsx,.csv" className="hidden" onChange={e => addFiles(e.target.files)} />
        </div>
        <div className="flex items-center gap-2 mt-3 flex-wrap">
          <button onClick={() => genDemo(6)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-accent/40 text-[12px] text-accent hover:bg-accent/10"><Sparkles className="w-3.5 h-3.5" />Generate 6 demo bids</button>
          <button onClick={() => genDemo(10)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-slate-300 text-[12px] text-slate-700 hover:border-accent/50"><Users className="w-3.5 h-3.5" />10 vendors</button>
        </div>
        {files.length > 0 && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-3">
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-2 bg-[#F8FAFC] border border-slate-200 rounded-sm px-2.5 py-1.5">
                <input value={f.name} onChange={e => rename(i, e.target.value)} className="flex-1 bg-transparent text-[12px] text-slate-800 focus:outline-none min-w-0" />
                <button onClick={() => remove(i)} className="text-slate-500 hover:text-red-400"><X className="w-3.5 h-3.5" /></button>
              </div>
            ))}
          </div>
        )}
        {err && <div className="flex items-center gap-2 text-[12px] text-red-700 bg-red-50 rounded-sm p-2 mt-3"><AlertTriangle className="w-4 h-4" />{err}</div>}
        <button onClick={compare} disabled={loading || files.length < 2}
          className="w-full mt-3 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-sm bg-accent text-[#F8FAFC] font-semibold text-sm hover:bg-accent-glow disabled:opacity-40 disabled:cursor-not-allowed">
          {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Comparing…</> : `Compare ${files.length} vendors`}
        </button>
      </Panel>

      {/* ranking */}
      {result && (
        <>
          <Panel title="Vendor ranking" subtitle={result.recommendation?.rationale}>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
              {result.ranked.map((v, i) => {
                const rec = v.vendor_label === result.recommendation?.recommended_vendor;
                const dev = modelledMid ? (v.total_vendor_value - modelledMid) / modelledMid : null;
                return (
                  <button key={v.vendor_label} onClick={() => setDrill(v.vendor_label)}
                    className={`text-left rounded-sm border p-3 transition-all ${rec ? 'border-accent bg-accent/5 ring-1 ring-accent/30' : 'border-slate-200 bg-[#FFFFFF] hover:border-slate-300'} ${drill === v.vendor_label ? 'ring-2 ring-accent/50' : ''}`}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[11px] font-mono text-slate-500">#{i + 1}</span>
                      {rec && <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-accent"><Trophy className="w-3 h-3" />Recommended</span>}
                    </div>
                    <div className="text-[14px] font-semibold text-slate-900 truncate">{v.vendor_label}</div>
                    <div className="text-xl font-bold num-tabular text-slate-900 mt-1">{money(v.total_vendor_value)}</div>
                    {dev != null && <div className={`text-[11px] num-tabular mt-0.5 ${Math.abs(dev) <= 0.15 ? 'text-emerald-600' : Math.abs(dev) <= 0.3 ? 'text-amber-600' : 'text-red-700'}`}>{dev >= 0 ? '+' : ''}{(dev * 100).toFixed(1)}% vs modelled</div>}
                    <div className="mt-2"><CoverageBar pct={Math.round(v.coverage_pct)} /></div>
                    <div className="flex gap-1.5 mt-2 text-[10px]">
                      {v.verdict_counts?.red > 0 && <VerdictPill colour="red">{v.verdict_counts.red} red</VerdictPill>}
                      {v.verdict_counts?.amber > 0 && <VerdictPill colour="amber">{v.verdict_counts.amber} amber</VerdictPill>}
                      {v.verdict_counts?.green > 0 && <VerdictPill colour="green">{v.verdict_counts.green} green</VerdictPill>}
                    </div>
                  </button>
                );
              })}
            </div>
          </Panel>

          {result.line_matrix?.length > 0 && (
            <Panel title="Line-by-line matrix" subtitle="Sticky first column · scroll horizontally across vendors">
              <div className="overflow-x-auto -mx-4">
                <table className="text-[11px] min-w-full">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-wider border-b border-slate-200">
                      <th className="sticky left-0 bg-[#FFFFFF] py-2 px-3 text-left font-semibold min-w-[220px]">Line item</th>
                      <th className="py-2 px-3 text-right font-semibold">Bench Mid</th>
                      {result.vendor_summary.map(v => (
                        <th key={v.vendor_label} className={`py-2 px-3 text-right font-semibold whitespace-nowrap ${drill === v.vendor_label ? 'text-accent' : ''}`}>{v.vendor_label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.line_matrix.map((row, ri) => (
                      <tr key={ri} className="border-b border-slate-200 hover:bg-slate-100">
                        <td className="sticky left-0 bg-[#FFFFFF] py-1.5 px-3 text-slate-800 min-w-[220px]">{row.description}<span className="text-slate-500 ml-1">({row.unit})</span></td>
                        <td className="py-1.5 px-3 text-right num-tabular text-slate-600">{money(row.bench_mid)}</td>
                        {result.vendor_summary.map(v => {
                          const cell = row.vendors?.[v.vendor_label];
                          const dp = cell?.delta_pct;
                          const col = dp == null ? 'text-slate-400' : Math.abs(dp) <= 0.15 ? 'text-emerald-600' : Math.abs(dp) <= 0.3 ? 'text-amber-600' : 'text-red-700';
                          return <td key={v.vendor_label} className={`py-1.5 px-3 text-right num-tabular ${col} ${drill === v.vendor_label ? 'bg-accent/5' : ''}`}>{cell ? money(cell.amount) : '—'}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          {result.unmatched_lines?.length > 0 && (
            <Panel title="Unmatched vendor lines" subtitle="Priced by a vendor but no benchmark catalogue match — shown so they're never silently dropped">
              <div className="overflow-x-auto -mx-4">
                <table className="text-[11px] min-w-full">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-wider border-b border-slate-200">
                      <th className="py-2 px-3 text-left font-semibold">Vendor</th>
                      <th className="py-2 px-3 text-left font-semibold">Description</th>
                      <th className="py-2 px-3 text-left font-semibold">Unit</th>
                      <th className="py-2 px-3 text-right font-semibold">Rate</th>
                      <th className="py-2 px-3 text-right font-semibold">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.unmatched_lines.map((u, i) => (
                      <tr key={i} className="border-b border-slate-200 hover:bg-slate-100">
                        <td className="py-1.5 px-3 text-slate-700 font-semibold whitespace-nowrap">{u.vendor_label}</td>
                        <td className="py-1.5 px-3 text-slate-800">{u.description}</td>
                        <td className="py-1.5 px-3 text-slate-600">{u.unit}</td>
                        <td className="py-1.5 px-3 text-right num-tabular text-slate-600">{u.rate != null ? money(u.rate) : '—'}</td>
                        <td className="py-1.5 px-3 text-right num-tabular text-slate-800">{u.amount != null ? money(u.amount) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

function BenchStat({ label, value, accent }) {
  return (
    <div className={`rounded-sm border p-2.5 ${accent ? 'border-accent/40 bg-white' : 'border-slate-200 bg-white'}`}>
      <div className="text-[9px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`text-[15px] font-bold num-tabular mt-0.5 ${accent ? 'text-accent-dim' : 'text-slate-900'}`}>{value}</div>
    </div>
  );
}
