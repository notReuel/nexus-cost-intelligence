import { useEffect, useState } from 'react';
import { Activity, Save, BookOpen, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, NumberInput, SelectInput, TextInput,
         CostBandCard, BreakdownTable, DiagnosticsList, RunButton, SourceNote } from '../components/UI.jsx';

const STORAGE_KEY = 'ndcip:pipeline_inputs';

export default function Pipeline({ hideHeader = false }) {
  const [opts, setOpts] = useState(null);
  const [inputs, setInputs] = useState(loadInputs());
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.options().then(setOpts).catch(() => setOpts(FALLBACK_OPTS));
  }, []);

  const update = (patch) => setInputs((prev) => ({ ...prev, ...patch }));
  const updateGlobals = (patch) => setInputs((prev) => ({ ...prev, globals: { ...prev.globals, ...patch } }));

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.estimatePipeline(inputs);
      setResult(r);
      saveInputs(inputs);
      saveResult(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!opts) return <div className="text-slate-500">Loading…</div>;

  return (
    <div className="space-y-8">
      {!hideHeader && (
        <PageHeader
          Icon={Activity}
          eyebrow="Module · Pipeline construction"
          title="Pipeline Estimator"
          subtitle="NNPC lay & weld benchmarks from 5 operators. Scope-class-aware. Returns Low / Mid / High band with full component build-up and envelope diagnostics."
        />
      )}

      <div className="grid lg:grid-cols-12 gap-6">
        {/* Inputs panel */}
        <Card className="lg:col-span-4 p-6 lg:sticky lg:top-24 self-start">
          <SectionHeader label="Project scope" />
          <div className="space-y-4">
            <TextInput
              label="Project name"
              value={inputs.globals.project_name}
              onChange={(v) => updateGlobals({ project_name: v })}
              placeholder="e.g. EGWA-2 bypass"
            />
            <div className="grid grid-cols-2 gap-3">
              <SelectInput
                label="Diameter (in)"
                value={String(inputs.dia)}
                onChange={(v) => update({ dia: Number(v) })}
                options={opts.diameter_inches.map(String)}
              />
              <SelectInput
                label="Schedule"
                value={inputs.sched}
                onChange={(v) => update({ sched: v })}
                options={opts.schedule}
              />
            </div>
            <SelectInput
              label="Terrain"
              value={inputs.terrain}
              onChange={(v) => update({ terrain: v })}
              options={opts.terrain}
            />
            <SelectInput
              label="Scope class"
              value={inputs.scope_class}
              onChange={(v) => update({ scope_class: v })}
              options={opts.scope_class}
              hint="LINEAR LAY = kilometre-scale. ON-SUPPORT FAB = bypass/manifold. BURIED = excavated/buried."
            />
            <div className="grid grid-cols-2 gap-3">
              <NumberInput
                label="Length"
                value={inputs.length_km}
                onChange={(v) => update({ length_km: v })}
                unit="km"
                step={0.001}
                min={0.001}
              />
              <NumberInput
                label="Duration"
                value={inputs.duration_days}
                onChange={(v) => update({ duration_days: v })}
                unit="days"
                min={1}
              />
            </div>
          </div>

          <SectionHeader label="Commercial terms" />
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <NumberInput
                label="Contingency"
                value={Math.round(inputs.globals.contingency_pct * 100)}
                onChange={(v) => updateGlobals({ contingency_pct: v / 100 })}
                unit="%"
                step={1}
                min={0}
              />
              <NumberInput
                label="VAT"
                value={inputs.globals.vat_pct * 100}
                onChange={(v) => updateGlobals({ vat_pct: v / 100 })}
                unit="%"
                step={0.5}
                min={0}
              />
            </div>
          </div>

          <div className="mt-6">
            <RunButton onClick={run} loading={loading} label="Run estimate" />
          </div>
          {error && <p className="text-rose-400 text-sm mt-3">{error}</p>}
        </Card>

        {/* Results panel */}
        <div className="lg:col-span-8 space-y-6">
          {!result && !loading && (
            <Card className="p-12 text-center">
              <Activity className="w-12 h-12 text-amber/40 mx-auto mb-4" />
              <h3 className="text-xl font-bold text-slate-200 mb-2">Ready to estimate</h3>
              <p className="text-slate-400 max-w-md mx-auto">
                Set your scope on the left and click <span className="text-amber font-bold">Run estimate</span>.
                Returns Low/Mid/High band with full build-up.
              </p>
            </Card>
          )}

          {loading && (
            <Card className="p-12 text-center text-slate-500">
              <div className="animate-pulse">Computing estimate…</div>
            </Card>
          )}

          {result && (
            <>
              <CostBandCard
                label="Total cost (incl. VAT)"
                band={result.total}
                confidence={result.confidence}
                unit={`${fmt.usd(result.per_unit.usd_per_m.mid)}/m  ·  ${fmt.usd(result.per_unit.usd_per_km.mid)}/km`}
              />
              <DiagnosticsList items={result.diagnostics} />

              <Card className="p-6">
                <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-4">Component build-up</h3>
                <BreakdownTable rows={result.breakdown} />
                <div className="mt-4 grid grid-cols-3 gap-4 text-sm border-t border-slate-700/50 pt-4">
                  <KV k="Direct cost (Mid)" v={fmt.usdFull(result.direct_cost.mid)} />
                  <KV k="+ Contingency"     v={fmt.usdFull(result.contingency.mid)} />
                  <KV k="+ VAT"             v={fmt.usdFull(result.vat.mid)} />
                </div>
              </Card>

              <CatalogueDeepDive scope={inputs} />

              <SourceNote>
                Based on NNPC tender data across 5 operators. Lay & weld rates from {result.confidence.toLowerCase()}-confidence
                benchmark records. Individual operator and vendor identities are not exposed in this view.
              </SourceNote>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-slate-500 mb-1">{k}</div>
      <div className="text-base font-semibold text-slate-200 num-tabular">{v}</div>
    </div>
  );
}

const FALLBACK_OPTS = {
  diameter_inches: [2,3,4,6,8,10,12,16],
  schedule: ['Sch 40','Sch 80','Sch 120','Sch 160'],
  terrain: ['Land','Swamp'],
  scope_class: ['LINEAR LAY','ON-SUPPORT FAB','BURIED'],
};

function defaultInputs() {
  return {
    dia: 6, sched: 'Sch 40', terrain: 'Swamp',
    length_km: 5.0, duration_days: 30, scope_class: 'LINEAR LAY',
    globals: {
      project_name: 'NNPC Project',
      ref_year: 2024, fx_mult: 1.55, sec_floor: 50, mob_uplift: 1.5,
      contingency_pct: 0.10, vat_pct: 0.075, band_pct: 0.15,
    },
  };
}
function loadInputs() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : defaultInputs();
  } catch { return defaultInputs(); }
}
function saveInputs(i) { try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(i)); } catch {} }
function saveResult(r) { try { sessionStorage.setItem('ndcip:pipeline_result', JSON.stringify(r)); } catch {} }

// ─── Inline catalogue deep-dive ──────────────────────────────────────────
// Shows catalogue entries matching the current Pipeline scope (terrain mostly,
// since most Pipeline benchmarks are terrain-aware). Gives the user transparency
// into which underlying records contributed to the estimate.
function CatalogueDeepDive({ scope }) {
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    // Pull a sample of construction items in the right terrain
    api.catalogueItems({
      category: 'Construction',
      limit: 8,
    }).then(d => {
      // Filter client-side by terrain matching the current scope
      const filtered = d.items.filter(i =>
        !i.spec?.terrain || i.spec.terrain === scope.terrain || i.spec.terrain === 'Land+Swamp'
      ).slice(0, 6);
      setItems(filtered);
    }).catch(() => setItems([]));
  }, [open, scope.terrain]);

  return (
    <Card className="p-6">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-1">
            Dataset traceability
          </h3>
          <p className="text-xs text-slate-400">
            Catalogue entries that feed this estimate. 324 line items total across 7 categories.
          </p>
        </div>
        <button
          onClick={() => setOpen(o => !o)}
          className="text-xs uppercase tracking-wider px-3 py-1.5 rounded border border-amber/40 text-amber hover:bg-amber/10 transition-colors">
          {open ? 'Hide' : 'Show'} related items
        </button>
      </div>

      {open && items === null && (
        <div className="text-sm text-slate-500 py-4">Loading…</div>
      )}

      {open && items && items.length > 0 && (
        <>
          <div className="rounded border border-slate-700/40 overflow-hidden mt-3">
            <table className="w-full text-xs">
              <thead className="bg-bg-dark">
                <tr>
                  <th className="text-left px-3 py-2 text-slate-400 uppercase tracking-wider">Item</th>
                  <th className="text-left px-3 py-2 text-slate-400 uppercase tracking-wider">Unit</th>
                  <th className="text-right px-3 py-2 text-amber uppercase tracking-wider">Mid</th>
                  <th className="text-center px-3 py-2 text-slate-400 uppercase tracking-wider">n</th>
                  <th className="text-center px-3 py-2 text-slate-400 uppercase tracking-wider">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {items.map(i => (
                  <tr key={i.id} className="border-t border-slate-700/30">
                    <td className="px-3 py-2 text-slate-200">{i.item}</td>
                    <td className="px-3 py-2 text-slate-400">{i.unit}</td>
                    <td className="px-3 py-2 text-right num-tabular text-amber font-semibold">
                      {i.mid >= 100 ? `$${i.mid.toFixed(0)}` : `$${i.mid.toFixed(2)}`}
                    </td>
                    <td className="px-3 py-2 text-center text-slate-400">{i.n_records}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                        i.confidence === 'HIGH' ? 'border-emerald-400/40 text-emerald-300 bg-emerald-500/10' :
                        i.confidence === 'MEDIUM' ? 'border-amber/40 text-amber bg-amber/10' :
                        'border-rose-400/40 text-rose-300 bg-rose-500/10'
                      }`}>{i.confidence}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link to="/catalogue"
            className="inline-flex items-center gap-1.5 mt-4 text-xs uppercase tracking-wider text-amber font-bold hover:gap-2.5 transition-all">
            <BookOpen className="w-3.5 h-3.5" />
            Open full catalogue
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </>
      )}
    </Card>
  );
}
