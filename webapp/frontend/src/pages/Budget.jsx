import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronRight, Download, ArrowRight, Inbox } from 'lucide-react';
import { Panel, ConfidencePill, SourcePopover, CoverageBar, money } from '../components/Enterprise.jsx';

export default function Budget() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [collapsed, setCollapsed] = useState({});

  useEffect(() => {
    try { const s = localStorage.getItem('ncmp:budget'); if (s) setData(JSON.parse(s)); } catch {}
  }, []);

  if (!data) return (
    <Empty onGo={() => nav('/model')} />
  );

  const { scope, result } = data;
  const sections = {};
  result.lines.forEach(l => { (sections[l.section] ||= []).push(l); });
  const toggle = (s) => setCollapsed(c => ({ ...c, [s]: !c[s] }));

  const exportCsv = () => {
    const rows = [['Item', 'Section', 'Description', 'Spec', 'Qty', 'Unit', 'Rate Low', 'Rate Mid', 'Rate High', 'Line Low', 'Line Mid', 'Line High', 'Confidence', 'Operators', 'Obs']];
    result.lines.forEach(l => rows.push([l.item_no, l.section, l.description, l.spec, l.qty, l.unit, l.rate_low, l.rate_mid, l.rate_high, l.line_low, l.line_mid, l.line_high, l.confidence, (l.source.operator_used || []).join('; '), l.source.n_obs]));
    const csv = rows.map(r => r.map(c => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a'); a.href = url; a.download = `${(scope.project_name || 'boq').replace(/\s+/g, '_')}_BOQ.csv`; a.click();
    URL.revokeObjectURL(url);
  };
  const toBids = () => nav('/bids');

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-slate-900">{scope.project_name}</h1>
          <p className="text-[13px] text-slate-500 num-tabular">
            {scope.operator} · {scope.dia}" {scope.sched} {scope.terrain} · {scope.length_m.toLocaleString()}m · {scope.duration_days}d
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportCsv} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-slate-300 text-[13px] text-slate-700 hover:border-accent/60 hover:text-accent"><Download className="w-3.5 h-3.5" />Export Excel</button>
          <button onClick={toBids} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-accent text-[#F8FAFC] font-semibold text-[13px] hover:bg-accent-glow">Move to bid intake<ArrowRight className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      {/* summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SumCard label="Direct cost" v={result.direct.mid} sub={`${money(result.direct.low)} – ${money(result.direct.high)}`} />
        <SumCard label={`Contingency ${(scope.contingency_pct * 100).toFixed(0)}%`} v={result.contingency.mid} />
        <SumCard label={`VAT ${(scope.vat_pct * 100).toFixed(1)}%`} v={result.vat.mid} />
        <SumCard label="Grand total" v={result.total.mid} accent sub={`${money(result.per_m.mid)}/m`} />
      </div>

      <div className="flex items-center gap-4 text-[12px] text-slate-600 px-1">
        <span>Evidence coverage</span>
        <div className="w-40"><CoverageBar pct={result.coverage_pct} /></div>
        <span>{result.backed_lines} of {result.total_lines} lines backed by real observations</span>
      </div>

      {/* BOQ table */}
      <Panel title="Bill of quantities" subtitle="Per-line source transparency — click the database icon on any row">
        <div className="overflow-x-auto -mx-4">
          <table className="w-full text-[12px] min-w-[860px]">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 text-[10px] uppercase tracking-wider">
                <th className="py-2 px-2 font-semibold">#</th>
                <th className="py-2 px-2 font-semibold">Description</th>
                <th className="py-2 px-2 font-semibold text-right">Qty</th>
                <th className="py-2 px-2 font-semibold">Unit</th>
                <th className="py-2 px-2 font-semibold text-right">Low</th>
                <th className="py-2 px-2 font-semibold text-right">Mid</th>
                <th className="py-2 px-2 font-semibold text-right">High</th>
                <th className="py-2 px-2 font-semibold text-right">Line total</th>
                <th className="py-2 px-2 font-semibold">Confidence</th>
                <th className="py-2 px-2 font-semibold text-right">Src</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(sections).map(([sec, lines]) => {
                const secTotal = lines.reduce((a, l) => a + l.line_mid, 0);
                const isC = collapsed[sec];
                return (
                  <tbody key={sec}>
                    <tr className="bg-slate-100 border-b border-slate-200 cursor-pointer hover:bg-slate-100" onClick={() => toggle(sec)}>
                      <td className="py-1.5 px-2" colSpan={2}>
                        <span className="inline-flex items-center gap-1.5 font-semibold text-slate-800 text-[12px]">
                          {isC ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}{sec}
                          <span className="text-slate-500 font-normal">({lines.length})</span>
                        </span>
                      </td>
                      <td colSpan={5}></td>
                      <td className="py-1.5 px-2 text-right font-semibold num-tabular text-accent">{money(secTotal)}</td>
                      <td colSpan={2}></td>
                    </tr>
                    {!isC && lines.map(l => (
                      <tr key={l.item_no} className="border-b border-slate-200 hover:bg-slate-100">
                        <td className="py-1.5 px-2 num-tabular text-slate-500">{l.item_no}</td>
                        <td className="py-1.5 px-2">
                          <div className="text-slate-800">{l.description}</div>
                          <div className="text-[10px] text-slate-500">{l.spec}{l.source.operator_used?.length ? ` · ${l.source.operator_used.join(', ')}` : ''}</div>
                        </td>
                        <td className="py-1.5 px-2 text-right num-tabular text-slate-700">{l.qty.toLocaleString()}</td>
                        <td className="py-1.5 px-2 text-slate-600">{l.unit}</td>
                        <td className="py-1.5 px-2 text-right num-tabular text-slate-600">{money(l.rate_low, l.rate_mid < 100 ? 2 : 0)}</td>
                        <td className="py-1.5 px-2 text-right num-tabular text-slate-800">{money(l.rate_mid, l.rate_mid < 100 ? 2 : 0)}</td>
                        <td className="py-1.5 px-2 text-right num-tabular text-slate-600">{money(l.rate_high, l.rate_mid < 100 ? 2 : 0)}</td>
                        <td className="py-1.5 px-2 text-right num-tabular font-semibold text-slate-900">{money(l.line_mid)}</td>
                        <td className="py-1.5 px-2"><ConfidencePill level={l.confidence} count={l.source.n_obs} /></td>
                        <td className="py-1.5 px-2 text-right"><SourcePopover source={l.source} /></td>
                      </tr>
                    ))}
                  </tbody>
                );
              })}
              <tr className="border-t-2 border-accent/40 bg-accent/5">
                <td colSpan={7} className="py-2 px-2 text-right font-bold text-slate-900 text-[13px]">Direct cost subtotal</td>
                <td className="py-2 px-2 text-right font-bold num-tabular text-accent text-[13px]">{money(result.direct.mid)}</td>
                <td colSpan={2}></td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function SumCard({ label, v, sub, accent }) {
  return (
    <div className={`rounded-sm border p-3 ${accent ? 'border-accent/40 bg-accent/5' : 'border-slate-200 bg-[#FFFFFF]'}`}>
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`text-lg font-bold num-tabular mt-1 ${accent ? 'text-accent' : 'text-slate-900'}`}>{money(v)}</div>
      {sub && <div className="text-[10px] text-slate-500 num-tabular mt-0.5">{sub}</div>}
    </div>
  );
}

function Empty({ onGo }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-24">
      <Inbox className="w-10 h-10 text-slate-400 mb-3" />
      <h2 className="text-lg font-semibold text-slate-800">No budget yet</h2>
      <p className="text-[13px] text-slate-500 max-w-sm mt-1">Build a scope in the Project Modeller, then generate a line-item budget to see it here.</p>
      <button onClick={onGo} className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-sm bg-accent text-[#F8FAFC] font-semibold text-sm">Open Project Modeller<ArrowRight className="w-4 h-4" /></button>
    </div>
  );
}
