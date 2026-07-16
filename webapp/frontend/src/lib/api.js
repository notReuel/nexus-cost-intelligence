// Lightweight API client — talks to FastAPI backend
// VITE_API_URL is the backend origin (Railway in production).
// In dev/preview, defaults to localhost. The `/api` prefix is added here so
// the API path stays consistent regardless of where the backend is hosted.

const ORIGIN =
  import.meta.env.VITE_API_URL || 'http://localhost:8765';
const API_BASE = ORIGIN.replace(/\/$/, '') + '/api';

async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return await res.json();
}

async function get(path, params) {
  let url = `${API_BASE}${path}`;
  if (params && Object.keys(params).length) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    }
    const q = qs.toString();
    if (q) url += '?' + q;
  }
  const res = await fetch(url);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return await res.json();
}

async function postAuthed(path, body, token) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return await res.json();
}

async function getAuthed(path, params, token) {
  let url = `${API_BASE}${path}`;
  if (params && Object.keys(params).length) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    }
    const q = qs.toString();
    if (q) url += '?' + q;
  }
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return await res.json();
}

export const authApi = {
  login: (email, password) => post('/v2/auth/login', { email, password }),
  me: (token) => getAuthed('/v2/auth/me', {}, token),
  benchmarks: (token, params) => getAuthed('/v2/benchmarks', params, token),
  submitObservation: (token, body) => postAuthed('/v2/observations', body, token),
  pendingObservations: (token, params) => getAuthed('/v2/observations/pending', params, token),
  review: (token, obsId, approve) => postAuthed(`/v2/observations/${obsId}/review`, { approve }, token),
};

export const api = {
  metadata: () => get('/metadata'),
  options:  () => get('/options'),
  estimatePipeline: (inp) => post('/estimate/pipeline', inp),
  estimateWell:     (inp) => post('/estimate/well', inp),
  estimateCT:       (inp) => post('/estimate/ct', inp),
  checkQuote:       (inp) => post('/qc/check', inp),
  findings:         () => get('/intelligence/findings'),
  ctCrossTender:    () => get('/intelligence/ct-cross-tender'),
  coverage:         () => get('/intelligence/coverage'),
  // Catalogue (Phase 1A)
  catalogueSummary: () => get('/catalogue/summary'),
  catalogueItems:   (filters) => get('/catalogue/items', filters),
  catalogueItem:    (id) => get(`/catalogue/items/${id}`),

  // Tender upload (Phase 1B)
  tenderUpload: async (file, projectName, vendorName) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('project_name', projectName || '');
    fd.append('vendor_name', vendorName || '');
    const res = await fetch(`${API_BASE}/tender/upload`, { method: 'POST', body: fd });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`${res.status}: ${txt}`);
    }
    return await res.json();
  },

  // v5: Project Modeller / Budget (compute-only, no persistence — not a write path).
  // Public by design — but if a token is supplied, the backend blends in
  // the caller's own tenant data alongside the shared reference library.
  modelProject:   (scope, token) => postAuthed('/model/project', scope, token),
  generateBudget: (scope, token) => postAuthed('/model/generate-budget', scope, token),

  // Bid comparison (multi-vendor)
  bidComparison: async (files, projectName) => {
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    fd.append('project_name', projectName || '');
    const res = await fetch(`${API_BASE}/bid-comparison`, { method: 'POST', body: fd });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`${res.status}: ${txt}`);
    }
    return await res.json();
  },
};

// ─── Formatters ─────────────────────────────────────────────────────────
export const fmt = {
  usd: (n) => {
    if (n == null || isNaN(n)) return '—';
    if (Math.abs(n) >= 1e6) return `$${(n/1e6).toFixed(2)}M`;
    if (Math.abs(n) >= 1e3) return `$${(n/1e3).toFixed(0)}k`;
    return `$${n.toFixed(0)}`;
  },
  usdFull: (n) => {
    if (n == null || isNaN(n)) return '—';
    return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
  },
  usd2: (n) => {
    if (n == null || isNaN(n)) return '—';
    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  },
  pct: (n) => {
    if (n == null || isNaN(n)) return '—';
    const v = n * 100;
    return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
  },
  pct0: (n) => `${(n * 100).toFixed(0)}%`,
};
