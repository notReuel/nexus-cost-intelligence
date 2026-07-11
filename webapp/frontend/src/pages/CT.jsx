import { useEffect, useState } from 'react';
import { Wrench } from 'lucide-react';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, NumberInput, SelectInput, TextInput,
         CostBandCard, BreakdownTable, DiagnosticsList, RunButton, SourceNote } from '../components/UI.jsx';

const STORAGE_KEY = 'ndcip:ct_inputs';

export default function CT({ hideHeader = false }) {
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
      const r = await api.estimateCT(inputs);
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
          Icon={Wrench}
          eyebrow="Module · Coiled Tubing"
          title="Coiled Tubing Estimator"
          subtitle="11-vendor Seplat 2024 + 6-vendor NAOC 2021 cross-tender benchmark. 4 vendors overlap — market deflation tracked. Reference-tender-aware: switch the benchmark basis as needed."
        />
      )}

      <div className="grid lg:grid-cols-12 gap-6">
        {/* Inputs */}
        <Card className="lg:col-span-4 p-6 lg:sticky lg:top-24 self-start">
          <SectionHeader label="CT job scope" />
          <div className="space-y-4">
            <TextInput
              label="Project name"
              value={inputs.globals.project_name}
              onChange={(v) => updateGlobals({ project_name: v })}
              placeholder="e.g. CT Campaign 2026"
            />
            <SelectInput
              label="CT unit size"
              value={inputs.ct_size}
              onChange={(v) => update({ ct_size: v })}
              options={opts.ct_size}
              hint="1.5″ is most common; all 11 Seplat vendors bid it."
            />
            <div className="grid grid-cols-2 gap-3">
              <NumberInput
                label="Number of wells"
                value={inputs.n_wells}
                onChange={(v) => update({ n_wells: v })}
                unit="wells"
                min={1}
              />
              <NumberInput
                label="Days per well"
                value={inputs.days_per_well}
                onChange={(v) => update({ days_per_well: v })}
                unit="days"
                min={1}
              />
            </div>
            <NumberInput
              label="Activity factor"
              value={inputs.activity_factor}
              onChange={(v) => update({ activity_factor: v })}
              unit="×"
              step={0.1}
              min={0.1}
              hint="1.0× = same intensity as CER assumption. 0.5× = half activity."
            />
          </div>

          <SectionHeader label="Benchmark source" />
          <SelectInput
            label="Reference tender"
            value={inputs.reference_tender}
            onChange={(v) => update({ reference_tender: v })}
            options={opts.ct_reference}
            hint="Seplat 2024 = current market. NAOC 2021 = historical/conservative. Combined = widest band."
          />

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
              <Wrench className="w-12 h-12 text-amber/40 mx-auto mb-4" />
              <h3 className="text-xl font-bold text-slate-200 mb-2">Ready to estimate</h3>
              <p className="text-slate-400 max-w-md mx-auto">Set scope and reference tender, then run the estimate.</p>
            </Card>
          )}

          {loading && <Card className="p-12 text-center text-slate-500 animate-pulse">Computing estimate…</Card>}

          {result && (
            <>
              <CostBandCard
                label="Total CT cost (incl. VAT)"
                band={result.total}
                confidence={result.confidence}
                unit={`${fmt.usdFull(result.per_unit.usd_per_well.mid)}/well  ·  ${fmt.usdFull(result.per_unit.usd_per_day.mid)}/day`}
              />
              <DiagnosticsList items={result.diagnostics} />

              <Card className="p-6">
                <h3 className="text-amber font-semibold tracking-wide uppercase text-sm mb-4">Cost build-up</h3>
                <BreakdownTable rows={result.breakdown} />
                <div className="mt-4 grid grid-cols-3 gap-4 text-sm border-t border-slate-700/50 pt-4">
                  <KV k="Direct cost (Mid)" v={fmt.usdFull(result.direct_cost.mid)} />
                  <KV k="+ Contingency"     v={fmt.usdFull(result.contingency.mid)} />
                  <KV k="+ VAT"             v={fmt.usdFull(result.vat.mid)} />
                </div>
              </Card>

              <Card className="p-5 border-l-4 border-l-teal">
                <h4 className="text-teal font-bold text-xs uppercase tracking-wider mb-2">Cross-tender market signal</h4>
                <p className="text-sm text-slate-300 leading-relaxed">
                  3 of 4 vendors that bid both NAOC 2021 and Seplat 2024 cut day rates 40–52% over 3 years (CAGR −15% to −22%).
                  Only one vendor held flat. <strong>If reviewing 2026+ quotes, use Seplat 2024 as primary benchmark.</strong>
                </p>
              </Card>

              <SourceNote>
                17 unique vendors across 2 tenders. Per-well stats derived from 10-well program totals (Seplat) and Year 1 of 2-year+1 contract (NAOC). Vendor identities are not exposed in this view.
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
  ct_size: ['1.25"','1.5"','1.75"'],
  ct_reference: ['Seplat 2024 (primary)','NAOC 2021','Combined (both)'],
};

function defaultInputs() {
  return {
    ct_size: '1.5"', n_wells: 1, days_per_well: 5, activity_factor: 1.0,
    reference_tender: 'Seplat 2024 (primary)',
    globals: {
      project_name: 'My CT Job',
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
function saveResult(r) { try { sessionStorage.setItem('ndcip:ct_result', JSON.stringify(r)); } catch {} }
