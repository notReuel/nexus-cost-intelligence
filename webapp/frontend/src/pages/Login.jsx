import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { LogIn, Loader2, AlertTriangle } from 'lucide-react';
import { authApi } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState('estimator@demo.io');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const data = await authApi.login(email, password);
      login(data);
      const dest = loc.state?.from || '/data';
      nav(dest, { replace: true });
    } catch (e) {
      setErr('Invalid email or password.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-sm mx-auto mt-16">
      <div className="text-center mb-6">
        <div className="w-10 h-10 bg-accent rounded-sm flex items-center justify-center font-bold text-white text-sm mx-auto mb-3">NX</div>
        <h1 className="text-lg font-bold text-slate-900">Sign in to NEPL NEXUS</h1>
        <p className="text-[13px] text-slate-500 mt-1">Cost Intelligence Platform</p>
      </div>
      <form onSubmit={submit} className="bg-white border border-slate-200 rounded-sm p-5 space-y-4">
        <div>
          <label htmlFor="login-email" className="block text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-1.5">Email</label>
          <input id="login-email" type="email" required value={email} onChange={e => setEmail(e.target.value)}
            className="w-full bg-[#F8FAFC] border border-slate-300 rounded-sm px-2.5 py-2 text-sm text-slate-900 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40" />
        </div>
        <div>
          <label htmlFor="login-password" className="block text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-1.5">Password</label>
          <input id="login-password" type="password" required value={password} onChange={e => setPassword(e.target.value)}
            className="w-full bg-[#F8FAFC] border border-slate-300 rounded-sm px-2.5 py-2 text-sm text-slate-900 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40" />
        </div>
        {err && <div role="alert" className="flex items-center gap-2 text-[12px] text-red-700 bg-red-50 rounded-sm p-2"><AlertTriangle className="w-4 h-4 shrink-0" />{err}</div>}
        <button type="submit" disabled={busy}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-sm bg-accent text-white font-semibold text-sm hover:bg-accent-glow disabled:opacity-40">
          {busy ? <><Loader2 className="w-4 h-4 animate-spin" />Signing in…</> : <><LogIn className="w-4 h-4" />Sign in</>}
        </button>
        <p className="text-[11px] text-slate-400 text-center pt-1">
          Demo: estimator@demo.io / changeme-estimator<br />or approver@demo.io / changeme-approver
        </p>
      </form>
    </div>
  );
}
