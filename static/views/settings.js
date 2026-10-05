import { api, h, toast, logout, state, fmtDate } from '../app.js';

const LABELS = { wake: 'Wake-up', whey_am: 'Morning shake', breakfast: 'Breakfast', lunch: 'Lunch', snack: 'Snack', gym: 'Gym reminder', dinner: 'Dinner', magnesium: 'Magnesium / bed', log_day: 'Log your day', weekly: 'Weekly scorecard' };

function b64ToU8(b64) {
  const pad = '='.repeat((4 - b64.length % 4) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

export async function renderSettings(root) {
  const s = await api('/api/settings');
  root.innerHTML = '';
  root.append(h('h1', {}, 'Settings'));

  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  const supported = 'serviceWorker' in navigator && 'PushManager' in window;
  let reg = null, sub = null;
  if (supported) { try { reg = await Promise.race([navigator.serviceWorker.ready, new Promise(r => setTimeout(() => r(null), 1500))]); sub = reg ? await reg.pushManager.getSubscription() : null; } catch {} }
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Notifications'),
    !supported ? h('div', { class: 'alert warn' }, 'Push not supported in this browser.') :
    !standalone ? h('div', { class: 'alert warn' }, 'iPhone: tap Share → Add to Home Screen, then open Transform from the icon to enable push.') : null,
    !s.vapid_public_key ? h('div', { class: 'alert bad' }, 'Server has no VAPID keys set.') : null,
    h('div', { class: 'row' },
      h('button', { class: `btn ${sub ? '' : 'primary'}`, disabled: !reg || !s.vapid_public_key, onclick: async () => {
        try {
          if (sub) { await api('/api/push/subscribe', { method: 'DELETE', body: { endpoint: sub.endpoint } }); await sub.unsubscribe(); toast('Push disabled'); }
          else {
            const perm = await Notification.requestPermission();
            if (perm !== 'granted') { toast('Permission denied'); return; }
            const ns = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(s.vapid_public_key) });
            await api('/api/push/subscribe', { method: 'POST', body: ns.toJSON() });
            toast('Push enabled');
          }
          renderSettings(root);
        } catch (e) { toast(e.message); }
      } }, sub ? 'Disable push on this device' : 'Enable push on this device')),
    h('div', { style: 'margin-top:12px' }, ...Object.keys(s.notif_times).map(k => h('label', { class: 'row between', style: 'padding:8px 0;border-top:1px solid var(--line)' },
      h('span', {}, `${LABELS[k] || k} `, h('span', { class: 'muted small' }, s.notif_times[k])),
      h('input', { type: 'checkbox', style: 'width:auto', checked: s.notif_enabled[k], onchange: async (e) => { try { await api('/api/settings', { method: 'PUT', body: { notif_enabled: { [k]: e.target.checked } } }); toast('Saved'); } catch (err) { toast(err.message); } } }))))));

  const start = h('input', { type: 'date' }), end = h('input', { type: 'date' });
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Travel mode'),
    h('p', { class: 'detail' }, 'Hotel circuit + protein rules replace the plan. Still scored to 100.'),
    h('div', { class: 'row', style: 'margin-top:8px' }, start, end),
    h('div', { class: 'row', style: 'margin-top:8px' },
      h('button', { class: 'btn', onclick: () => setTravel(true) }, 'Mark travel'),
      h('button', { class: 'btn ghost', onclick: () => setTravel(false) }, 'Clear')),
    s.travel_days_upcoming.length ? h('div', { class: 'detail', style: 'margin-top:8px' }, 'Upcoming: ' + s.travel_days_upcoming.map(d => fmtDate(d)).join(', ')) : null));
  async function setTravel(on) {
    if (!start.value) return toast('Pick a start date');
    try { await api('/api/travel', { method: 'PUT', body: { start: start.value, end: end.value || start.value, on } }); toast(on ? 'Travel set' : 'Cleared'); renderSettings(root); } catch (e) { toast(e.message); }
  }

  const pt = h('input', { type: 'number', inputmode: 'numeric', value: s.protein_target, style: 'width:90px' });
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Targets'),
    h('div', { class: 'row between' }, h('span', {}, 'Protein target (g)'), h('div', { class: 'row' }, pt, h('button', { class: 'btn sm', onclick: async () => { try { await api('/api/settings', { method: 'PUT', body: { protein_target: +pt.value } }); toast('Saved'); } catch (e) { toast(e.message); } } }, 'Save'))),
    h('div', { class: 'detail', style: 'margin-top:10px' }, `Calorie level today: ${s.calorie_level_today} (0 = aggressive plan; +1 adds the dinner roti after a guardrail trigger)`),
    h('div', { class: 'detail' }, `Diet break: ${fmtDate(s.diet_break.start)} – ${fmtDate(s.diet_break.end)}`),
    h('div', { class: 'detail' }, `Start ${s.start_weight} kg on ${fmtDate(s.start_date)} · goal ${s.goal_weight} kg`)));

  root.append(h('div', { class: 'card' }, h('h2', {}, 'Data'),
    h('div', { class: 'row' },
      h('button', { class: 'btn', onclick: async () => {
        const r = await fetch('/api/export', { headers: { Authorization: `Bearer ${state.token}` } });
        const blob = await r.blob(); const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = `transform-export-${new Date().toISOString().slice(0, 10)}.json`; a.click();
      } }, 'Export JSON'),
      h('button', { class: 'btn danger', onclick: () => { logout(); } }, 'Lock app')),
    h('p', { class: 'detail', style: 'margin-top:8px' }, 'PIN is set by the TRANSFORM_PIN environment variable on Railway. Plan changes are commits to plan/plan.yaml.')));
}
