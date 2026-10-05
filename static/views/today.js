import { api, h, toast, fmtDate, addDays, navigate, QueuedError, queueLength } from '../app.js';

const expanded = new Set(['court_block', 'gym', 'travel_circuit']);
let current = null; // last payload from the API

async function load(date) {
  current = await api(date ? `/api/day/${date}` : '/api/today');
  return current;
}

function applyLocally(path, body) {
  // Optimistic update so a queued (offline) tap is visible immediately.
  if (path === '/api/check') {
    if (body.state === 'untouched') delete current.checks[body.item_key];
    else current.checks[body.item_key] = { state: body.state, value_num: body.value_num ?? null, value_text: body.value_text ?? null };
  } else if (path === '/api/lift') {
    current.lifts = current.lifts.filter(l => !(l.exercise_key === body.exercise_key && l.set_no === body.set_no));
    current.lifts.push({ exercise_key: body.exercise_key, set_no: body.set_no, reps: body.reps, weight_kg: body.weight_kg });
  } else if (path === '/api/rule') {
    current.rule_breaks = current.rule_breaks.filter(k => k !== body.rule_key);
    if (body.broken) current.rule_breaks.push(body.rule_key);
  } else if (path === '/api/weight') {
    current.weight = body.kg;
  }
  current._pending = true;
}

async function put(path, body) {
  try { current = await api(path, { method: 'PUT', body }); return true; }
  catch (e) {
    if (e instanceof QueuedError) { applyLocally(path, body); return true; }
    toast(e.message); return false;
  }
}

function check(k) { return current.checks[k] || { state: 'untouched' }; }

export async function renderToday(root, { param } = {}) {
  await load(param || null);
  draw(root);
}

function draw(root) {
  const d = current, p = d.plan, isToday = d.date === d.today;
  const scroll = window.scrollY;
  root.innerHTML = '';
  const rerender = () => draw(root);
  const setCheck = async (item_key, state, extra = {}) => { if (await put('/api/check', { date: d.date, item_key, state, ...extra })) rerender(); };
  const badgeCls = p.mode === 'normal' ? (p.gym_title ? 'gym' : 'court') : p.mode;

  root.append(h('div', { class: 'row between' },
    h('button', { class: 'btn ghost sm', onclick: () => navigate(`#today/${addDays(d.date, -1)}`) }, '‹'),
    h('div', { style: 'text-align:center' },
      h('div', { class: 'muted small' }, isToday ? 'TODAY' : fmtDate(d.date, { weekday: 'long' }).toUpperCase()),
      h('h1', {}, fmtDate(d.date, { day: 'numeric', month: 'short' })),
      h('span', { class: `badge ${badgeCls}` }, p.day_type)),
    h('button', { class: 'btn ghost sm', disabled: isToday, onclick: () => navigate(`#today/${addDays(d.date, 1)}`) }, '›')));

  root.append(h('div', { class: 'card row between' },
    h('div', {},
      h('div', { class: `score ${d.score.grade}` }, d.score.total),
      h('div', { class: 'muted small' }, d.frozen ? 'Frozen' : (isToday ? 'live score' : 'editable 48 h'))),
    h('div', { style: 'flex:1' },
      h('div', { class: 'row between small' }, h('span', {}, `Protein ${Math.round(d.score.protein)} / ${p.protein_target} g`), h('span', { class: 'muted' }, `streak ${d.streak}`)),
      h('div', { class: 'bar' }, h('i', { style: `width:${Math.min(100, d.score.protein / p.protein_target * 100)}%` })),
      h('div', { class: 'row between small muted wrap', style: 'margin-top:6px' },
        ...Object.entries(d.score.breakdown).map(([k, v]) => h('span', {}, `${k.slice(0, 5)} ${v}`))))));

  if (d._offline || d._pending) root.append(h('div', { class: 'alert warn' }, `Offline · showing saved copy${queueLength() ? ` · ${queueLength()} change${queueLength() > 1 ? 's' : ''} waiting to sync` : ''}. Score updates after sync.`));
  if (isToday && d.yesterday_sleep_missing) {
    const ln = h('input', { class: 'sm', type: 'time' });
    ln.addEventListener('change', async () => { if (ln.value && await put('/api/check', { date: addDays(d.date, -1), item_key: 'sleep', state: 'done', value_text: ln.value })) { toast('Last night logged'); await load(null); rerender(); } });
    root.append(h('div', { class: 'card row between' }, h('div', {}, h('div', { class: 'title' }, 'Last night: in bed at?'), h('div', { class: 'detail' }, 'Counts for yesterday. Bed by 22:30 scores 5.')), ln));
  }
  if (p.adaptation) root.append(h('div', { class: 'alert info' }, 'Weeks 1–2: adaptation. Conservative loads, learn the routine.'));
  for (const pr of d.progression) root.append(h('div', { class: 'alert warn' }, '⬆ ' + pr.message));
  if (p.calorie_level !== 'level0' && p.mode !== 'travel') root.append(h('div', { class: 'alert info' }, `Calorie level: ${p.calorie_level}. Grains adjusted in today's meals.`));

  if (isToday) {
    const inp = h('input', { class: 'sm', type: 'number', step: '0.1', inputmode: 'decimal', placeholder: 'kg', value: d.weight ?? '', style: 'width:90px' });
    root.append(h('div', { class: 'card row between' },
      h('div', {}, h('div', { class: 'title' }, 'Morning weigh-in'), h('div', { class: 'detail' }, d.weight ? `${d.weight} kg logged` : 'before breakfast')),
      h('div', { class: 'row' }, inp, h('button', { class: 'btn sm', onclick: async () => { const kg = parseFloat(inp.value); if (kg && await put('/api/weight', { date: d.date, kg })) { toast('Weight saved'); rerender(); } } }, 'Save'))));
  }

  const body = h('div', { class: d.frozen ? 'frozen' : '' });
  root.append(body);

  const items = [];
  for (const s of p.schedule) items.push({ time: s.time, kind: 'sched', s });
  for (const m of p.meals) items.push({ time: m.time, kind: 'meal', m });
  items.sort((a, b) => a.time.localeCompare(b.time));
  const list = h('div', { class: 'card' });
  for (const it of items) list.append(it.kind === 'sched' ? schedRow(it.s) : mealRow(it.m));
  body.append(list);

  body.append(h('div', { class: 'card' }, h('h2', {}, 'Supplements'),
    ...p.supplements.map(s => h('div', { class: 'item' }, h('div', { class: 'time' }, s.time), h('div', { class: 'body' }, h('div', { class: 'title' }, s.label)),
      tick(`supp:${s.key}`, () => setCheck(`supp:${s.key}`, check(`supp:${s.key}`).state === 'done' ? 'untouched' : 'done'))))));

  body.append(h('div', { class: 'card' }, h('h2', {}, 'Rules — tap to confess a break'),
    h('div', { class: 'rules' }, ...p.rules.map(r => {
      const broken = d.rule_breaks.includes(r.key);
      return h('button', { class: `rule ${broken ? 'broken' : ''}`, onclick: async () => { if (await put('/api/rule', { date: d.date, rule_key: r.key, broken: !broken })) rerender(); } }, (broken ? '✗ ' : '✓ ') + r.label);
    }))));

  if (p.sunday_prep.length) body.append(h('div', { class: 'card' }, h('h2', {}, 'Sunday prep'), ...p.sunday_prep.map((t, i) => h('div', { class: 'detail' }, `${i + 1}. ${t}`))));

  if (isToday) body.append(h('button', { class: 'btn ghost', style: 'width:100%', onclick: async () => {
    const on = p.mode !== 'travel';
    try { await api('/api/travel', { method: 'PUT', body: { start: d.date, end: d.date, on } }); await load(null); rerender(); toast(on ? 'Travel mode on for today' : 'Travel mode off'); }
    catch (e) { toast(e.message); }
  } }, p.mode === 'travel' ? 'Switch today back to the normal plan' : 'Travelling today? Switch to travel mode'));

  window.scrollTo(0, scroll);

  function tick(key, onclick) {
    const st = check(key).state;
    const cls = st === 'done' ? 'on' : st === 'swapped' ? 'swap' : st === 'skipped' ? 'skip' : '';
    return h('button', { class: `tick ${cls}`, onclick }, st === 'done' ? '✓' : st === 'swapped' ? '⇄' : st === 'skipped' ? '✗' : '');
  }

  function schedRow(s) {
    if (s.key === 'sleep') return sleepRow(s);
    const exGroup = s.key === 'court_block' ? p.court_exercises : s.key === 'gym' ? p.gym_exercises : s.key === 'travel_circuit' ? p.travel_circuit : null;
    const title = s.key === 'court_block' ? `${s.label} · ${p.court_title}` : s.key === 'gym' ? `${s.label} · ${p.gym_title}` : s.label;
    return h('div', { class: 'item' }, h('div', { class: 'time' }, s.time),
      h('div', { class: 'body' },
        h('div', { class: 'title', onclick: exGroup ? () => { expanded.has(s.key) ? expanded.delete(s.key) : expanded.add(s.key); rerender(); } : null },
          title, exGroup ? h('span', { class: 'muted small' }, expanded.has(s.key) ? ' ▾' : ' ▸') : null, s.points ? h('span', { class: 'muted small' }, `  ${s.points} pts`) : null),
        exGroup && expanded.has(s.key) ? exerciseList(exGroup) : null),
      tick(s.key, () => setCheck(s.key, check(s.key).state === 'done' ? 'untouched' : 'done')));
  }

  function exerciseList(exs) {
    return h('div', { class: 'sub' }, ...exs.map(ex => {
      const k = `ex:${ex.key}`;
      const head = h('div', { class: 'ex' }, h('div', {}, h('div', {}, ex.name), h('div', { class: 'detail' }, `${ex.sets} × ${ex.reps_label}${ex.load ? ' · ' + ex.load : ''}`)),
        ex.logs_sets ? null : tick(k, () => setCheck(k, check(k).state === 'done' ? 'untouched' : 'done')));
      if (!ex.logs_sets) return head;
      const sets = h('div', { class: 'sets' });
      for (let i = 1; i <= ex.sets; i++) {
        const existing = d.lifts.find(l => l.exercise_key === ex.key && l.set_no === i);
        const reps = h('input', { type: 'number', inputmode: 'numeric', placeholder: 'reps', value: existing ? existing.reps : '' });
        const kg = h('input', { type: 'number', inputmode: 'decimal', step: '0.5', placeholder: 'kg', value: existing ? existing.weight_kg : '' });
        const save = async () => { if (reps.value !== '' && kg.value !== '') { if (await put('/api/lift', { date: d.date, exercise_key: ex.key, set_no: i, reps: +reps.value, weight_kg: +kg.value })) rerender(); } };
        reps.addEventListener('change', save); kg.addEventListener('change', save);
        sets.append(h('div', { class: 'set' }, reps, kg));
      }
      return h('div', {}, head, sets);
    }));
  }

  function mealRow(m) {
    const k = `meal:${m.key}`, c = check(k);
    return h('div', { class: 'item' }, h('div', { class: 'time' }, m.time),
      h('div', { class: 'body' },
        h('div', { class: 'title' }, m.label, h('span', { class: 'muted small' }, `  ${m.protein} g P · ${m.kcal} kcal${m.optional ? ' · optional' : ''}`)),
        h('div', { class: 'detail' }, m.detail),
        h('div', { class: 'row', style: 'margin-top:8px' },
          h('button', { class: `btn sm ${c.state === 'done' ? 'on' : ''}`, onclick: () => setCheck(k, c.state === 'done' ? 'untouched' : 'done', p.mode === 'travel' ? { value_num: c.value_num ?? m.protein } : {}) }, 'Ate'),
          h('button', { class: `btn sm swap ${c.state === 'swapped' ? 'on' : ''}`, onclick: () => setCheck(k, 'swapped', { value_num: c.value_num ?? null, value_text: c.value_text ?? null }) }, 'Swapped'),
          h('button', { class: `btn sm skip ${c.state === 'skipped' ? 'on' : ''}`, onclick: () => setCheck(k, 'skipped') }, 'Skipped')),
        (c.state === 'swapped' || c.state === 'skipped' || (p.mode === 'travel' && c.state === 'done')) ? detailInputs(k, c) : null));
  }

  function detailInputs(k, c) {
    const text = h('input', { placeholder: c.state === 'skipped' ? 'why / what instead (optional)' : 'what did you eat? (required for half credit)', value: c.value_text || '' });
    const grams = h('input', { class: 'sm', type: 'number', inputmode: 'numeric', placeholder: 'protein g', value: c.value_num ?? '', style: 'width:110px' });
    const save = () => setCheck(k, c.state, { value_text: text.value || null, value_num: grams.value === '' ? null : +grams.value });
    text.addEventListener('change', save); grams.addEventListener('change', save);
    return h('div', { class: 'row', style: 'margin-top:8px' }, text, grams);
  }

  function sleepRow(s) {
    const c = check('sleep');
    const inp = h('input', { class: 'sm', type: 'time', value: c.value_text || '' });
    inp.addEventListener('change', () => inp.value && setCheck('sleep', 'done', { value_text: inp.value }));
    return h('div', { class: 'item' }, h('div', { class: 'time' }, s.time), h('div', { class: 'body' }, h('div', { class: 'title' }, s.label), h('div', { class: 'detail' }, 'Log the time you were in bed')), inp);
  }
}
