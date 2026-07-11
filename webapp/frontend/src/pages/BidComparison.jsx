import { useState, useRef, useMemo } from 'react';
import { Upload, Trash2, Award, AlertTriangle, CheckCircle2, XCircle, TrendingDown, TrendingUp, ScrollText, Crown } from 'lucide-react';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, TextInput, RunButton, SourceNote } from '../components/UI.jsx';

export default function BidComparison() {
  const [files, setFiles] = useState([]);
  const [projectName, setProjectName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);
  const inputRef = useRef(null);

  const addFiles = (incoming) => {
    setError(null);
    const valid = [...incoming].filter(f => /\.(xlsx|xls|csv)$/i.test(f.name) && f.size <= 20 * 1024 * 1024);
    if (valid.length !== incoming.length) {
      setError('Some files were rejected (must be .xlsx/.xls/.csv, max 20 MB each)');
    }
    setFiles(prev => [...prev, ...valid].slice(0, 10));
  };
  const removeFile = (idx) => setFiles(prev => prev.filter((_, i) => i !== idx));

  const runComparison = async () => {
    if (files.length < 2) { setError('Need at least 2 vendor BOQs to compare'); return; }
    setLoading(true); setError(null);
    try {
      const r = await api.bidComparison(files, projectName);
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
        Icon={Award}
        eyebrow="Benchmark service · Bid comparison"
        title="Multi-vendor Bid Comparison"
        subtitle="Upload 2+ vendor BOQs for the same scope. The platform ranks them, flags unsustainable lowball bids, and recommends the lowest priced bid within an acceptable deviation band from the benchmark."
      />

      {!report && (
        <>
          <Card className="p-8">
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files); }}
              onClick={() => inputRef.current?.click()}
              className="border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors border-slate-700 hover:border-amber/50">
              <Upload className="w-10 h-10 mx-auto mb-3 text-slate-500" />
              <div className="text-base font-bold text-slate-100 mb-1">
                Drop 2–10 vendor BOQs, or click to browse
              </div>
              <div className="text-xs text-slate-500">.xlsx, .xls, .csv — max 20 MB each</div>
              <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" multiple className="hidden"
                     onChange={(e) => addFiles(e.target.files)} />
            </div>

            {files.length > 0 && (
              <div className="mt-6 space-y-2">
                <div className="text-xs uppercase tracking-wider text-slate-400 mb-1">
                  Vendor BOQs ({files.length})
                </div>
                {files.map((f, i) => (
                  <div key={i} className="flex items-center justify-between bg-bg-dark border border-slate-700 rounded px-3 py-2">
                    <div className="flex items-center gap-3 min-w-0">
                      <ScrollText className="w-4 h-4 text-amber flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="text-sm text-slate-200 truncate">{f.name}</div>
                        <div className="text-[10px] text-slate-500">{(f.size / 1024).toFixed(1)} KB</div>
                      </div>
                    </div>
                    <button onClick={() => removeFile(i)} className="text-slate-500 hover:text-rose-400 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {files.length > 0 && (
              <div className="mt-6 grid md:grid-cols-2 gap-4">
                <TextInput
                  label="Project name (optional)"
                  value={projectName}
                  onChange={setProjectName}
                  placeholder="e.g. CT 2025 Tender"
                />
              </div>
            )}

            {files.length >= 2 && (
              <div className="mt-6">
                <RunButton onClick={runComparison} loading={loading} label={`Compare ${files.length} bids`} />
              </div>
            )}

            {error && <p className="text-rose-400 text-sm mt-4">{error}</p>}
          </Card>

          <Card className="p-6 border-l-4 border-l-amber">
            <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-3">Recommendation logic</h3>
            <ul className="space-y-2 text-sm text-slate-300">
              <li>• Bids are ranked by total vendor value (cheapest first).</li>
              <li>• A bid is <span className="text-emerald-300 font-bold">acceptable</span> when: mean Δ from benchmark ≤ 30%, RED-verdict lines ≤ 40%, and not deeply underpriced (mean Δ ≥ −35%).</li>
              <li>• The recommendation is the <span className="text-amber font-bold">lowest priced bid that is also acceptable</span> — not always the absolute lowest.</li>
              <li>• Deep lowball bids (mean Δ &lt; −35%) are flagged as <span className="text-rose-300 font-bold">unsustainable risk</span>.</li>
            </ul>
          </Card>
        </>
      )}

      {report && <ComparisonReport report={report} onReset={() => { setReport(null); setFiles([]); setError(null); }} />}
    </div>
  );
}

function ComparisonReport({ report, onReset }) {
  const { project_name, vendor_count, ranked, recommendation, line_matrix } = report;
  const [filter, setFilter] = useState('ALL');

  const filteredLines = useMemo(() => {
    if (filter === 'ALL') return line_matrix;
    return line_matrix.filter(row =>
      Object.values(row.vendors).some(v => v && v.verdict === filter)
    );
  }, [line_matrix, filter]);

  const vendorLabels = ranked.map(r => r.vendor_label);

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-widest text-amber mb-1">Bid comparison result</div>
            <h2 className="text-xl font-bold text-slate-100">{project_name}</h2>
            <div className="text-xs text-slate-500 mt-1">{vendor_count} vendors compared</div>
          </div>
          <button onClick={onReset} className="text-xs uppercase tracking-wider text-slate-400 hover:text-amber border border-slate-700 px-3 py-1.5 rounded">
            New comparison
          </button>
        </div>
      </Card>

      {/* Recommendation */}
      <Card accent className="p-6 border-l-4 border-l-amber">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-lg bg-amber/15 border border-amber/40 flex items-center justify-center flex-shrink-0">
            <Crown className="w-6 h-6 text-amber" />
          </div>
          <div className="flex-1">
            <div className="text-xs uppercase tracking-wider text-amber font-bold mb-1">Recommendation</div>
            {recommendation.recommended_vendor ? (
              <>
                <h3 className="text-2xl font-bold text-slate-100 mb-2">
                  {recommendation.recommended_vendor}
                  <span className="text-amber ml-3 num-tabular">{fmt.usdFull(recommendation.recommended_value)}</span>
                </h3>
                <p className="text-sm text-slate-300 leading-relaxed">{recommendation.rationale}</p>
              </>
            ) : (
              <>
                <h3 className="text-xl font-bold text-rose-300 mb-2">No vendor passes acceptance criteria</h3>
                <p className="text-sm text-slate-300 leading-relaxed">{recommendation.rationale}</p>
              </>
            )}
          </div>
        </div>
      </Card>

      {/* Vendor ranking */}
      <div>
        <SectionHeader num="01" label="Vendor ranking" />
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-bg-dark">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Rank</th>
                <th className="text-left px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Vendor</th>
                <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-amber font-semibold">Total bid</th>
                <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Mean Δ%</th>
                <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">RED lines</th>
                <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Coverage</th>
                <th className="text-center px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Flag</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map(v => (
                <tr key={v.vendor_label}
                    className={`border-t border-slate-700/30 ${v.recommended ? 'bg-amber/10' : ''}`}>
                  <td className="px-4 py-2.5 text-slate-300 font-mono">
                    {v.recommended && <Crown className="w-3.5 h-3.5 text-amber inline -mt-1 mr-1" />}
                    #{v.rank}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="text-slate-100 font-medium">{v.vendor_label}</div>
                    <div className="text-[10px] text-slate-500 truncate max-w-[260px]">{v.filename}</div>
                  </td>
                  <td className={`px-4 py-2.5 text-right num-tabular font-semibold ${v.lowest_overall ? 'text-emerald-300' : 'text-slate-200'}`}>
                    {fmt.usdFull(v.total_vendor_value)}
                  </td>
                  <td className={`px-4 py-2.5 text-right num-tabular ${
                    Math.abs(v.mean_delta_pct) > 0.30 ? 'text-rose-300' :
                    Math.abs(v.mean_delta_pct) > 0.15 ? 'text-amber' : 'text-emerald-300'
                  }`}>
                    {(v.mean_delta_pct * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-300 num-tabular">
                    {(v.red_line_pct * 100).toFixed(0)}%
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-300 num-tabular">
                    {(v.coverage_pct * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    {v.recommended && <Pill colour="amber" label="RECOMMENDED" />}
                    {!v.recommended && v.acceptable && <Pill colour="emerald" label="ACCEPTABLE" />}
                    {!v.acceptable && v.unsustainable_risk && <Pill colour="rose" label="LOWBALL RISK" />}
                    {!v.acceptable && !v.unsustainable_risk && <Pill colour="slate" label="OUT OF BAND" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Side-by-side line matrix */}
      <div>
        <SectionHeader num="02" label="Line-by-line comparison" />
        <Card className="overflow-hidden">
          <div className="flex flex-wrap gap-2 p-4 border-b border-slate-700/50">
            {['ALL', 'GREEN', 'AMBER', 'RED', 'UNMATCHED'].map(v => (
              <button key={v} onClick={() => setFilter(v)}
                className={`text-xs uppercase tracking-wider px-3 py-1.5 rounded border transition-colors ${
                  filter === v
                    ? 'bg-amber/20 border-amber text-amber font-bold'
                    : 'border-slate-700 text-slate-400 hover:text-slate-200'
                }`}>
                {v}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-bg-dark">
                <tr>
                  <th className="px-3 py-2 text-left text-slate-400 uppercase tracking-wider w-8">#</th>
                  <th className="px-3 py-2 text-left text-slate-400 uppercase tracking-wider min-w-[240px]">Description</th>
                  <th className="px-3 py-2 text-left text-slate-400 uppercase tracking-wider">Unit</th>
                  {vendorLabels.map(label => (
                    <th key={label} className="px-3 py-2 text-right text-slate-400 uppercase tracking-wider min-w-[110px]" title={label}>
                      <div className="truncate max-w-[120px]">{label}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredLines.map(row => (
                  <tr key={row.line_index} className="border-t border-slate-700/30 hover:bg-bg-panel/30">
                    <td className="px-3 py-2 text-slate-500 font-mono">{row.line_index}</td>
                    <td className="px-3 py-2 text-slate-200">
                      <div className="max-w-md truncate" title={row.description}>{row.description}</div>
                    </td>
                    <td className="px-3 py-2 text-slate-400 text-[11px]">{row.unit || '—'}</td>
                    {vendorLabels.map(label => {
                      const v = row.vendors[label];
                      if (!v || v.rate == null) return <td key={label} className="px-3 py-2 text-right text-slate-600">—</td>;
                      const isLowest = row.lowest_vendor === label;
                      return (
                        <td key={label} className={`px-3 py-2 text-right ${isLowest ? 'bg-emerald-500/10' : ''}`}>
                          <div className={`num-tabular font-semibold ${isLowest ? 'text-emerald-300' : 'text-slate-200'}`}>
                            ${v.rate.toFixed(2)}
                          </div>
                          {v.delta_pct != null && (
                            <div className={`text-[10px] num-tabular ${
                              Math.abs(v.delta_pct) > 0.30 ? 'text-rose-300' :
                              Math.abs(v.delta_pct) > 0.15 ? 'text-amber' : 'text-emerald-300'
                            }`}>
                              {v.delta_pct > 0 ? '+' : ''}{(v.delta_pct * 100).toFixed(0)}%
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {filteredLines.length === 0 && (
                  <tr>
                    <td colSpan={3 + vendorLabels.length} className="text-center py-8 text-slate-500">
                      No lines match this verdict filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <SourceNote>
        Lowest vendor rate per line highlighted in green. Δ% is calculated against the catalogue benchmark Mid (USD 2024 real).
        Lines where no vendor matched the catalogue show as dashes — these are excluded from the recommendation math.
      </SourceNote>
    </div>
  );
}

function Pill({ colour, label }) {
  const map = {
    amber:   'bg-amber/15       text-amber       border-amber/40',
    emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/40',
    rose:    'bg-rose-500/15    text-rose-300    border-rose-400/40',
    slate:   'bg-slate-700/30   text-slate-400   border-slate-600/40',
  };
  return (
    <span className={`inline-block px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded ${map[colour]}`}>
      {label}
    </span>
  );
}
