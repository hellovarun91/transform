import { api, h } from '../app.js';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
let cache = null;
let sel = (new Date().getDay() + 6) % 7;

export async function renderPlan(root) {
  cache = cache || (await api('/api/plan')).days;
  draw(root);
}

function draw(root) {
  const p = cache[sel];
  root.innerHTML = '';
  root.append(h('h1', {}, 'Plan'), h('p', { class: 'muted small', style: 'margin:4px 0 12px' }, 'Fixed per 4-week block. Loads progress via prompts on Today.'));
  root.append(h('div', { class: 'daytabs' }, ...DAYS.map((d, i) => h('button', { class: i === sel ? 'active' : '', onclick: () => { sel = i; draw(root); } }, d))));
  root.append(h('div', { class: 'card' }, h('span', { class: `badge ${p.mode === 'normal' ? (p.gym_title ? 'gym' : 'court') : p.mode}` }, p.day_type),
    h('div', { style: 'margin-top:10px' }, ...p.schedule.map(s => h('div', { class: 'item' }, h('div', { class: 'time' }, s.time),
      h('div', { class: 'body' }, h('div', { class: 'title' }, s.key === 'court_block' ? `${s.label} · ${p.court_title}` : s.key === 'gym' ? `${s.label} · ${p.gym_title}` : s.label)))))));
  if (p.court_exercises.length) root.append(exCard(`Court block · ${p.court_title}`, p.court_exercises));
  if (p.gym_exercises.length) root.append(exCard(`Gym · ${p.gym_title}`, p.gym_exercises));
  root.append(h('div', { class: 'card' }, h('h2', {}, `Meals · ${p.protein_target} g protein`),
    ...p.meals.map(m => h('div', { class: 'item' }, h('div', { class: 'time' }, m.time),
      h('div', { class: 'body' }, h('div', { class: 'title' }, m.label, h('span', { class: 'muted small' }, `  ${m.protein} g · ${m.kcal} kcal`)), h('div', { class: 'detail' }, m.detail))))));
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Supplements'), ...p.supplements.map(s => h('div', { class: 'detail' }, `${s.time}  ${s.label}`))));
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Rules every day'), ...p.rules.map(r => h('div', { class: 'detail' }, '• ' + r.label))));
  if (p.sunday_prep.length) root.append(h('div', { class: 'card' }, h('h2', {}, 'Sunday prep'), ...p.sunday_prep.map((t, i) => h('div', { class: 'detail' }, `${i + 1}. ${t}`))));
}

function exCard(title, exs) {
  return h('div', { class: 'card' }, h('h2', {}, title), ...exs.map(e => h('div', { class: 'ex' }, h('div', {}, e.name), h('div', { class: 'muted' }, `${e.sets} × ${e.reps_label}`))));
}
