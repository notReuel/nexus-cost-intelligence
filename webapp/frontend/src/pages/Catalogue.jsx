import { useEffect, useState, useMemo } from 'react';
import { BookOpen, Search, X, ChevronRight, Database, Layers } from 'lucide-react';
import { api, fmt } from '../lib/api.js';
import { PageHeader, SectionHeader, Card, SourceNote } from '../components/UI.jsx';

const CATEGORY_DESCRIPTIONS = {
  'Materials':            'Pipe coatings, HDD crossings, split sleeves (clamps), line crossings, painting & surface treatment.',
  'Construction':         'Lay & weld, welding (per joint), field joint coating, tie-ins, repairs, post-weld heat treatment, pipe supports.',
  'NDT & Integrity':      'Radiography, dye penetrant testing (DPT), magnetic particle inspection (MPI).',
  'Mechanical Completion':'Hydrotesting, pigging, flushing, dewatering, pre-commissioning.',
  'Civil':                'Excavation, ROW clearing, trenching, backfilling.',
  'Mobilisation':         'Mob, demob, CASHES, security.',
  'Equipment':            'Per-item equipment day rates — barges, cranes, tugboats, swamp buggies, welding machines.',
  'Personnel':            'Per-role day rates — welders, site engineers, supervisors, labour.',
  'Logistics':            'Pipe collection, transport, handling.',
};

export default function Catalogue() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState(0);

  // Filters
  const [category, setCategory] = useState('');
  const [subCategory, setSubCategory] = useState('');
  const [confidence, setConfidence] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 25;

  // Selected detail
  const [detail, setDetail] = useState(null);

  // Load summary once
  useEffect(() => {
    api.catalogueSummary().then(setSummary).catch(console.error);
  }, []);

  // Re-query when filters change
  useEffect(() => {
    setItems(null);
    api.catalogueItems({
      category: category || undefined,
      sub_category: subCategory || undefined,
      confidence: confidence || undefined,
      search: search.trim() || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }).then(d => {
      setItems(d.items);
      setTotal(d.total);
    }).catch(console.error);
  }, [category, subCategory, confidence, search, page]);

  // Reset to page 0 when filters change (but not when page itself changes)
  useEffect(() => { setPage(0); }, [category, subCategory, confidence, search]);

  const subCategories = useMemo(() => {
    if (!summary || !category) return [];
    return summary.sub_categories_by_category[category] || [];
  }, [summary, category]);

  const clearFilters = () => {
    setCategory(''); setSubCategory(''); setConfidence(''); setSearch('');
  };
  const hasFilters = category || subCategory || confidence || search;

  return (
    <div className="space-y-8">
      <PageHeader
        Icon={BookOpen}
        eyebrow="Phase 1A · Line item library"
        title="Benchmark Catalogue"
        subtitle="Every pipeline line item the dataset has, normalised to USD 2024 real terms. Materials, Construction, NDT & Integrity, Mechanical Completion, Civil, Mobilisation, Equipment, Personnel, Logistics — with source attribution, page references, and confidence ratings."
      />

      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile
            num={summary.meta.total_items}
            label="Catalogued items"
            sub={`Aggregated from ${summary.meta.records_aggregated} raw records`}
          />
          <StatTile
            num={summary.categories.length}
            label="Categories"
            sub={`Across ${summary.units.length} units of measure`}
          />
          <StatTile
            num={summary.meta.by_confidence?.HIGH || 0}
            label="HIGH confidence"
            sub={`+ ${summary.meta.by_confidence?.MEDIUM || 0} medium · ${summary.meta.by_confidence?.LOW || 0} low`}
            colour="emerald"
          />
          <StatTile
            num={summary.operators.length}
            label="Operators in source"
            sub={summary.operators.join(' · ')}
          />
        </div>
      )}

      {/* Category pills */}
      {summary && !category && (
        <div>
          <SectionHeader label="Browse by category" />
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {summary.categories.map(cat => {
              const count = summary.meta.by_category?.[cat]?.count || 0;
              return (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  className="text-left p-5 rounded-sm bg-bg-panel border border-slate-700/50 hover:border-amber/50 transition-colors group"
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="text-base font-bold text-slate-100">{cat}</h3>
                    <span className="text-xs font-mono text-amber bg-amber/10 px-2 py-0.5 rounded-sm">{count}</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {CATEGORY_DESCRIPTIONS[cat] || ''}
                  </p>
                  <div className="mt-3 text-xs text-amber font-bold uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                    Browse <ChevronRight className="w-3 h-3" />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Active filters + search */}
      {(category || summary) && (
        <Card className="p-5">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search items (e.g. weld, swamp, NDT, transport)"
                className="w-full bg-bg-dark border border-slate-700 rounded-sm pl-10 pr-3 py-2 text-sm text-slate-100 focus:border-amber focus:outline-none"
              />
            </div>

            <FilterPill label="Category" value={category} onClear={() => setCategory('')}
                       options={summary?.categories || []} onChange={setCategory} />
            {category && (
              <FilterPill label="Sub-category" value={subCategory} onClear={() => setSubCategory('')}
                         options={subCategories} onChange={setSubCategory} />
            )}
            <FilterPill label="Confidence" value={confidence} onClear={() => setConfidence('')}
                       options={['HIGH', 'MEDIUM', 'LOW']} onChange={setConfidence} />

            {hasFilters && (
              <button onClick={clearFilters}
                className="text-xs uppercase tracking-wider text-slate-400 hover:text-amber px-2 py-1">
                Clear all
              </button>
            )}
          </div>
          <div className="mt-3 text-xs text-slate-500">
            {items === null ? 'Searching…' : `${total} item${total === 1 ? '' : 's'} match`}
          </div>
        </Card>
      )}

      {/* Items list */}
      {items && items.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-bg-dark">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Item</th>
                <th className="text-left px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Unit</th>
                <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Low</th>
                <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-amber font-semibold">Mid</th>
                <th className="text-right px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">High</th>
                <th className="text-center px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Sources</th>
                <th className="text-center px-4 py-2.5 text-xs uppercase tracking-wider text-slate-400 font-semibold">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.id}
                    onClick={() => setDetail(it)}
                    className="border-t border-slate-700/30 hover:bg-bg-panel/70 transition-colors cursor-pointer">
                  <td className="px-4 py-2.5">
                    <div className="text-slate-100 font-medium">{it.item}</div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {it.category} → {it.sub_category} <span className="text-slate-600">· {it.id}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 text-[13px]">{it.unit}</td>
                  <td className="px-4 py-2.5 text-right num-tabular text-slate-300">{fmtRate(it.low, it.unit)}</td>
                  <td className="px-4 py-2.5 text-right num-tabular text-amber font-semibold">{fmtRate(it.mid, it.unit)}</td>
                  <td className="px-4 py-2.5 text-right num-tabular text-slate-300">{fmtRate(it.high, it.unit)}</td>
                  <td className="px-4 py-2.5 text-center text-[13px] text-slate-400">{it.n_records}</td>
                  <td className="px-4 py-2.5 text-center">
                    <ConfBadge confidence={it.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {items && items.length === 0 && (
        <Card className="p-12 text-center">
          <Search className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No items match the current filters.</p>
        </Card>
      )}

      {/* Pagination */}
      {items && total > PAGE_SIZE && (
        <div className="flex justify-between items-center text-sm text-slate-400">
          <div>
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 rounded-sm border border-slate-700 hover:bg-bg-panel disabled:opacity-40 disabled:cursor-not-allowed">
              Previous
            </button>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={(page + 1) * PAGE_SIZE >= total}
              className="px-3 py-1.5 rounded-sm border border-slate-700 hover:bg-bg-panel disabled:opacity-40 disabled:cursor-not-allowed">
              Next
            </button>
          </div>
        </div>
      )}

      <SourceNote>
        All benchmarks normalised to USD 2024 real terms using year-by-year CBN FX and US PPI-FG inflation indices.
        Confidence: HIGH = 3+ source records, MEDIUM = 2 sources, LOW = single source.
        Outliers and flagged data quality issues are excluded from the catalogue.
      </SourceNote>

      {detail && <DetailModal item={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

// ─── Filter pill component ────────────────────────────────────────────
function FilterPill({ label, value, options, onChange, onClear }) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none bg-bg-dark border border-slate-700 rounded-sm pl-3 pr-8 py-1.5 text-xs text-slate-100 focus:border-amber focus:outline-none cursor-pointer">
        <option value="">{label}: All</option>
        {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
      </select>
      {value && (
        <button
          onClick={onClear}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-amber">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

// ─── Stat tile ────────────────────────────────────────────────────────
function StatTile({ num, label, sub, colour = 'amber' }) {
  const colourMap = {
    amber: 'text-amber',
    emerald: 'text-emerald-400',
    rose: 'text-rose-400',
  };
  return (
    <Card className="p-5">
      <div className={`text-3xl md:text-4xl font-bold ${colourMap[colour]} num-tabular leading-none mb-2`}>{num}</div>
      <div className="text-sm font-semibold text-slate-200 mb-1">{label}</div>
      <div className="text-xs text-slate-500 leading-snug">{sub}</div>
    </Card>
  );
}

function ConfBadge({ confidence }) {
  const map = {
    HIGH:   'bg-emerald-50 text-emerald-600 border-emerald-400/40',
    MEDIUM: 'bg-amber/15 text-amber border-amber/40',
    LOW:    'bg-rose-500/15 text-rose-300 border-rose-400/40',
  };
  return (
    <span className={`inline-block px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded-sm ${map[confidence] || ''}`}>
      {confidence}
    </span>
  );
}

// ─── Detail modal ─────────────────────────────────────────────────────
function DetailModal({ item, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
         onClick={onClose}>
      <div className="bg-bg-panel border border-slate-700 rounded-sm max-w-3xl w-full max-h-[90vh] overflow-y-auto"
           onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-bg-panel border-b border-slate-700 px-6 py-4 flex justify-between items-start">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-amber mb-1">{item.category} → {item.sub_category} · {item.id}</div>
            <h2 className="text-xl font-bold text-slate-100">{item.item}</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-amber p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Cost band */}
          <div className="grid grid-cols-3 gap-px bg-slate-700/50 rounded-sm overflow-hidden">
            <div className="bg-bg-dark p-4 text-center">
              <div className="text-[10px] uppercase text-slate-500 mb-1">Low</div>
              <div className="text-xl font-bold text-slate-200 num-tabular">{fmtRate(item.low, item.unit)}</div>
            </div>
            <div className="bg-amber/10 p-4 text-center">
              <div className="text-[10px] uppercase text-amber font-bold mb-1">Mid</div>
              <div className="text-xl font-bold text-amber num-tabular">{fmtRate(item.mid, item.unit)}</div>
            </div>
            <div className="bg-bg-dark p-4 text-center">
              <div className="text-[10px] uppercase text-slate-500 mb-1">High</div>
              <div className="text-xl font-bold text-slate-200 num-tabular">{fmtRate(item.high, item.unit)}</div>
            </div>
          </div>

          {/* Metadata grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
            <KV k="Discipline" v={item.discipline || 'Pipeline'} />
            <KV k="Unit" v={item.unit} />
            <KV k="Median" v={fmtRate(item.median, item.unit)} />
            <KV k="Sources" v={item.n_records} />
            {item.spec?.dia != null && <KV k="Diameter" v={item.spec.dia} />}
            {item.spec?.sched && <KV k="Schedule" v={item.spec.sched} />}
            {item.spec?.terrain && <KV k="Terrain" v={item.spec.terrain} />}
            {item.material_grade && <KV k="Material grade" v={item.material_grade} />}
            <KV k="Confidence" v={<ConfBadge confidence={item.confidence} />} />
            <KV k="Year range" v={item.year_range || '—'} />
          </div>

          {/* Operators */}
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-500 mb-2">Operators in benchmark</div>
            <div className="flex flex-wrap gap-2">
              {item.operators.map(op => (
                <span key={op} className="text-xs bg-bg-dark border border-slate-700 rounded-sm px-2 py-1 text-slate-300">{op}</span>
              ))}
            </div>
          </div>

          {/* Source documents */}
          {item.source_documents && item.source_documents.length > 0 && (
            <div>
              <div className="text-xs uppercase tracking-wider text-slate-500 mb-2">Source documents</div>
              <div className="space-y-1">
                {item.source_documents.map((doc, i) => (
                  <div key={i} className="text-xs text-slate-400 font-mono leading-relaxed">
                    {doc}
                    {item.source_pages && item.source_pages.length > 0 && i === 0 && (
                      <span className="text-slate-600"> · p.{item.source_pages.join(', p.')}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Source record IDs */}
          {item.source_refs && (
            <div>
              <div className="text-xs uppercase tracking-wider text-slate-500 mb-2">Source record IDs</div>
              <div className="text-xs text-slate-500 font-mono">{item.source_refs.join(' · ')}</div>
            </div>
          )}

          {/* Notes */}
          {item.notes && (
            <div className="text-xs italic text-slate-400 border-l-2 border-amber/40 pl-3">{item.notes}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">{k}</div>
      <div className="text-slate-200">{v}</div>
    </div>
  );
}

// Smart rate formatter — picks $X.XX for small numbers, $X for large
function fmtRate(n, unit) {
  if (n == null || isNaN(n)) return '—';
  if (Math.abs(n) >= 10000) return `$${(n/1000).toFixed(1)}k`;
  if (Math.abs(n) >= 100)   return `$${n.toFixed(0)}`;
  return `$${n.toFixed(2)}`;
}
