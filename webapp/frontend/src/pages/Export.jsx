import { useEffect, useState } from 'react';
import { FileDown, Printer, AlertCircle } from 'lucide-react';
import { fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card } from '../components/UI.jsx';

export default function Export() {
  const [pipelineR, setPipelineR] = useState(null);
  const [wellR, setWellR] = useState(null);
  const [ctR, setCtR] = useState(null);

  useEffect(() => {
    setPipelineR(safeParse('ndcip:pipeline_result'));
    setWellR(safeParse('ndcip:well_result'));
    setCtR(safeParse('ndcip:ct_result'));
  }, []);

  const project = pipelineR?.inputs_echo?.globals?.project_name ||
                  wellR?.inputs_echo?.globals?.project_name ||
                  ctR?.inputs_echo?.globals?.project_name ||
                  '(no project named)';

  const noResults = !pipelineR && !wellR && !ctR;

  return (
    <div className="space-y-8">
      <PageHeader
        Icon={FileDown}
        eyebrow="One-page summary"
        title="Project Export"
        subtitle="Snapshot of all module estimates run this session. Print to PDF for management circulation."
      />

      <div className="flex gap-3 print:hidden">
        <button
          onClick={() => window.print()}
          className="bg-amber hover:bg-amber/90 text-bg-dark font-bold py-2.5 px-5 rounded-sm uppercase tracking-wider text-sm flex items-center gap-2 shadow-lg shadow-amber/20"
        >
          <Printer className="w-4 h-4" />
          Print / Save as PDF
        </button>
      </div>

      {noResults && (
        <Card className="border-l-4 border-l-amber p-5">
          <div className="flex gap-3">
            <AlertCircle className="w-5 h-5 text-amber flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-300">
              <span className="font-bold text-amber">No estimates yet. </span>
              Run estimates on the Pipeline, Well, and/or CT pages first. They'll appear here automatically.
            </div>
          </div>
        </Card>
      )}

      {/* The printable area */}
      <div id="export-sheet" className="bg-white text-slate-900 rounded-sm p-8 md:p-12 shadow-2xl">
        <ExportContent project={project} pipeline={pipelineR} well={wellR} ct={ctR} />
      </div>

      <style>{`
        @media print {
          @page { margin: 1cm; size: A4 portrait; }
          body { background: white !important; }
          .print\\:hidden { display: none !important; }
          #export-sheet { box-shadow: none !important; padding: 0 !important; border-radius: 0 !important; }
          header, footer, nav { display: none !important; }
        }
      `}</style>
    </div>
  );
}

function ExportContent({ project, pipeline, well, ct }) {
  const today = new Date().toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b-2 border-slate-900 pb-4">
        <div className="text-[10px] tracking-[0.3em] uppercase font-bold text-slate-600 mb-1">NNPC Cost Intelligence Platform</div>
        <h1 className="text-3xl font-bold text-slate-900 leading-tight">{project}</h1>
        <div className="flex justify-between mt-2 text-sm text-slate-600">
          <div>Project cost estimate · {today}</div>
          <div>Confidential — Internal use only</div>
        </div>
      </div>

      {/* Modules */}
      {pipeline && <PrintModule title="Pipeline" result={pipeline} extras={pipelineExtras(pipeline)} />}
      {well     && <PrintModule title="Well Services" result={well}     extras={wellExtras(well)} />}
      {ct       && <PrintModule title="Coiled Tubing" result={ct}       extras={ctExtras(ct)} />}

      {!pipeline && !well && !ct && (
        <div className="text-center py-12 text-slate-400 italic">
          No estimates run yet. Visit the module pages to generate results.
        </div>
      )}

      {/* Grand total if multiple modules */}
      {[pipeline, well, ct].filter(Boolean).length > 1 && (
        <div className="border-t-2 border-slate-900 pt-4">
          <PrintGrandTotal pipeline={pipeline} well={well} ct={ct} />
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-slate-300 pt-3 text-[10px] text-slate-500 leading-relaxed">
        Generated from the NNPC Cost Intelligence Platform v2.0. All rates normalised to USD 2024 real terms.
        Benchmarks derived from tender/AFE/BEME data across 6 operators (SPDC, Seplat, NPDC/ARAHAS, NAOC/Oando, HEOSL, Sahara Energy).
        Underlying database not exposed; outputs are aggregate bands only.
      </div>
    </div>
  );
}

function PrintModule({ title, result, extras }) {
  return (
    <div>
      <h2 className="text-lg font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 mb-3">
        {title}
      </h2>

      {/* Echo of inputs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-4">
        {extras.map((e, i) => (
          <div key={i}>
            <div className="text-slate-500 uppercase tracking-wider">{e.k}</div>
            <div className="font-semibold text-slate-900">{e.v}</div>
          </div>
        ))}
      </div>

      {/* Cost band */}
      <div className="grid grid-cols-3 border border-slate-300 mb-3">
        <div className="text-center py-3 px-3 border-r border-slate-300">
          <div className="text-xs uppercase text-slate-500 mb-1">Low</div>
          <div className="text-2xl font-bold text-slate-900 num-tabular">{fmt.usdFull(result.total.low)}</div>
        </div>
        <div className="text-center py-3 px-3 border-r border-slate-300 bg-amber/10">
          <div className="text-xs uppercase text-amber-700 font-bold mb-1">Mid (recommended)</div>
          <div className="text-2xl font-bold text-amber-700 num-tabular">{fmt.usdFull(result.total.mid)}</div>
        </div>
        <div className="text-center py-3 px-3">
          <div className="text-xs uppercase text-slate-500 mb-1">High</div>
          <div className="text-2xl font-bold text-slate-900 num-tabular">{fmt.usdFull(result.total.high)}</div>
        </div>
      </div>

      <div className="grid grid-cols-3 text-xs text-slate-600 mb-3">
        <div>Direct cost (Mid): <span className="font-semibold text-slate-900">{fmt.usdFull(result.direct_cost.mid)}</span></div>
        <div>+ Contingency: <span className="font-semibold text-slate-900">{fmt.usdFull(result.contingency.mid)}</span></div>
        <div>+ VAT: <span className="font-semibold text-slate-900">{fmt.usdFull(result.vat.mid)}</span></div>
      </div>

      {/* Full itemised breakdown */}
      {result.breakdown && result.breakdown.length > 0 && (
        <table className="w-full text-xs border border-slate-300 mb-3">
          <thead>
            <tr className="bg-slate-100">
              <th className="text-left px-2 py-1.5 font-semibold text-slate-700">Component</th>
              <th className="text-right px-2 py-1.5 font-semibold text-slate-700">Low</th>
              <th className="text-right px-2 py-1.5 font-semibold text-slate-700">Mid</th>
              <th className="text-right px-2 py-1.5 font-semibold text-slate-700">High</th>
            </tr>
          </thead>
          <tbody>
            {result.breakdown.map((b, i) => (
              <PrintBreakdownRows key={i} row={b} />
            ))}
          </tbody>
        </table>
      )}

      <div className="text-xs text-slate-500 italic">
        Confidence: <span className="font-bold text-slate-700">{result.confidence}</span>
        {result.diagnostics && result.diagnostics.length > 0 && (
          <span> · {result.diagnostics.length} diagnostic note{result.diagnostics.length > 1 ? 's' : ''}</span>
        )}
      </div>
    </div>
  );
}

function PrintBreakdownRows({ row }) {
  const hasKids = row.children && row.children.length > 0;
  return (
    <>
      <tr className="border-t border-slate-200">
        <td className="px-2 py-1.5 font-semibold text-slate-900">{row.component}</td>
        <td className="px-2 py-1.5 text-right text-slate-600 num-tabular">{fmt.usdFull(row.low)}</td>
        <td className="px-2 py-1.5 text-right text-slate-900 font-semibold num-tabular">{fmt.usdFull(row.mid)}</td>
        <td className="px-2 py-1.5 text-right text-slate-600 num-tabular">{fmt.usdFull(row.high)}</td>
      </tr>
      {hasKids && row.children.map((c, j) => (
        <tr key={j} className="text-[11px]">
          <td className="px-2 py-1 pl-6 text-slate-500">
            {c.label}
            {c.qty != null && <span className="text-slate-400"> · {c.qty.toLocaleString()} {c.qty_unit}</span>}
            {c.unit_rate_mid != null && <span className="text-slate-400"> @ ${c.unit_rate_mid.toLocaleString(undefined,{maximumFractionDigits:2})}{c.unit_rate_unit}</span>}
          </td>
          <td className="px-2 py-1 text-right text-slate-400 num-tabular">{fmt.usdFull(c.low)}</td>
          <td className="px-2 py-1 text-right text-slate-600 num-tabular">{fmt.usdFull(c.mid)}</td>
          <td className="px-2 py-1 text-right text-slate-400 num-tabular">{fmt.usdFull(c.high)}</td>
        </tr>
      ))}
    </>
  );
}

function PrintGrandTotal({ pipeline, well, ct }) {
  const sum = (k) => (pipeline?.total[k] || 0) + (well?.total[k] || 0) + (ct?.total[k] || 0);
  return (
    <div>
      <h2 className="text-lg font-bold uppercase tracking-wider text-slate-900 mb-3">Project Grand Total</h2>
      <div className="grid grid-cols-3 border-2 border-amber bg-amber/5">
        <div className="text-center py-4 px-3 border-r border-amber/40">
          <div className="text-xs uppercase text-slate-600 mb-1">Low</div>
          <div className="text-2xl font-bold text-slate-900 num-tabular">{fmt.usdFull(sum('low'))}</div>
        </div>
        <div className="text-center py-4 px-3 border-r border-amber/40 bg-amber/20">
          <div className="text-xs uppercase text-amber-700 font-bold mb-1">Mid</div>
          <div className="text-3xl font-bold text-amber-700 num-tabular">{fmt.usdFull(sum('mid'))}</div>
        </div>
        <div className="text-center py-4 px-3">
          <div className="text-xs uppercase text-slate-600 mb-1">High</div>
          <div className="text-2xl font-bold text-slate-900 num-tabular">{fmt.usdFull(sum('high'))}</div>
        </div>
      </div>
      <p className="text-xs text-slate-500 italic mt-2">Sum of module totals. Excludes any project-level cross-module discounts or shared mobilisation savings.</p>
    </div>
  );
}

function pipelineExtras(r) {
  const i = r.inputs_echo;
  return [
    { k: 'Diameter / Schedule', v: `${i.dia}″ ${i.sched}` },
    { k: 'Terrain',             v: i.terrain },
    { k: 'Length / Duration',   v: `${i.length_km} km · ${i.duration_days} d` },
    { k: 'Scope class',         v: i.scope_class },
  ];
}
function wellExtras(r) {
  const i = r.inputs_echo;
  return [
    { k: 'Well name',           v: i.well_name },
    { k: 'TVD',                 v: `${i.tvd_m} m` },
    { k: 'Well type',           v: i.well_type },
    { k: '# Wells',             v: String(i.n_wells) },
  ];
}
function ctExtras(r) {
  const i = r.inputs_echo;
  return [
    { k: 'CT size',             v: i.ct_size },
    { k: 'Wells / days each',   v: `${i.n_wells} × ${i.days_per_well}d` },
    { k: 'Activity factor',     v: `${i.activity_factor}×` },
    { k: 'Reference tender',    v: i.reference_tender },
  ];
}

function safeParse(key) {
  try { const r = sessionStorage.getItem(key); return r ? JSON.parse(r) : null; }
  catch { return null; }
}
