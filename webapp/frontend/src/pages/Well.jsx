import { useEffect, useState } from 'react';
import { Droplets, AlertTriangle } from 'lucide-react';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, NumberInput, SelectInput, TextInput,
         CostBandCard, BreakdownTable, DiagnosticsList, RunButton, SourceNote } from '../components/UI.jsx';

const STORAGE_KEY = 'ndcip:well_inputs';

export default function Well({ hideHeader = false }) {
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
      const r = await api.estimateWell(inputs);
      setResult(r);
      saveInputs(inputs);
      saveResult(r);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  if (!opts) return <div className="text-slate-500">Loading…</div>;

  return (
    <div className="space-y-8">
      {!hideHeader && (
        <PageHeader
          Icon={Droplets}
          eyebrow="Module · Well services"
          title="Well Services Estimator"
          subtitle="7-phase AFE build-up: pre-spud, rig move, 16″ / 12¼″ / 8½″ sections, testing, completions. Calibrated to Sahara Energy 2024/25 onshore vertical AFE."
        />
      )}

      {/* Confidence warning banner — Well is LOW confidence */}
      <Card className="border-l-4 border-l-rose-400 p-4">
        <div className="flex gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <span className="text-rose-300 font-bold uppercase tracking-wide text-xs">LOW confidence module · </span>
            <span className="text-slate-300">
              Single-source benchmark (one onshore vertical AFE). No swamp wells, no field test against a close-out yet.
              Use outputs for directional planning only. Validate against your own AFE history before tender QC.
            </span>
          </div>
        </div>
      </Card>

      <div className="grid lg:grid-cols-12 gap-6">
        {/* Inputs */}
        <Card className="lg:col-span-4 p-6 lg:sticky lg:top-24 self-start">
          <SectionHeader label="Well scope" />
          <div className="space-y-4">
            <TextInput
              label="Well name"
              value={inputs.well_name}
              onChange={(v) => update({ well_name: v })}
              placeholder="e.g. Well 1"
            />
            <NumberInput
              label="Target depth (TVD)"
              value={inputs.tvd_m}
              onChange={(v) => update({ tvd_m: v })}
              unit="m"
              min={100}
              step={100}
            />
            <SelectInput
              label="Well type"
              value={inputs.well_type}
              onChange={(v) => update({ well_type: v })}
              options={opts.well_type}
              hint="Calibration source is onshore vertical. Other types use the same baseline."
            />
            <NumberInput
              label="Number of wells"
              value={inputs.n_wells}
              onChange={(v) => update({ n_wells: v })}
              unit="wells"
              min={1}
            />
          </div>

          <SectionHeader label="Commercial terms" />
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

          <div className="mt-6">
            <RunButton onClick={run} loading={loading} />
          </div>
          {error && <p className="text-rose-400 text-sm mt-3">{error}</p>}
        </Card>

        {/* Results */}
        <div className="lg:col-span-8 space-y-6">
          {!result && !loading && (
            <Card className="p-12 text-center">
              <Droplets className="w-12 h-12 text-amber/40 mx-auto mb-4" />
              <h3 className="text-xl font-bold text-slate-200 mb-2">Ready to estimate</h3>
              <p className="text-slate-400 max-w-md mx-auto">Set your well scope on the left and run the estimate.</p>
            </Card>
          )}

          {loading && <Card className="p-12 text-center text-slate-500 animate-pulse">Computing estimate…</Card>}

          {result && (
            <>
              <CostBandCard
                label="Total well cost (incl. VAT)"
                band={result.total}
                confidence={result.confidence}
                unit={`${fmt.usdFull(result.per_unit.usd_per_well.mid)}/well  ·  ${fmt.usdFull(result.per_unit.usd_per_m_tvd.mid)}/m TVD`}
              />
              <DiagnosticsList items={result.diagnostics} />

              <Card className="p-6">
                <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-4">Phase breakdown</h3>
                <BreakdownTable rows={result.breakdown} />
                <div className="mt-4 grid grid-cols-3 gap-4 text-sm border-t border-slate-700/50 pt-4">
                  <KV k="Direct cost (Mid)" v={fmt.usdFull(result.direct_cost.mid)} />
                  <KV k="+ Contingency"     v={fmt.usdFull(result.contingency.mid)} />
                  <KV k="+ VAT"             v={fmt.usdFull(result.vat.mid)} />
                </div>
              </Card>

              <SourceNote>
                Based on a single NNPC operator's 2024/25 onshore vertical AFE. Phase scaling preserved; Low/Mid/High bands set at 0.85× / 1.00× / 1.20×.
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
  well_type: ['Onshore vertical','Onshore deviated','Swamp vertical','Swamp deviated'],
};

function defaultInputs() {
  return {
    well_name: 'Well 1', tvd_m: 3500, well_type: 'Onshore vertical', n_wells: 1,
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
function saveResult(r) { try { sessionStorage.setItem('ndcip:well_result', JSON.stringify(r)); } catch {} }
