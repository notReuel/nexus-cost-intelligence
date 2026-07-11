import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Droplets, Wrench } from 'lucide-react';
import { PageHeader, Card } from '../components/UI.jsx';
import Well from './Well.jsx';
import CT from './CT.jsx';

/**
 * Unified Well Services & Coiled Tubing estimator.
 * Sub-mode toggle: "Drilling AFE" (Well) | "CT Campaign" (CT)
 *
 * The underlying engines are unchanged — this is a presentation layer.
 */
export default function WellAndCT() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = searchParams.get('mode') === 'ct' ? 'ct' : 'well';
  const [mode, setMode] = useState(initial);

  useEffect(() => {
    setSearchParams(mode === 'ct' ? { mode: 'ct' } : {}, { replace: true });
  }, [mode, setSearchParams]);

  return (
    <div className="space-y-6">
      <PageHeader
        Icon={mode === 'ct' ? Wrench : Droplets}
        eyebrow="Discipline · Well services & coiled tubing"
        title={mode === 'ct' ? 'Coiled Tubing Campaign' : 'Drilling AFE'}
        subtitle={
          mode === 'ct'
            ? '11-vendor Seplat 2024 + 6-vendor NAOC 2021 cross-tender benchmark. Reference-tender-aware.'
            : '7-phase AFE build-up: pre-spud, rig move, 16″ / 12¼″ / 8½″ sections, testing, completions.'
        }
      />

      {/* Sub-mode toggle */}
      <div className="flex gap-1 border-b border-slate-700">
        <ModeButton active={mode === 'well'} onClick={() => setMode('well')} Icon={Droplets}>
          Drilling AFE
        </ModeButton>
        <ModeButton active={mode === 'ct'} onClick={() => setMode('ct')} Icon={Wrench}>
          CT Campaign
        </ModeButton>
      </div>

      {/* Render the inner estimator — we strip its own PageHeader by passing hideHeader */}
      <div>
        {mode === 'well' ? <Well hideHeader /> : <CT hideHeader />}
      </div>
    </div>
  );
}

function ModeButton({ active, onClick, Icon, children }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
        active
          ? 'border-amber text-amber'
          : 'border-transparent text-slate-400 hover:text-slate-200'
      }`}
    >
      <Icon className="w-4 h-4" />
      {children}
    </button>
  );
}
