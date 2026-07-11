import { Lock } from 'lucide-react';
import { Panel } from '../components/Enterprise.jsx';

export default function ComingSoon({ title, body }) {
  return (
    <div className="max-w-xl">
      <Panel title={title}>
        <div className="flex items-start gap-3 py-2">
          <div className="w-9 h-9 rounded-sm bg-slate-100 flex items-center justify-center shrink-0"><Lock className="w-4 h-4 text-slate-600" /></div>
          <div>
            <div className="inline-flex items-center px-2 py-0.5 rounded-sm bg-slate-100 text-slate-600 text-[10px] font-semibold uppercase tracking-widest mb-2">Roadmap</div>
            <p className="text-[13px] text-slate-700 leading-relaxed">{body}</p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
