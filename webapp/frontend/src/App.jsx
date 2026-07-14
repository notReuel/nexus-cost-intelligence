import { Routes, Route, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import {
  Home as HomeIcon, SlidersHorizontal, Table2, BarChart3, Database,
  LineChart, FileDown, Lock, Wrench, ShieldCheck, Menu, X,
  PanelLeftClose, PanelLeftOpen, LogOut,
} from 'lucide-react';

import Home from './pages/Home.jsx';
import ProjectModeller from './pages/ProjectModeller.jsx';
import Budget from './pages/Budget.jsx';
import BidIntake from './pages/BidIntake.jsx';
import DataEntry from './pages/DataEntry.jsx';
import Login from './pages/Login.jsx';
import Catalogue from './pages/Catalogue.jsx';
import Export from './pages/Export.jsx';
import ComingSoon from './pages/ComingSoon.jsx';
import { AuthProvider, useAuth } from './lib/auth.jsx';

const NAV = [
  { to: '/', label: 'Home', Icon: HomeIcon },
  { section: 'Estimating' },
  { to: '/model', label: 'Project Model', Icon: SlidersHorizontal },
  { to: '/budget', label: 'Line-item Budget', Icon: Table2 },
  { section: 'Procurement' },
  { to: '/bids', label: 'Cost Benchmarking & Ranking', Icon: BarChart3 },
  { section: 'Data' },
  { to: '/catalogue', label: 'Catalogue', Icon: Database },
  { to: '/data', label: 'Data Entry', Icon: Database },
  { to: '/intelligence', label: 'Cost Intelligence', Icon: LineChart, locked: true },
  { section: 'Roadmap' },
  { to: '/well-services', label: 'Well Services / CT', Icon: Wrench, locked: true },
  { to: '/verification', label: 'Vendor Verification', Icon: ShieldCheck, locked: true },
  { section: null },
  { to: '/export', label: 'Export', Icon: FileDown },
];

function Rail({ open, onClose, collapsed, onToggleCollapse }) {
  const w = collapsed ? 'w-16' : 'w-60';
  return (
    <aside className={`fixed lg:sticky top-0 z-40 h-screen ${w} shrink-0 bg-white border-r border-slate-200 flex flex-col transition-all duration-200 ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
      <div className="h-14 flex items-center gap-2.5 px-3 border-b border-slate-200">
        <div className="w-8 h-8 bg-accent rounded-sm flex items-center justify-center font-bold text-white text-[13px] shrink-0">NX</div>
        {!collapsed && (
          <div className="leading-tight min-w-0">
            <div className="text-[14px] font-bold text-slate-900 tracking-tight">NEPL NEXUS</div>
            <div className="text-[9px] uppercase tracking-[0.18em] text-accent">Cost Intelligence</div>
          </div>
        )}
        <button onClick={onClose} className="ml-auto lg:hidden text-slate-400"><X className="w-4 h-4" /></button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2 px-2">
        {NAV.map((item, i) => {
          if ('section' in item) {
            if (collapsed) return item.section === null ? <div key={i} className="my-2 border-t border-slate-200" /> : <div key={i} className="my-1.5" />;
            return item.section
              ? <div key={i} className="px-2 pt-4 pb-1 text-[9px] font-bold uppercase tracking-widest text-slate-400">{item.section}</div>
              : <div key={i} className="my-2 border-t border-slate-200" />;
          }
          if (item.locked) {
            return (
              <div key={item.to} title={item.label + ' — coming soon'} className={`flex items-center gap-2.5 px-2.5 py-2 rounded-sm text-[13px] text-slate-400 cursor-not-allowed select-none ${collapsed ? 'justify-center' : ''}`}>
                <item.Icon className="w-4 h-4 shrink-0" />
                {!collapsed && <><span className="truncate">{item.label}</span><Lock className="w-3 h-3 ml-auto shrink-0" /></>}
              </div>
            );
          }
          return (
            <NavLink key={item.to} to={item.to} end={item.to === '/'} onClick={onClose} title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-2.5 py-2 rounded-sm text-[13px] transition-colors ${collapsed ? 'justify-center' : ''} ${isActive ? 'bg-accent-light text-accent-dim font-semibold' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
              <item.Icon className="w-4 h-4 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-slate-200 p-2">
        <button onClick={onToggleCollapse} className={`hidden lg:flex items-center gap-2.5 w-full px-2.5 py-2 rounded-sm text-[12px] text-slate-500 hover:bg-slate-100 hover:text-slate-800 ${collapsed ? 'justify-center' : ''}`}>
          {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <><PanelLeftClose className="w-4 h-4" /><span>Collapse</span></>}
        </button>
        {!collapsed && <div className="px-2.5 pt-2 text-[10px] text-slate-400"><span className="font-mono">v5.0</span> · Swamp Lay &amp; Weld</div>}
      </div>
    </aside>
  );
}

function AppShell() {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('ncmp:rail_collapsed') === '1');
  useEffect(() => { localStorage.setItem('ncmp:rail_collapsed', collapsed ? '1' : '0'); }, [collapsed]);
  const loc = useLocation();
  const title = NAV.find(n => n.to === loc.pathname)?.label || '';
  return (
    <div className="min-h-screen flex bg-[#F8FAFC] text-slate-800">
      {open && <div className="fixed inset-0 bg-slate-900/30 z-30 lg:hidden" onClick={() => setOpen(false)} />}
      <Rail open={open} onClose={() => setOpen(false)} collapsed={collapsed} onToggleCollapse={() => setCollapsed(c => !c)} />
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 sticky top-0 z-20 bg-white/95 backdrop-blur border-b border-slate-200 flex items-center gap-3 px-4">
          <button onClick={() => setOpen(true)} className="lg:hidden text-slate-500"><Menu className="w-5 h-5" /></button>
          <span className="text-[13px] font-semibold text-slate-900">{title}</span>
          <div className="ml-auto flex items-center gap-3 text-[11px] text-slate-500">
            <span className="hidden sm:inline">USD 2024 real</span>
            <span className="hidden md:inline px-2 py-0.5 rounded-sm bg-slate-100 border border-slate-200">4 operators · 440 obs</span>
            <AccountChip />
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6 max-w-[1400px] w-full mx-auto">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/model" element={<ProjectModeller />} />
            <Route path="/budget" element={<Budget />} />
            <Route path="/bids" element={<BidIntake />} />
            <Route path="/catalogue" element={<Catalogue />} />
            <Route path="/data" element={<DataEntry />} />
            <Route path="/login" element={<Login />} />
            <Route path="/intelligence" element={<ComingSoon title="Cost Intelligence" body="The third pillar — cross-operator cost trends, escalation curves and outlier detection — is in development. It builds on the same observation base you're growing through Data Entry." />} />
            <Route path="/export" element={<Export />} />
            <Route path="/well-services" element={<ComingSoon title="Well Services / Coiled Tubing" body="Well and CT benchmarking is on the roadmap. It needs a second operator's well AFE and cross-tender CT data before it can be defended at operator grade." />} />
            <Route path="/verification" element={<ComingSoon title="Vendor Verification" body="PEP screening and vendor KYC require a licensed data-provider integration. This unlocks once that provider is contracted." />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function AccountChip() {
  const { auth, logout } = useAuth();
  const nav = useNavigate();
  if (!auth) {
    return (
      <button onClick={() => nav('/login')} className="px-2 py-0.5 rounded-sm bg-accent text-white font-semibold">Sign in</button>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <span className="px-2 py-0.5 rounded-sm bg-accent-light text-accent-dim font-semibold">{auth.name} · {auth.role}</span>
      <button onClick={logout} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-sm border border-slate-300 text-slate-600 hover:border-red-400 hover:text-red-600 font-semibold">
        <LogOut className="w-3.5 h-3.5" />Sign out
      </button>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
