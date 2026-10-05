import { api, h, todayISO, addDays, fmtDate, navigate } from '../app.js';

let selected = null;

function isoWeek(iso) {
  const d = new Date(iso + 'T00:00:00Z');
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const y = d.getUTCFullYear();
  const wk = Math.ceil(((d - Date.UTC(y, 0, 1)) / 86400000 + 1) / 7);
  return `${y}-W${String(wk).padStart(2, '0')}`;
}

export async function renderHistory(root) {
  const today = todayISO();
  const start = addDays(today, -83);
  const mondayOffset = (new Date(start).getDay() + 6) % 7;
  const gridStart = addDays(start, -mondayOffset);
  const [hist, week] = await Promise.all([
    api(`/api/history?from=${gridStart}&to=${today}`),
    api(`/api/week/${isoWeek(selected || today)}`),
  ]);
  root.innerHTML = '';
  root.append(h('h1', {}, 'History'));

  root.append(h('div', { class: 'card' }, h('h2', {}, `Week ${week.week.split('-W')[1]} · ${fmtDate(week.start)} – ${fmtDate(week.end)}`),
    h('div', { class: 'kpi' },
      h('div', {}, h('b', {}, week.avg_score), h('span', {}, 'avg score')),
      h('div', {}, h('b', {}, week.green_days), h('span', {}, 'green days')),
      h('div', {}, h('b', {}, `${week.sessions_done}/${week.sessions_target}`), h('span', {}, 'sessions'))),
    h('div', { class: 'kpi', style: 'margin-top:8px' },
      h('div', {}, h('b', {}, week.protein_avg), h('span', {}, 'protein avg g')),
      h('div', {}, h('b', {}, week.lifts_progressed), h('span', {}, 'lifts up')),
      h('div', {}, h('b', {}, week.weight_change === null ? '—' : (week.weight_change > 0 ? '+' : '') + week.weight_change), h('span', {}, 'kg this week'))),
    h('div', { class: `alert ${week.on_plan ? 'info' : 'bad'}`, style: 'margin:10px 0 0' }, `${week.on_plan ? 'ON PLAN' : 'OFF PLAN'} · ${week.verdict.replace('_', ' ')} vs corridor`)));

  const grid = h('div', { class: 'heat' }, ...['M', 'T', 'W', 'T', 'F', 'S', 'S'].map(d => h('div', { class: 'small muted', style: 'text-align:center' }, d)));
  for (const d of hist.days) {
    const cls = ['cell', d.grade || '', d.date === today ? 'today' : '', d.date === selected ? 'sel' : ''].join(' ');
    grid.append(h('div', { class: cls, onclick: () => { selected = d.date; renderHistory(root); } }, d.score === null ? '' : d.score));
  }
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Last 12 weeks'), grid));

  if (selected) {
    const day = await api(`/api/day/${selected}`);
    root.append(h('div', { class: 'card' }, h('div', { class: 'row between' }, h('h2', {}, fmtDate(selected, { weekday: 'long', day: 'numeric', month: 'short' })), h('span', { class: `score ${day.score.grade}`, style: 'font-size:28px' }, day.score.total)),
      h('div', { class: 'row wrap small muted' }, ...Object.entries(day.score.breakdown).map(([k, v]) => h('span', {}, `${k} ${v}`))),
      h('div', { class: 'detail', style: 'margin-top:8px' }, `${day.plan.day_type} · protein ${Math.round(day.score.protein)} g · ${Object.keys(day.checks).length} items logged${day.rule_breaks.length ? ' · breaks: ' + day.rule_breaks.join(', ') : ''}`),
      ...Object.entries(day.checks).filter(([k, c]) => k.startsWith('meal:') && c.value_text).map(([k, c]) => h('div', { class: 'detail' }, `${k.slice(5)}: ${c.state} — ${c.value_text}`)),
      h('button', { class: 'btn sm', style: 'margin-top:10px', onclick: () => navigate(`#today/${selected}`) }, day.frozen ? 'View day' : 'Edit day')));
  }
}
