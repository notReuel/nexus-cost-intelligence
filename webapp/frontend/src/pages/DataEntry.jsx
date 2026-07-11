import { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, Loader2, LogOut, Inbox, ShieldCheck, X } from 'lucide-react';
import { authApi } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { Panel, Field, TextIn, Segmented, ConfidencePill, money } from '../components/Enterprise.jsx';

const US_PPI = { 2015: 195.30, 2016: 195.36, 2017: 199.91, 2018: 204.50, 2019: 206.10, 2020: 206.50, 2021: 221.00, 2022: 250.90, 2023: 254.60, 2024: 257.70, 2025: 263.00 };
const CBN = { 2017: 305.79, 2021: 401.15, 2023: 645.16, 2024: 1486.57, 2025: 1554.62 };
function preview(rate, cur, yr) {
  const ppi = US_PPI[2024] / (US_PPI[yr] || US_PPI[2024]);
  if (cur === 'NGN') { const fx = CBN[yr] || CBN[2024]; return (rate / fx) * ppi; }
  return rate * ppi;
}

const SUBS = ['Lay & Weld', 'Field joint coating', 'Radiography', 'Hydrotesting', 'Excavation', 'ROW clearing', 'Mob / demob', 'Security / CASHES', 'Tie-ins', 'Line crossings', 'Pipe transport'];

export default function DataEntry() {
  const { auth, logout, hasRole } = useAuth();
  const [f, setF] = useState({ operator: 'Seplat', year: 2023, sub_category: 'Lay & Weld', dia: 6, terrain: 'Swamp', unit: 'm', orig_currency: 'NGN', orig_rate: 12911.5, notes: '' });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [pending, setPending] = useState(null);
  const [reviewBusy, setReviewBusy] = useState(null);
  const set = (p) => setF(s => ({ ...s, ...p }));

  const refreshPending = useCallback(() => {
    if (auth && hasRole('approver')) {
      authApi.pendingObservations(auth.token).then(setPending).catch(() => setPending([]));
    }
  }, [auth, hasRole]);

  useEffect(() => { refreshPending(); }, [refreshPending, done]);

  const usd = preview(Number(f.orig_rate), f.orig_currency, Number(f.year));

  const submit = async () => {
    setBusy(true); setDone(null);
    try {
      const res = await authApi.submitObservation(auth.token, {
        category_path: `Pipeline > Construction > ${f.sub_category}`,
        canonical_name: `${f.sub_category} ${f.dia}" ${f.terrain}`,
        unit: f.unit,
        attributes: { dia_in: Number(f.dia), terrain: f.terrain },
        source_type: 'tender', operator: f.operator,
        currency: f.orig_currency, orig_rate: Number(f.orig_rate), orig_year: Number(f.year),
        notes: f.notes,
      });
      setDone(res);
    } catch (e) { alert(String(e.message || e)); }
    finally { setBusy(false); }
  };

  const review = async (obsId, approve) => {
    setReviewBusy(obsId);
    try {
      await authApi.review(auth.token, obsId, approve);
      refreshPending();
    } catch (e) { alert(String(e.message || e)); }
    finally { setReviewBusy(null); }
  };

  if (!auth) {
    return (
      <div className="max-w-md mx-auto text-center py-16">
        <Inbox className="w-8 h-8 text-slate-400 mx-auto mb-3" />
        <p className="text-[13px] text-slate-500">Sign in to submit or review observations.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Data Entry</h1>
          <p className="text-[13px] text-slate-500">Submit → pending review → approval → benchmark. Every step goes through the secured v2 API.</p>
        </div>
        <div className="flex items-center gap-3 text-[12px] text-slate-500">
          <span className="px-2 py-1 rounded-sm bg-slate-100">{auth.name} · {auth.role}</span>
          <button onClick={logout} className="inline-flex items-center gap-1 text-slate-500 hover:text-red-600"><LogOut className="w-3.5 h-3.5" />Sign out</button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_320px] gap-4">
        {hasRole('estimator') ? (
          <Panel title="New observation">
            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Operator"><Segmented value={f.operator} options={['SPDC', 'Seplat', 'NPDC', 'ARAHAS']} onChange={v => set({ operator: v })} /></Field>
              <Field label="Year"><Segmented value={f.year} options={[2017, 2021, 2023, 2025].map(y => ({ value: y, label: `${y}` }))} onChange={v => set({ year: v })} /></Field>
              <Field label="Sub-category">
                <select value={f.sub_category} onChange={e => set({ sub_category: e.target.value })} className="w-full bg-[#F8FAFC] border border-slate-300 rounded-sm px-2.5 py-1.5 text-sm text-slate-900 focus:border-accent focus:outline-none">
                  {SUBS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="Diameter (inch)"><TextIn type="number" value={f.dia} onChange={e => set({ dia: Number(e.target.value) })} /></Field>
              <Field label="Terrain"><Segmented value={f.terrain} options={['Land', 'Swamp']} onChange={v => set({ terrain: v })} /></Field>
              <Field label="Unit"><TextIn value={f.unit} onChange={e => set({ unit: e.target.value })} /></Field>
              <Field label="Currency"><Segmented value={f.orig_currency} options={['USD', 'NGN']} onChange={v => set({ orig_currency: v })} /></Field>
              <Field label="Original rate"><TextIn type="number" value={f.orig_rate} onChange={e => set({ orig_rate: Number(e.target.value) })} /></Field>
              <div className="sm:col-span-2"><Field label="Notes"><TextIn value={f.notes} onChange={e => set({ notes: e.target.value })} /></Field></div>
            </div>
            <button onClick={submit} disabled={busy}
              className="w-full mt-4 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-sm bg-accent text-white font-semibold text-sm hover:bg-accent-glow disabled:opacity-40">
              {busy ? <><Loader2 className="w-4 h-4 animate-spin" />Submitting…</> : 'Submit for review'}
            </button>
          </Panel>
        ) : (
          <Panel title="New observation"><p className="text-[13px] text-slate-500">Your role ({auth.role}) can review submissions but not create new ones.</p></Panel>
        )}

        <div className="space-y-3">
          <Panel title="Normalisation preview">
            <div className="text-center py-2">
              <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">USD 2024 (real)</div>
              <div className="text-2xl font-bold text-accent num-tabular">${usd.toLocaleString('en-US', { maximumFractionDigits: 2 })}<span className="text-sm text-slate-500">/{f.unit}</span></div>
            </div>
          </Panel>

          {done && (
            <Panel title="Submitted">
              <div className="flex items-center gap-2 text-emerald-700 text-[13px] mb-2"><CheckCircle2 className="w-4 h-4" />Observation #{done.observation_id}</div>
              <div className="text-[12px] text-slate-500">{done.message}</div>
              <div className="mt-2"><ConfidencePill level="MODELLED" /> <span className="text-[11px] text-slate-500 ml-1">status: {done.status}</span></div>
            </Panel>
          )}
        </div>
      </div>

      {hasRole('approver') && (
        <Panel title="Review queue" subtitle={<span className="inline-flex items-center gap-1 text-[11px]"><ShieldCheck className="w-3.5 h-3.5" />pending approval</span>}>
          {pending === null ? (
            <p className="text-[13px] text-slate-400">Loading…</p>
          ) : pending.length === 0 ? (
            <p className="text-[13px] text-slate-400">Nothing pending review.</p>
          ) : (
            <div className="space-y-2">
              {pending.map(o => (
                <div key={o.id} className="flex items-center justify-between gap-3 border border-slate-200 rounded-sm p-2.5">
                  <div className="text-[12px]">
                    <span className="font-semibold text-slate-800">#{o.id}</span>
                    <span className="text-slate-500 ml-2">{o.operator} · {o.currency} {o.orig_rate} ({o.orig_year}) → {money(o.normalised_base, 2)}</span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => review(o.id, true)} disabled={reviewBusy === o.id}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-sm bg-accent text-white text-[11px] font-semibold disabled:opacity-40">
                      <CheckCircle2 className="w-3.5 h-3.5" />Approve
                    </button>
                    <button onClick={() => review(o.id, false)} disabled={reviewBusy === o.id}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-sm border border-slate-300 text-slate-600 text-[11px] font-semibold disabled:opacity-40">
                      <X className="w-3.5 h-3.5" />Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
