import { useEffect, useState } from 'react';
import { ShieldCheck, AlertCircle } from 'lucide-react';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, NumberInput, SelectInput, TextInput,
         VerdictBadge, RunButton, SourceNote } from '../components/UI.jsx';

export default function QC() {
  const [module, setModule] = useState('Pipeline');
  const [vendor, setVendor] = useState('Vendor name');
  const [quoteRef, setQuoteRef] = useState('QTN-2026-001');
  const [currency, setCurrency] = useState('USD');
  const [total, setTotal] = useState(1000000);
  const [bandPct, setBandPct] = useState(0.15);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sourceBand, setSourceBand] = useState(null);   // band fetched from prior module run

  // Try to pre-fill band from sessionStorage prior estimate
  useEffect(() => {
    const key = { Pipeline: 'ndcip:pipeline_result', Well: 'ndcip:well_result', CT: 'ndcip:ct_result' }[module];
    try {
      const raw = sessionStorage.getItem(key);
      if (raw) {
        const r = JSON.parse(raw);
        setSourceBand({
          low: r.total.low, mid: r.total.mid, high: r.total.high,
          module: r.module,
        });
      } else {
        setSourceBand(null);
      }
    } catch { setSourceBand(null); }
  }, [module]);

  const run = async () => {
    if (!sourceBand) {
      setError(`No ${module} benchmark loaded. Run an estimate on the ${module} page first.`);
      return;
    }
    setLoading(true); setError(null);
    try {
      const r = await api.checkQuote({
        module,
        vendor_name: vendor,
        quote_reference: quoteRef,
        quote_currency: currency,
        quote_total: total,
        band_low: sourceBand.low,
        band_mid: sourceBand.mid,
        band_high: sourceBand.high,
        band_pct: bandPct,
      });
      setResult(r);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        Icon={ShieldCheck}
        eyebrow="Unified verification"
        title="Quote Checker"
        subtitle="Paste a vendor quote. Engine compares against the module's current benchmark band and returns GREEN / AMBER / RED verdict with position-in-band."
      />

      {/* Required prereq notice */}
      {!sourceBand && (
        <Card className="border-l-4 border-l-amber p-5">
          <div className="flex gap-3 items-start">
            <AlertCircle className="w-5 h-5 text-amber flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-300">
              <span className="font-bold text-amber">No benchmark loaded for {module}.</span>{' '}
              Run an estimate on the <span className="text-amber">{module}</span> page first, then come back here.
              The Quote Checker uses your current estimator inputs to compare against the quote.
            </div>
          </div>
        </Card>
      )}

      <div className="grid lg:grid-cols-12 gap-6">
        {/* Inputs */}
        <Card className="lg:col-span-5 p-6">
          <SectionHeader label="Quote details" />
          <div className="space-y-4">
            <SelectInput
              label="Module"
              value={module}
              onChange={setModule}
              options={['Pipeline', 'Well', 'CT']}
              hint="Determines which benchmark band to compare against."
            />
            <TextInput label="Vendor / contractor" value={vendor} onChange={setVendor} />
            <TextInput label="Quote reference" value={quoteRef} onChange={setQuoteRef} />
            <div className="grid grid-cols-2 gap-3">
              <SelectInput
                label="Currency"
                value={currency}
                onChange={setCurrency}
                options={['USD', 'NGN']}
              />
              <NumberInput
                label="Quote total"
                value={total}
                onChange={setTotal}
                unit={currency}
                min={1}
                step={1000}
              />
            </div>
            {currency === 'NGN' && (
              <p className="text-xs text-slate-500">
                NGN converts at ₦1,500/USD (CBN official) × 1.55 (parallel uplift) → FwdUSD basis.
              </p>
            )}
            <NumberInput
              label="GREEN/AMBER band threshold"
              value={Math.round(bandPct * 100)}
              onChange={(v) => setBandPct(v / 100)}
              unit="%"
              step={1}
              min={5}
              hint="Default ±15%. Tighter = stricter verdict."
            />
          </div>

          <div className="mt-6">
            <RunButton onClick={run} loading={loading} label="Check quote" />
          </div>
          {error && <p className="text-rose-400 text-sm mt-3">{error}</p>}
        </Card>

        {/* Benchmark display + Verdict */}
        <div className="lg:col-span-7 space-y-6">
          {sourceBand && (
            <Card className="p-6">
              <h3 className="text-xs uppercase tracking-wider text-slate-400 mb-4">Active benchmark · {sourceBand.module}</h3>
              <div className="grid grid-cols-3 gap-px bg-slate-700/50 rounded overflow-hidden">
                <BenchCell label="Low" value={sourceBand.low} />
                <BenchCell label="Mid" value={sourceBand.mid} highlight />
                <BenchCell label="High" value={sourceBand.high} />
              </div>
              <p className="text-xs text-slate-500 mt-3">From your most recent estimator run on the {sourceBand.module} page.</p>
            </Card>
          )}

          {result && (
            <Card accent className="p-6 md:p-8">
              <div className="flex flex-col items-center text-center gap-4 mb-6">
                <VerdictBadge colour={result.verdict_colour} text={result.verdict} />
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <Metric label="Quote (FwdUSD)" value={fmt.usdFull(result.quote_usd)} />
                <Metric label="Δ vs Mid" value={fmt.pct(result.delta_pct)} accent={result.verdict_colour} />
                <Metric label="In Low–High band" value={result.in_band ? '✅ YES' : '❌ NO'} accent={result.in_band ? 'green' : 'red'} />
                <Metric label="Position in band" value={fmt.pct0(result.position_in_band)} />
              </div>

              <div className="border-t border-slate-700/50 pt-5 text-sm text-slate-400">
                <strong className="text-slate-200">Interpretation:</strong>{' '}
                {result.verdict_colour === 'green' && 'Quote is within acceptable variance from benchmark Mid. Proceed with normal review.'}
                {result.verdict_colour === 'amber' && 'Quote is meaningfully off Mid. Challenge the vendor on cost drivers — equipment day rates, mob, personnel — before commercial close.'}
                {result.verdict_colour === 'red' && 'Quote is significantly off benchmark. Demand line-item breakdown. May indicate scope misalignment or unsustainable pricing.'}
              </div>
            </Card>
          )}

          {!result && sourceBand && (
            <Card className="p-12 text-center">
              <ShieldCheck className="w-12 h-12 text-amber/40 mx-auto mb-4" />
              <h3 className="text-xl font-bold text-slate-200 mb-2">Ready to check</h3>
              <p className="text-slate-400 max-w-md mx-auto">
                Enter the vendor quote details on the left and click <span className="text-amber font-bold">Check quote</span>.
              </p>
            </Card>
          )}

          <SourceNote>
            QC verdict uses the band returned by the active module's most recent estimate. Benchmark thresholds: ±{Math.round(bandPct*100)}% = GREEN, ±{Math.round(bandPct*200)}% = AMBER, beyond = RED.
          </SourceNote>
        </div>
      </div>
    </div>
  );
}

function BenchCell({ label, value, highlight }) {
  return (
    <div className={`${highlight ? 'bg-amber/10' : 'bg-bg-panel'} px-4 py-4 text-center`}>
      <div className={`text-xs uppercase tracking-wider mb-1 ${highlight ? 'text-amber font-bold' : 'text-slate-500'}`}>{label}</div>
      <div className={`text-xl font-bold num-tabular ${highlight ? 'text-amber' : 'text-slate-300'}`}>{fmt.usd(value)}</div>
    </div>
  );
}

function Metric({ label, value, accent }) {
  const color = {
    green: 'text-emerald-300',
    amber: 'text-amber',
    red: 'text-rose-300',
  }[accent] || 'text-slate-200';
  return (
    <div className="bg-bg-dark rounded p-4">
      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">{label}</div>
      <div className={`text-lg font-bold num-tabular ${color}`}>{value}</div>
    </div>
  );
}
