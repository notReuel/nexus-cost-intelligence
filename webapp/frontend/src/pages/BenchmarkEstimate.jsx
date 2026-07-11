import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Activity, Droplets } from 'lucide-react';
import { PageHeader } from '../components/UI.jsx';
import Pipeline from './Pipeline.jsx';
import WellAndCT from './WellAndCT.jsx';

/**
 * Discipline router for the "Run an estimate" sub-page.
 * URL: /benchmark/estimate?discipline=pipeline | well
 */
export default function BenchmarkEstimate() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = searchParams.get('discipline') === 'well' ? 'well' : 'pipeline';
  const [discipline, setDiscipline] = useState(initial);

  useEffect(() => {
    setSearchParams({ discipline }, { replace: true });
  }, [discipline, setSearchParams]);

  return (
    <div className="space-y-6">
      <PageHeader
        Icon={discipline === 'well' ? Droplets : Activity}
        eyebrow="Benchmark service · Run an estimate"
        title={discipline === 'well' ? 'Well services & coiled tubing' : 'Pipeline construction'}
        subtitle={
          discipline === 'well'
            ? 'Estimate drilling AFEs or coiled tubing campaigns using the NNPC tender benchmark.'
            : 'Estimate pipeline construction cost using the NNPC scope-class engine across 5 operators.'
        }
      />

      {/* Discipline toggle */}
      <div className="flex gap-1 border-b border-slate-700">
        <DiscButton active={discipline === 'pipeline'} onClick={() => setDiscipline('pipeline')} Icon={Activity}>
          Pipeline construction
        </DiscButton>
        <DiscButton active={discipline === 'well'} onClick={() => setDiscipline('well')} Icon={Droplets}>
          Well services / coiled tubing
        </DiscButton>
      </div>

      <div>
        {discipline === 'pipeline' ? <Pipeline hideHeader /> : <WellAndCT />}
      </div>
    </div>
  );
}

function DiscButton({ active, onClick, Icon, children }) {
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
