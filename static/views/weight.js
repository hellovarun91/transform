import { api, h, toast, todayISO, fmtDate, QueuedError } from '../app.js';

export async function renderWeight(root) {
  const w = await api('/api/weight');
  root.innerHTML = '';
  const today = todayISO();
  const todayPt = w.series.find(s => s.date === today);
  const inp = h('input', { type: 'number', step: '0.1', inputmode: 'decimal', placeholder: 'kg this morning', value: todayPt ? todayPt.kg : '' });
  root.append(h('h1', {}, 'Weight'));
  root.append(h('div', { class: 'card row' }, inp, h('button', { class: 'btn primary', onclick: async () => {
    const kg = parseFloat(inp.value); if (!kg) return;
    try { await api('/api/weight', { method: 'PUT', body: { date: today, kg } }); toast('Saved'); renderWeight(root); } catch (e) { if (!(e instanceof QueuedError)) toast(e.message); }
  } }, 'Save')));

  const last = w.ma7.at(-1), latest = w.series.at(-1);
  const band = w.corridor.find(c => c.date === today);
  const status = !band || !last ? 'no data' : last.kg > band.hi ? 'behind' : last.kg < band.lo ? 'ahead' : 'on pace';
  root.append(h('div', { class: 'card kpi' },
    h('div', {}, h('b', {}, latest ? latest.kg : '—'), h('span', {}, 'latest')),
    h('div', {}, h('b', {}, last ? last.kg.toFixed(1) : '—'), h('span', {}, '7-day avg')),
    h('div', {}, h('b', {}, band ? band.mid.toFixed(1) : '—'), h('span', {}, 'target today'))));
  root.append(h('div', { class: `alert ${status === 'behind' ? 'bad' : status === 'ahead' ? 'info' : 'warn'}` },
    `${status.toUpperCase()} · goal ${w.goal} kg · ${w.projection ? 'projected ' + fmtDate(w.projection, { day: 'numeric', month: 'short', year: 'numeric' }) : 'need more weigh-ins for a projection'}`));
  if (w.checkpoint_flag) root.append(h('div', { class: 'alert bad' }, `CHECKPOINT MISSED · ${fmtDate(w.checkpoint_flag.date)} target ${w.checkpoint_flag.target} kg, 7-day avg ${w.checkpoint_flag.ma7.toFixed(1)} kg (${w.checkpoint_flag.over_by.toFixed(1)} kg over the corridor). Tighten meals this week.`));
  if (today < w.creatine_loading_until) root.append(h('div', { class: 'alert info' }, 'Creatine loading: expect +1–1.5 kg of water for two weeks. Not fat.'));
  root.append(h('div', { class: 'card' }, chart(w)));
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Checkpoints'), ...w.checkpoints.map(c => h('div', { class: 'row between detail' }, h('span', {}, fmtDate(c.date, { day: 'numeric', month: 'short', year: 'numeric' })), h('span', {}, `${c.kg} kg`)))));
}

function chart(w) {
  const W = 600, H = 240, L = 36, R = 8, T = 10, B = 24;
  const dates = [...new Set([...w.corridor.map(c => c.date), ...w.series.map(s => s.date)])].sort();
  if (!dates.length) return h('p', { class: 'muted' }, 'No data yet');
  const d0 = new Date(dates[0]), d1 = new Date(dates.at(-1));
  const span = Math.max(1, (d1 - d0) / 86400000);
  const ys = [...w.corridor.flatMap(c => [c.lo, c.hi]), ...w.series.map(s => s.kg), w.goal];
  const yMin = Math.floor(Math.min(...ys) - 1), yMax = Math.ceil(Math.max(...ys) + 1);
  const x = iso => L + ((new Date(iso) - d0) / 86400000) / span * (W - L - R);
  const y = kg => T + (yMax - kg) / (yMax - yMin) * (H - T - B);
  const path = pts => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.date).toFixed(1)},${y(p.kg).toFixed(1)}`).join(' ');
  const corridor = w.corridor.length ? `M${w.corridor.map(c => `${x(c.date).toFixed(1)},${y(c.hi).toFixed(1)}`).join(' L')} L${[...w.corridor].reverse().map(c => `${x(c.date).toFixed(1)},${y(c.lo).toFixed(1)}`).join(' L')} Z` : '';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'chart'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = `
    ${[...Array(5)].map((_, i) => { const kg = yMin + (yMax - yMin) * i / 4; return `<line x1="${L}" x2="${W - R}" y1="${y(kg)}" y2="${y(kg)}" stroke="#26282d"/><text x="2" y="${y(kg) + 4}" fill="#8a8f98" font-size="10">${kg.toFixed(0)}</text>`; }).join('')}
    ${corridor ? `<path d="${corridor}" fill="rgba(96,165,250,.15)" stroke="none"/>` : ''}
    <line x1="${L}" x2="${W - R}" y1="${y(w.goal)}" y2="${y(w.goal)}" stroke="#4ade80" stroke-dasharray="4 4"/>
    ${w.series.length > 1 ? `<path d="${path(w.series)}" fill="none" stroke="#8a8f98" stroke-width="1"/>` : ''}
    ${w.series.map(s => `<circle cx="${x(s.date)}" cy="${y(s.kg)}" r="2.5" fill="#e7e7ea"/>`).join('')}
    ${w.ma7.length > 1 ? `<path d="${path(w.ma7)}" fill="none" stroke="#f59e0b" stroke-width="2.5"/>` : ''}
    <text x="${L}" y="${H - 6}" fill="#8a8f98" font-size="10">${dates[0]}</text>
    <text x="${W - R}" y="${H - 6}" fill="#8a8f98" font-size="10" text-anchor="end">${dates.at(-1)}</text>`;
  return svg;
}
