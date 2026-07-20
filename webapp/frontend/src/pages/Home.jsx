import { Link } from 'react-router-dom';
import { SlidersHorizontal, BarChart3, LineChart, ArrowRight, Lock, UploadCloud } from 'lucide-react';

const CARDS = [
  { to: '/model', Icon: SlidersHorizontal, title: 'Project Model',
    body: 'Model a pipeline cost from real data.' },
  { to: '/tender', Icon: UploadCloud, title: 'Vendor Bid Check',
    body: 'Upload one vendor BOQ and benchmark it directly — no project model needed.' },
  { to: '/bids', Icon: BarChart3, title: 'Cost Benchmarking & Ranking',
    body: 'Check and rank vendor bids.' },
  { to: null, Icon: LineChart, title: 'Cost Intelligence', locked: true,
    body: 'Cost trends and outliers.' },
];

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-accent mb-1.5">NEPL NEXUS</div>
        <h1 className="text-2xl font-bold text-slate-900">Cost Intelligence for Upstream Pipelines</h1>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CARDS.map(c => {
          const inner = (
            <>
              <div className="flex items-center justify-between mb-3">
                <div className={`w-10 h-10 rounded-sm flex items-center justify-center ${c.locked ? 'bg-slate-100' : 'bg-accent-light'}`}>
                  <c.Icon className={`w-5 h-5 ${c.locked ? 'text-slate-400' : 'text-accent'}`} />
                </div>
                {c.locked
                  ? <Lock className="w-4 h-4 text-slate-300" />
                  : <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-accent transition-colors" />}
              </div>
              <div className="flex items-center gap-2">
                <h2 className={`text-[15px] font-semibold ${c.locked ? 'text-slate-400' : 'text-slate-900'}`}>{c.title}</h2>
                {c.locked && <span className="text-[9px] font-semibold uppercase tracking-widest text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded-sm">Soon</span>}
              </div>
              <p className={`text-[12.5px] mt-1.5 ${c.locked ? 'text-slate-400' : 'text-slate-500'}`}>{c.body}</p>
            </>
          );
          const cls = `block rounded-sm border p-5 transition-all ${c.locked ? 'border-slate-200 bg-slate-50/50 cursor-not-allowed select-none' : 'group border-slate-200 bg-white hover:border-accent/40 hover:shadow-sm'}`;
          return c.locked
            ? <div key={c.title} className={cls} title="In development">{inner}</div>
            : <Link key={c.title} to={c.to} className={cls}>{inner}</Link>;
        })}
      </div>
    </div>
  );
}
