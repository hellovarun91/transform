import { renderToday } from './views/today.js';
import { renderPlan } from './views/plan.js';
import { renderWeight } from './views/weight.js';
import { renderHistory } from './views/history.js';
import { renderSettings } from './views/settings.js';

const TOKEN_KEY = 'tf_token';
const QUEUE_KEY = 'tf_queue';

export const state = { token: localStorage.getItem(TOKEN_KEY) };

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function todayISO() {
  const n = new Date();
  const ist = new Date(n.getTime() + (330 + n.getTimezoneOffset()) * 60000);
  return ist.toISOString().slice(0, 10);
}

export function fmtDate(iso, opts = { weekday: 'short', day: 'numeric', month: 'short' }) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', opts);
}

export function addDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(y, m - 1, d + n);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
}

let toastTimer;
export function toast(msg, ms = 2200) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add('hidden'), ms);
}

export class QueuedError extends Error {}

function readQueue() { try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); } catch { return []; } }
function writeQueue(q) { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); }

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {
    if (method === 'PUT') {
      const q = readQueue(); q.push({ path, body, ts: Date.now() }); writeQueue(q);
      toast('Offline — saved, will sync');
      throw new QueuedError('queued');
    }
    throw e;
  }
  if (res.status === 401) { logout(); throw new Error('unauthorised'); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    if (typeof detail !== 'string') detail = JSON.stringify(detail);
    throw new Error(detail);
  }
  return res.json();
}

export async function flushQueue() {
  const q = readQueue();
  if (!q.length || !navigator.onLine) return;
  writeQueue([]);
  for (const item of q) {
    try { await api(item.path, { method: 'PUT', body: item.body }); }
    catch (e) { if (!(e instanceof QueuedError)) console.warn('dropped queued write', item, e.message); }
  }
  if (!readQueue().length) { toast(`Synced ${q.length} change${q.length > 1 ? 's' : ''}`); render(); }
}

export function logout() {
  state.token = null; localStorage.removeItem(TOKEN_KEY);
  document.getElementById('login').classList.remove('hidden');
}

export function navigate(hash) { location.hash = hash; }

const routes = { today: renderToday, plan: renderPlan, weight: renderWeight, history: renderHistory, settings: renderSettings };

export async function render() {
  if (!state.token) { document.getElementById('login').classList.remove('hidden'); return; }
  const [route, ...rest] = (location.hash.slice(1) || 'today').split('/');
  const fn = routes[route] || renderToday;
  document.querySelectorAll('#tabs a').forEach(a => a.classList.toggle('active', a.dataset.route === (routes[route] ? route : 'today')));
  const root = document.getElementById('view');
  root.innerHTML = '<p class="muted">Loading…</p>';
  try { await fn(root, { param: rest.join('/') }); }
  catch (e) { if (!(e instanceof QueuedError)) root.innerHTML = `<div class="alert bad">${e.message}</div>`; }
}

document.getElementById('loginForm').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const pin = document.getElementById('pin').value;
  const err = document.getElementById('loginErr');
  err.textContent = '';
  try {
    const r = await fetch('/api/auth', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin }) });
    if (!r.ok) { err.textContent = r.status === 429 ? 'Too many attempts. Wait 15 min.' : 'Wrong PIN'; return; }
    state.token = (await r.json()).token; localStorage.setItem(TOKEN_KEY, state.token);
    document.getElementById('login').classList.add('hidden'); document.getElementById('pin').value = '';
    render();
  } catch { err.textContent = 'Network error'; }
});

window.addEventListener('hashchange', render);
window.addEventListener('online', flushQueue);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { flushQueue(); render(); } });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
flushQueue().finally(render);
