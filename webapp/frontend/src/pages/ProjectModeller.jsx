import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, FolderOpen, ArrowRight, Loader2, AlertTriangle } from 'lucide-react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { Panel, Segmented, Field, TextIn, ConfidencePill, CoverageBar, money, moneyK } from '../components/Enterprise.jsx';

const DEFAULT = {
  project_name: 'Untitled swamp flowline',
  operator: 'Blended', year: 2023, project_type: 'New Flowline',
  dia: 6, sched: 'Sch 40', terrain: 'Swamp',
  length_m: 5000, duration_days: 30, n_tie_ins: 0, n_crossings: 0,
  sections: { materials: true, welding: true, civil: true, ndt: true, coating: true, hydrotest: true, mob_cashes_security: true },
  contingency_pct: 0.10, vat_pct: 0.075,
};

const SECTION_LABELS = {
  materials: 'Materials', welding: 'Welding & lay', civil: 'Civil works',
  ndt: 'NDT', coating: 'Coating', hydrotest: 'Hydrotest', mob_cashes_security: 'Mob / CASHES / Security',
};

export default function ProjectModeller() {
  const nav = useNavigate();
  const { auth } = useAuth();
  const [scope, setScope] = useState(() => {
    try { const s = localStorage.getItem('ncmp:modeller_input'); if (s) return { ...DEFAULT, ...JSON.parse(s) }; } catch {}
    return DEFAULT;
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const timer = useRef(null);

  const set = (patch) => setScope(s => ({ ...s, ...patch }));
  const toggle = (k) => setScope(s => ({ ...s, sections: { ...s.sections, [k]: !s.sections[k] } }));

  const run = useCallback(async (sc) => {
    setLoading(true); setErr(null);
    try { setResult(await api.modelProject(sc, auth?.token)); }
    catch (e) { setErr(String(e.message || e)); }
    finally { setLoading(false); }
  }, [auth?.token]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { localStorage.setItem('ncmp:modeller_input', JSON.stringify(scope)); run(scope); }, 300);
    return () => clearTimeout(timer.current);
  }, [scope, run]);

  const saveProject = () => { localStorage.setItem('ncmp:modeller_saved', JSON.stringify(scope)); alert('Project saved to this browser.'); };
  const loadProject = () => { try { const s = localStorage.getItem('ncmp:modeller_saved'); if (s) setScope({ ...DEFAULT, ...JSON.parse(s) }); else alert('No saved project.'); } catch {} };
  const toBudget = () => {
    if (!result) return;
    localStorage.setItem('ncmp:budget', JSON.stringify({ scope, result }));
    nav('/budget');
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-5">
      {/* ── Form ─────────────────────────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Project Model</h1>
            <p className="text-[13px] text-slate-500">Build a swamp lay &amp; weld scope. Every rate is drawn from real observations.</p>
          </div>
          <div className="flex gap-2">
            <button onClick={saveProject} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-slate-300 text-[13px] text-slate-700 hover:border-accent/60 hover:text-accent"><Save className="w-3.5 h-3.5" />Save</button>
            <button onClick={loadProject} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-slate-300 text-[13px] text-slate-700 hover:border-accent/60 hover:text-accent"><FolderOpen className="w-3.5 h-3.5" />Load</button>
          </div>
        </div>

        <Panel num="01" title="Project identity">
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Project name"><TextIn value={scope.project_name} onChange={e => set({ project_name: e.target.value })} /></Field>
            <Field label="Pricing basis">
              <div className="flex items-center gap-2 h-[34px] px-3 rounded-sm border border-slate-200 bg-slate-50 text-[13px] text-slate-600">
                <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                Blended · normalised to USD 2024 real
              </div>
            </Field>
            <div className="sm:col-span-2">
              <Segmented label="Operator benchmark" value={scope.operator}
                options={['Blended', 'SPDC', 'Seplat', 'NPDC', 'ARAHAS']}
                onChange={v => set({ operator: v })}
                locked={[{ label: 'Sahara Energy', tooltip: 'Coming with Phase 3 data acquisition — requires additional operator data currently being collected' }]} />
            </div>
          </div>
        </Panel>

        <Panel num="02" title="Scope & geometry">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <Segmented label="Project type" value={scope.project_type}
                options={['New Flowline', 'Replacement Line', 'Bypass']} onChange={v => set({ project_type: v })}
                locked={[{ label: 'Loop Line' }, { label: 'Reroute/Diversion' }, { label: 'Brownfield Mod' }]} />
            </div>
            <Field label="Diameter (inch)"><Segmented value={scope.dia} options={[2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 28].map(d => ({ value: d, label: `${d}"` }))} onChange={v => set({ dia: v })} /></Field>
            <Field label="Schedule"><Segmented value={scope.sched} options={['Sch 40', 'Sch 80']} onChange={v => set({ sched: v })} locked={[{ label: 'Sch 120' }, { label: 'Sch 160' }]} /></Field>
            <Field label="Terrain"><Segmented value={scope.terrain} options={['Land', 'Swamp']} onChange={v => set({ terrain: v })} locked={scope.terrain === 'Swamp' ? [{ label: 'Freshwater swamp' }, { label: 'Mangrove' }] : []} /></Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Length (m)"><TextIn type="number" value={scope.length_m} onChange={e => set({ length_m: Number(e.target.value) })} /></Field>
              <Field label="Duration (days)"><TextIn type="number" value={scope.duration_days} onChange={e => set({ duration_days: Number(e.target.value) })} /></Field>
            </div>
          </div>
        </Panel>

        <Panel num="03" title="Scope drivers">
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Number of tie-ins"><TextIn type="number" min={0} value={scope.n_tie_ins} onChange={e => set({ n_tie_ins: Number(e.target.value) })} /></Field>
            <Field label="Number of crossings" hint="HDD / road / river pooled — single count">
              <TextIn type="number" min={0} value={scope.n_crossings} onChange={e => set({ n_crossings: Number(e.target.value) })} />
              <div className="flex flex-wrap gap-1 mt-2">{['HDD/Bored', 'Road', 'River', 'Sleeper'].map(c => <span key={c} className="px-2 py-0.5 rounded-sm border border-dashed border-slate-300 text-slate-500 text-[10px]">{c}</span>)}</div>
            </Field>
          </div>
        </Panel>

        <Panel num="04" title="Scope completeness" subtitle="Toggle sections in or out of the estimate">
          <div className="grid sm:grid-cols-2 gap-2.5">
            {Object.keys(SECTION_LABELS).map(k => (
              <label key={k} className="flex items-center gap-2.5 px-3 py-2 rounded-sm border border-slate-300 bg-[#F8FAFC] cursor-pointer hover:border-accent/40">
                <input type="checkbox" checked={scope.sections[k]} onChange={() => toggle(k)} className="accent-accent w-4 h-4" />
                <span className="text-[13px] text-slate-800">{SECTION_LABELS[k]}</span>
              </label>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-200">
            <Field label={`Contingency ${(scope.contingency_pct * 100).toFixed(0)}%`}><input type="range" min={0} max={0.3} step={0.01} value={scope.contingency_pct} onChange={e => set({ contingency_pct: Number(e.target.value) })} className="w-full accent-accent" /></Field>
            <Field label={`VAT ${(scope.vat_pct * 100).toFixed(1)}%`}><input type="range" min={0} max={0.15} step={0.005} value={scope.vat_pct} onChange={e => set({ vat_pct: Number(e.target.value) })} className="w-full accent-accent" /></Field>
          </div>
        </Panel>
      </div>

      {/* ── Sticky rolling estimate ──────────────────────────── */}
      <div className="xl:sticky xl:top-20 h-fit space-y-3">
        <Panel title="Rolling estimate" right={loading ? <Loader2 className="w-4 h-4 animate-spin text-accent" /> : null}>
          {err && <div className="flex items-start gap-2 text-[12px] text-red-700 bg-red-50 rounded-sm p-2 mb-3"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />{err}</div>}
          <div className="text-center py-2">
            <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Total (Mid, incl. VAT)</div>
            <div className="text-3xl font-bold text-accent num-tabular">{result ? money(result.total.mid) : '—'}</div>
            {result && <div className="text-[12px] text-slate-500 num-tabular mt-1">{money(result.total.low)} – {money(result.total.high)}</div>}
          </div>
          {result && (
            <>
              <div className="grid grid-cols-2 gap-2 mt-3 text-center">
                <Stat label="Per metre" value={`${money(result.per_m.mid, 0)}/m`} />
                <Stat label="Direct" value={moneyK(result.direct.mid)} />
              </div>
              <div className="mt-4">
                <div className="flex items-center justify-between text-[11px] text-slate-600 mb-1.5">
                  <span>Evidence coverage</span>
                  <span>{result.backed_lines}/{result.total_lines} lines backed</span>
                </div>
                <CoverageBar pct={result.coverage_pct} />
              </div>
              <div className="mt-4 space-y-1 max-h-52 overflow-y-auto pr-1">
                {Object.entries(result.section_totals).map(([s, t]) => (
                  <div key={s} className="flex items-center justify-between text-[12px] py-1 border-b border-slate-200">
                    <span className="text-slate-600 truncate">{s}</span>
                    <span className="num-tabular text-slate-800">{money(t.mid)}</span>
                  </div>
                ))}
              </div>
              {result.diagnostics?.length > 0 && (
                <div className="mt-3 space-y-1">
                  {result.diagnostics.map((d, i) => <div key={i} className="text-[11px] text-amber-700 flex gap-1.5"><AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />{d}</div>)}
                </div>
              )}
            </>
          )}
          <button onClick={toBudget} disabled={!result}
            className="w-full mt-4 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-sm bg-accent text-[#F8FAFC] font-semibold text-sm hover:bg-accent-glow disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            Generate line-item budget <ArrowRight className="w-4 h-4" />
          </button>
        </Panel>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="bg-[#F8FAFC] rounded-sm border border-slate-200 py-2">
      <div className="text-[9px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className="text-sm font-semibold num-tabular text-slate-900 mt-0.5">{value}</div>
    </div>
  );
}
