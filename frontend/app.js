/* FINN frontend — vanilla JS, no build step. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (n, d = 0) => n == null ? '—' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d });
const pct = (n, d = 1) => n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(d)}%`;
const cls = n => n == null ? 'mu' : n > 0 ? 'up' : n < 0 ? 'dn' : 'mu';
const lab = c => c.replace(/_/g, ' ');
const short = p => p ? p.slice(0, 3) + " '" + p.slice(-2) : '';

/* ---------------- state ---------------- */
const DEF = { window_hours: 24, price_move_pct: 3, volume_mult: 2, cats: {} };
const S = {
  meta: null, rules: Object.assign({}, DEF, JSON.parse(localStorage.getItem('finn.rules') || '{}')),
  digest: null, alerts: [], thread: [], ctx: null, seen: new Set(JSON.parse(localStorage.getItem('finn.seen') || '[]')),
};
const saveRules = () => localStorage.setItem('finn.rules', JSON.stringify(S.rules));
function qs(extra = {}) {
  const r = S.rules, watch = [], mute = [];
  Object.entries(r.cats || {}).forEach(([c, v]) => v === 'watch' ? watch.push(c) : v === 'mute' ? mute.push(c) : 0);
  const p = new URLSearchParams({ hours: r.window_hours, price: r.price_move_pct, vol: r.volume_mult, ...extra });
  if (watch.length) p.set('watch', watch.join(','));
  if (mute.length) p.set('mute', mute.join(','));
  return p.toString();
}
const rulesBody = () => {
  const watch = [], mute = [];
  Object.entries(S.rules.cats || {}).forEach(([c, v]) => v === 'watch' ? watch.push(c) : v === 'mute' ? mute.push(c) : 0);
  const o = { window_hours: S.rules.window_hours, price_move_pct: S.rules.price_move_pct, volume_mult: S.rules.volume_mult };
  if (watch.length) o.watch = watch; if (mute.length) o.mute = mute; return o;
};
async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function ago(ts) {
  const m = (Date.now() - new Date(ts).getTime()) / 60000;
  if (isNaN(m)) return '';
  if (m < 60) return `${Math.max(1, Math.round(m))}m`;
  if (m < 2880) return `${Math.round(m / 60)}h`;
  return `${Math.round(m / 1440)}d`;
}
function toast(title, sub) {
  const t = $('#toast'); $('b', t).textContent = title; $('span', t).textContent = sub || '';
  t.classList.add('on'); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('on'), 4200);
}

/* ---------------- tiny charts ---------------- */
function spark(vals, w = 64, h = 24, up = true, neutral = false) {
  if (!vals || vals.length < 2) return '';
  const mn = Math.min(...vals), mx = Math.max(...vals), rg = mx - mn || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - mn) / rg * (h - 4)).toFixed(1)}`).join(' ');
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts}" fill="none" stroke="${neutral ? 'var(--dim)' : up ? 'var(--up)' : 'var(--dn)'}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>${neutral ? `<circle cx="${w}" cy="${(h - 2 - (vals[vals.length - 1] - mn) / rg * (h - 4)).toFixed(1)}" r="2.6" fill="${up ? 'var(--up)' : 'var(--dn)'}"/>` : ''}</svg>`;
}
function trajChart(tr) {
  const W = 320, H = 150, pl = 6, pr = 6, top = 14, bot = 26, n = tr.q.length, bw = (W - pl - pr) / n;
  const yoy = tr.q_yoy.map(v => v ?? 0), mx = Math.max(...yoy, 1), mn = Math.min(...yoy, 0);
  const sc = v => top + (H - top - bot) * (1 - (v - mn) / (mx - mn || 1));
  const bars = yoy.map((v, i) => `<rect x="${pl + i * bw + 5}" y="${Math.min(sc(v), sc(0))}" width="${bw - 10}" height="${Math.abs(sc(v) - sc(0)) || 1}" rx="3" fill="rgba(138,180,255,.55)"/><text x="${pl + i * bw + bw / 2}" y="${sc(v) - 4}" text-anchor="middle">${tr.q_yoy[i] == null ? '' : tr.q_yoy[i].toFixed(0)}</text>`).join('');
  const om = tr.q_opm, omn = Math.min(...om), omx = Math.max(...om);
  const so = v => top + (H - top - bot) * (1 - (v - omn) / (omx - omn || 1)) * .62;
  const line = om.map((v, i) => `${pl + i * bw + bw / 2},${so(v)}`).join(' ');
  const dots = om.map((v, i) => `<circle cx="${pl + i * bw + bw / 2}" cy="${so(v)}" r="2.6" fill="var(--am)"/>`).join('');
  const xl = tr.q.map((p, i) => `<text x="${pl + i * bw + bw / 2}" y="${H - 8}" text-anchor="middle">${short(p)}</text>`).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}">${bars}<polyline points="${line}" fill="none" stroke="var(--am)" stroke-width="1.8"/>${dots}${xl}</svg>
  <div class="legend"><span style="--c:rgba(138,180,255,.7)">Revenue growth, YoY %</span><span style="--c:var(--am)">Operating margin ${om[om.length - 1].toFixed(1)}%</span></div>`;
}
function cashChart(cs) {
  const W = 320, H = 150, pl = 6, pr = 6, top = 22, bot = 26, n = cs.periods.length, gw = (W - pl - pr) / n;
  const all = [...cs.cfo, ...cs.pat].filter(v => v != null), mx = Math.max(...all, 1);
  const hh = v => (H - top - bot) * Math.max(v, 0) / mx;
  let g = '';
  cs.periods.forEach((p, i) => {
    const x = pl + i * gw, bw = (gw - 12) / 2;
    g += `<rect x="${x + 6}" y="${H - bot - hh(cs.pat[i])}" width="${bw}" height="${hh(cs.pat[i])}" rx="2" fill="rgba(255,255,255,.25)"/>
    <rect x="${x + 6 + bw + 1}" y="${H - bot - hh(cs.cfo[i])}" width="${bw}" height="${hh(cs.cfo[i])}" rx="2" fill="${(cs.conversion[i] ?? 0) >= .8 ? 'var(--up)' : 'var(--dn)'}" opacity=".85"/>
    <text x="${x + gw / 2}" y="${top - 8}" text-anchor="middle" style="fill:${(cs.conversion[i] ?? 0) >= .8 ? 'var(--up)' : 'var(--dn)'}">${cs.conversion[i] == null ? '' : cs.conversion[i].toFixed(2) + '×'}</text>
    <text x="${x + gw / 2}" y="${H - 8}" text-anchor="middle">${short(p)}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}">${g}</svg><div class="legend"><span style="--c:rgba(255,255,255,.35)">Net profit</span><span style="--c:var(--up)">Operating cash flow</span><span style="--c:var(--dn)">below 0.8× of profit</span></div>`;
}

/* ---------------- Today ---------------- */
const WINDOWS = [[6, '6h'], [24, '24h'], [72, '3d'], [168, '7d']];
async function loadToday() {
  const el = $('#t-today');
  if (!S.digest) el.innerHTML = '<div class="skel" style="height:120px;margin-top:18px"></div><div class="skel"></div><div class="skel"></div>';
  try {
    const [d, a] = await Promise.all([api('/api/digest?' + qs()), api('/api/alerts?' + qs())]);
    S.digest = d; S.alerts = a.alerts; renderToday(); renderBook(); notify(a.alerts);
  } catch (e) { el.innerHTML = `<div class="err">Couldn’t load the feed.<br><small>${esc(e.message)}</small></div>`; }
}
function renderToday() {
  const d = S.digest, p = d.pulse, el = $('#t-today');
  const now = p.now, hrs = p.window_hours;
  const winLabel = hrs < 48 ? `${hrs}h` : `${Math.round(hrs / 24)} days`;
  const big = now === 0 ? 'No high-priority filings' : `<em>${now}</em> filing${now === 1 ? '' : 's'} to review`;
  const best = p.best, worst = p.worst;
  const chips = WINDOWS.map(([h, l]) => `<button class="chip ${hrs === h ? 'on' : ''}" data-w="${h}">${l}</button>`).join('') +
    `<button class="chip ${WINDOWS.some(w => w[0] === hrs) ? '' : 'on'}" id="cw">${WINDOWS.some(w => w[0] === hrs) ? 'Custom…' : winLabel}</button>`;
  const hi = S.alerts.filter(a => a.kind !== 'filing');
  const alerts = hi.length ? `<div class="sec-h"><b>Triggered by your rules</b><span>${hi.length}</span></div><div class="alerts">${hi.slice(0, 8).map(a => `
    <button class="al ${a.severity}" data-sym="${esc(a.symbol)}"><div class="k">${a.kind === 'price' ? 'Price move' : 'Volume'}</div><div class="t">${esc(a.title)}</div><div class="d">${esc(a.detail)}</div></button>`).join('')}</div>` : '';
  const tier = t => d.items.filter(i => i.tier === t);
  const sec = (t, title, items) => items.length ? `<div class="sec-h"><b>${title}</b><span>${items.length}</span></div>${items.map(card).join('')}` : '';
  const rt = tier('routine');
  const routine = rt.length ? `<div class="sec-h"><b>Routine</b><span>collapsed</span></div><details class="routine"><summary><span>${rt.length} routine filing${rt.length > 1 ? 's' : ''} hidden</span><span>›</span></summary>${rt.map(i => `<div class="rrow"><span class="tkr">${esc(i.symbol)}</span><span>${esc(i.headline)}</span><a href="${esc(i.url)}" target="_blank" rel="noopener">↗</a></div>`).join('')}</details>` : '';
  el.innerHTML = `
  <div class="pulse">${d.data.mode === 'snapshot' ? '<p class="note">Portfolio snapshot · '+esc(d.data.asof.replace('T',' ').slice(0,16))+' IST · Past '+winLabel+'</p>' : ''}<div class="big">${big}</div>
   <div class="sub"><span>${p.total} filings across your book in ${winLabel}</span>
   <span class="pill">Book <b class="${cls(p.avg_move)}">${pct(p.avg_move, 2)}</b></span>
   ${best ? `<span class="pill">▲ ${esc(best.symbol)} <b class="up">${pct(best.pct)}</b></span>` : ''}${worst ? `<span class="pill">▼ ${esc(worst.symbol)} <b class="dn">${pct(worst.pct)}</b></span>` : ''}</div></div>
  <div class="chips">${chips}</div>${alerts}
  ${sec('now', 'Needs you', tier('now'))}${sec('look', 'Worth a look', tier('look'))}${routine}
  <p class="note" style="text-align:center;margin-top:22px">Prices as of ${esc(p.asof || '—')} close · ${S.meta?.data?.mode === 'demo' ? 'synthetic demo data' : 'NSE / Yahoo / screener.in'}</p>`;
  $$('[data-w]', el).forEach(b => b.onclick = () => { S.rules.window_hours = +b.dataset.w; saveRules(); S.digest = null; loadToday(); });
  $('#cw', el).onclick = customWindow;
  $$('.al', el).forEach(b => b.onclick = () => openResearch(b.dataset.sym));
  bindCards(el);
  const dot = $('#dot'); const n = p.now; dot.hidden = !n; dot.textContent = n;
}
function customWindow() {
  const h = S.rules.window_hours;
  openSheet(`<div class="rh"><h2>Choose a window</h2><div class="src">Every filing across your book in the period you pick, prioritised.</div></div>
  <div class="rule"><div class="l"><b>Look back</b><span id="wv">${h < 48 ? h + ' h' : Math.round(h / 24) + ' d'}</span></div>
  <input type="range" id="wr" min="1" max="336" value="${h}"></div><div class="actions"><button class="btn pri" id="wg">Show digest</button></div>`);
  const r = $('#wr'); r.oninput = () => $('#wv').textContent = r.value < 48 ? r.value + ' h' : (r.value / 24).toFixed(1) + ' d';
  $('#wg').onclick = () => { S.rules.window_hours = +r.value; saveRules(); closeSheet(); S.digest = null; loadToday(); };
}

function resultsDetail(e) {
  const rows = e.rows.map(r => {
    const w = Math.min(Math.abs(r.yoy ?? 0), 60) / 60 * 50;
    const bar = r.yoy == null ? '' : `<div class="bar2"><i style="${r.yoy >= 0 ? `left:50%;width:${w}%;background:var(--up)` : `right:50%;width:${w}%;background:var(--dn)`}"></i></div>`;
    return `<tr><td>${r.metric}</td><td class="v">${fmt(r.cur, 0)}</td><td><span class="dl ${cls(r.qoq)}">${pct(r.qoq)}</span></td><td><span class="dl ${cls(r.yoy)}">${pct(r.yoy)}</span>${bar}</td></tr>`;
  }).join('');
  const m = e.ebitda_margin;
  return `<div style="margin-bottom:8px">${e.verdict ? `<span class="tone ${e.verdict.tone}">${e.verdict.tone}</span>` : ''}<span class="mu">${esc(e.quarter)} · ₹ crore</span></div>
  <table class="rt"><thead><tr><th>Metric</th><th>Now</th><th>vs last Q</th><th>vs year ago</th></tr></thead><tbody>${rows}</tbody></table>
  ${m ? `<div class="note">EBITDA margin ${fmt(m.cur, 1)}% · last quarter ${m.prev == null ? '—' : fmt(m.prev, 1)}% · year ago ${m.yoy == null ? '—' : fmt(m.yoy, 1)}%</div>` : ''}
  <div class="note">${esc(e.basis)}</div>`;
}
function mgmtDetail(e) {
  const ex = e.events.filter(x => x.type === 'exit').map(x => `<div class="person"><div class="av">↗</div><div><b>${esc(x.person)}</b><div class="r">Leaving · ${esc(x.role)}</div></div></div>`).join('');
  const inn = e.incoming.map(x => {
    const b = x.bio;
    return `<div class="person"><div class="av">${esc(x.person[0])}</div><div><b>${esc(x.person)}</b><div class="r">Joining · ${esc(x.role)}${e.effective ? ' · w.e.f. ' + esc(e.effective) : ''}</div>
    ${b ? `<p>${esc(b.summary || '')}</p>${(b.prev || []).length ? `<div class="note">Before: ${b.prev.map(esc).join(' → ')}</div>` : ''}${(b.links || []).map(l => `<div class="note"><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a></div>`).join('')}${b.note ? `<div class="note">${esc(b.note)}</div>` : ''}` : '<p class="mu">No public background found yet.</p>'}</div></div>`;
  }).join('');
  return ex + inn;
}
function card(it) {
  const ctx = it.context ? `<div class="ctx">● ${esc(it.context)}</div>` : '';
  let more = '';
  if (it.enrich?.kind === 'results') more += resultsDetail(it.enrich);
  if (it.enrich?.kind === 'mgmt') more += mgmtDetail(it.enrich);
  if (!more) more += `<div class="why">${esc(it.subject)} — ${esc(it.headline)}</div>`;
  if (it.related?.length) more += `<div class="sec-h" style="margin:14px 0 4px"><b>Also filed</b></div>` + it.related.map(r => `<div class="rel"><span>${ago(r.ts)}</span><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.subject)}</a></div>`).join('');
  const link = it.url.startsWith('demo://') || it.source === 'DEMO' ? `<span class="btn ghost">Filing · demo</span>` : `<a class="btn" href="${esc(it.url)}" target="_blank" rel="noopener">Open filing ↗</a>`;
  return `<article class="card ${it.tier}" data-id="${esc(it.id)}">
   <div class="top"><span class="tkr">${esc(it.symbol)}</span><span class="cat">${esc(lab(it.cat))}</span><span class="time">${ago(it.ts)} ago<span class="caret">›</span></span></div>
   <h3>${esc(it.headline)}</h3>${ctx}<div class="why">${esc(it.why)}</div>
   <div class="more">${more}<div class="actions">${link}<button class="btn pri" data-r="${esc(it.symbol)}">Research ›</button><button class="btn ghost" data-m="${esc(it.cat)}">Mute ${esc(lab(it.cat))}</button></div></div></article>`;
}
function bindCards(root) {
  $$('.card', root).forEach(c => c.addEventListener('click', e => { if (e.target.closest('a,button')) return; c.classList.toggle('open'); }));
  $$('[data-r]', root).forEach(b => b.onclick = e => { e.stopPropagation(); openResearch(b.dataset.r); });
  $$('[data-m]', root).forEach(b => b.onclick = e => { e.stopPropagation(); S.rules.cats[b.dataset.m] = 'mute'; saveRules(); toast('Muted ' + lab(b.dataset.m), 'You can change this in Rules.'); S.digest = null; loadToday(); });
}

/* ---------------- alerts delivery ---------------- */
function notify(alerts) {
  const fresh = alerts.filter(a => !S.seen.has(a.id) && a.severity === 'high');
  if (!fresh.length) return;
  fresh.forEach(a => S.seen.add(a.id));
  localStorage.setItem('finn.seen', JSON.stringify([...S.seen].slice(-300)));
  const a = fresh[0];
  if (fresh.length > 1) toast(`${fresh.length} alerts triggered by your rules`, `Most severe: ${a.title}`);
  else toast(a.title, a.detail);
  try { if (navigator.vibrate && navigator.userActivation?.hasBeenActive) navigator.vibrate(30); } catch (e) { }
  if ('Notification' in window && Notification.permission === 'granted') new Notification('FINN · ' + a.title, { body: a.detail });
}
setInterval(() => { if (!document.hidden) api('/api/alerts?' + qs()).then(a => { S.alerts = a.alerts; notify(a.alerts); }).catch(() => { }); }, 90000);

/* ---------------- Book ---------------- */
function renderBook() {
  const el = $('#t-book'), d = S.digest; if (!d) return;
  const m = d.market, rows = d.universe.filter(u => m[u.symbol]).sort((a, b) => Math.abs(m[b.symbol].pct) - Math.abs(m[a.symbol].pct));
  const col = v => { const k = Math.min(Math.abs(v) / 5, 1); return v >= 0 ? `rgba(121,217,143,${.12 + k * .5})` : `rgba(255,113,100,${.12 + k * .5})`; };
  const tiles = rows.map(u => `<button class="tile" style="background:${col(m[u.symbol].pct)}" data-sym="${u.symbol}"><b>${esc(u.symbol)}</b><span>${pct(m[u.symbol].pct)}</span></button>`).join('');
  const thr = S.rules.volume_mult;
  const list = rows.map(u => {
    const x = m[u.symbol], hot = Math.abs(x.pct) >= S.rules.price_move_pct || (x.vol_ratio || 0) >= thr;
    const vw = Math.min((x.vol_ratio || 0) / (thr * 2), 1) * 100;
    return `<button class="row ${hot ? 'hot' : ''}" data-sym="${u.symbol}"><div><div class="n">${esc(u.name)}</div><div class="s"><span>${esc(u.symbol)}</span><span>·</span><span>${esc(u.sector)}</span></div>
    <div class="vr" title="Volume ${x.vol_ratio}× average"><i style="width:${vw}%"></i><u style="left:50%"></u></div></div>
    <div>${spark(x.spark, 64, 26, x.pct >= 0, true)}</div><div class="px"><b>₹${fmt(x.close, 1)}</b><span class="${cls(x.pct)}">${pct(x.pct, 2)}</span><div class="mu" style="font-size:11px">${x.vol_ratio ?? '—'}× vol</div></div></button>`;
  }).join('');
  const sug = (S.meta?.suggested || []).map(s => `<button class="chip" data-sym="${s}">${s}</button>`).join('');
  el.innerHTML = `<div class="pulse">${d.data.mode === 'snapshot' ? '<p class="note">Portfolio snapshot · '+esc(d.data.asof.replace('T',' ').slice(0,16))+' IST · Past '+winLabel+'</p>' : ''}<div class="big">Your book, <em>one glance</em>.</div><div class="sub">Colour = today’s move. Tap any name for the research view.</div></div>
  <div class="heat">${tiles}</div>
  <div class="sec-h"><b>Research any NSE ticker</b></div>
  <form class="search" id="sf"><input id="si" placeholder="e.g. ASIANPAINT, HAL, PIDILITIND" autocapitalize="characters" autocomplete="off"><button class="btn pri" type="submit">Research</button></form>
  <div class="chips" style="padding-top:2px">${sug}</div><div class="hint">Built to generalise: works on any ticker with screener.in data — not just the book.</div>
  <div class="sec-h"><b>Holdings</b><span>by size of move</span></div><div class="hint" style="margin:-4px 2px 4px">30-day line · dot = today’s direction · amber tick on the bar = your volume trigger.</div>${list}`;
  $$('[data-sym]', el).forEach(b => b.onclick = () => openResearch(b.dataset.sym));
  $('#sf', el).onsubmit = e => { e.preventDefault(); const v = $('#si', el).value.trim().toUpperCase(); if (v) openResearch(v); };
}

/* ---------------- research renderer ---------------- */
const TITLES = { business: 'What it does', financials: 'Financial snapshot', trajectory: 'Trajectory', balance: 'Balance sheet', cash: 'Cash quality', guidance: 'Promised vs delivered', narrative: 'Narrative vs numbers', bullbear: 'Bull vs bear' };
const ORDER = ['narrative', 'guidance', 'financials', 'business', 'trajectory', 'balance', 'cash', 'bullbear'];
const PALETTE = ['#8ab4ff', '#e9c46a', '#79d98f', '#c79bff', '#ff9e7a'];
function flagsHTML(fl) { return fl.map(([l, t]) => `<div class="flag"><i class="${l}"></i><span>${esc(t)}</span></div>`).join(''); }
function band(r) {
  const vals = [r.lo, r.hi ?? r.lo, r.actual ?? r.lo]; const mn = Math.min(...vals), mx = Math.max(...vals), pad = (mx - mn) * .45 + 2;
  const a = mn - pad, b = mx + pad, X = v => ((v - a) / (b - a) * 100).toFixed(1);
  const colr = { delivered: 'var(--up)', near: 'var(--am)', missed: 'var(--dn)' }[r.status];
  return `<div class="track"><div class="ln"></div><div class="bandx" style="left:${X(r.lo)}%;width:${Math.max(X(r.hi ?? r.lo) - X(r.lo), 1.2)}%"></div>${r.actual != null ? `<div class="act" style="left:${X(r.actual)}%;background:${colr}"></div>` : ''}</div>`;
}
const MET = { revenue_growth: 'Revenue growth', ebitda_margin: 'EBITDA margin', pat_growth: 'PAT growth' };
function section(k, v, r) {
  if (!v || (Array.isArray(v) && !v.length)) return '';
  const T = TITLES[k]; let body = '';
  if (k === 'business') {
    const seg = v.segments || [];
    body = `<div>${esc(v.what || 'Business description not found in the annual report.')}</div>` + (seg.length ? `<div class="seg">${seg.map((s, i) => `<i style="width:${s.share}%;background:${PALETTE[i % 5]}"></i>`).join('')}</div><div class="legend">${seg.map((s, i) => `<span style="--c:${PALETTE[i % 5]}">${esc(s.name)} ${s.share}%</span>`).join('')}</div>` : '') +
      (v.watch_notes?.length ? `<div style="margin-top:12px">${v.watch_notes.map(n => `<div class="flag"><i class="amber"></i><span><b>${esc(n.label)}.</b> ${esc(n.text)}</span></div>`).join('')}</div>` : '');
  } else if (k === 'financials') {
    const q = v.quarter, f = v.fy;
    const K = (l, val, sub, c) => `<div class="kpi"><small>${l}</small><b>${val}</b><span class="${c || 'mu'}">${sub || ''}</span></div>`;
    body = `<div class="kpis">${K('Revenue · ' + v.latest_quarter, '₹' + fmt(q.revenue, 0) + ' cr', pct(q.revenue_yoy) + ' YoY', cls(q.revenue_yoy))}
    ${K('Op. margin', fmt(q.opm, 1) + '%', q.opm_yoy_bps == null ? '' : `${q.opm_yoy_bps > 0 ? '+' : ''}${fmt(q.opm_yoy_bps, 0)} bps YoY`, cls(q.opm_yoy_bps))}
    ${K('PAT', '₹' + fmt(q.pat, 0) + ' cr', pct(q.pat_yoy) + ' YoY', cls(q.pat_yoy))}
    ${K(f.label.replace('Mar ', 'FY') + ' revenue', '₹' + fmt(f.revenue, 0), pct(f.revenue_growth) + ' YoY', cls(f.revenue_growth))}
    ${K('ROCE', v.roce == null ? '—' : fmt(v.roce, 1) + '%', 'return on capital')}
    ${K('Debt / equity', v.de == null ? '—' : fmt(v.de, 2) + '×', v.de > 1 ? 'leveraged' : 'comfortable', v.de > 1 ? 'dn' : 'up')}</div>`;
  } else if (k === 'trajectory') {
    body = trajChart(v) + `<div class="kpis" style="margin:12px 0 4px"><div class="kpi"><small>Revenue CAGR</small><b>${v.rev_cagr == null ? '—' : fmt(v.rev_cagr, 1) + '%'}</b><span class="mu">${v.fy.length - 1} yrs</span></div><div class="kpi"><small>Profit CAGR</small><b>${v.pat_cagr == null ? '—' : fmt(v.pat_cagr, 1) + '%'}</b><span class="mu">${v.fy.length - 1} yrs</span></div><div class="kpi"><small>Margin shift</small><b class="${cls(v.opm_change_bps)}">${v.opm_change_bps == null ? '—' : (v.opm_change_bps > 0 ? '+' : '') + fmt(v.opm_change_bps, 0)}</b><span class="mu">bps</span></div></div>` + flagsHTML(v.flags);
  } else if (k === 'balance') {
    const de = v.de.filter(x => x != null), wc = v.wc;
    body = `<div class="kpis"><div class="kpi"><small>Debt / equity</small><b>${de.length ? fmt(de[de.length - 1], 2) : '—'}×</b><span>${spark(de, 70, 18, de[de.length - 1] <= de[0])}</span></div><div class="kpi"><small>Interest cover</small><b class="${v.interest_cover != null && v.interest_cover < 3 ? 'dn' : ''}">${v.interest_cover ?? '—'}×</b><span class="mu">op. profit / interest</span></div><div class="kpi"><small>Cash cycle</small><b>${wc ? fmt(wc.ccc.filter(x => x != null).slice(-1)[0], 0) : '—'} d</b><span>${wc ? spark(wc.ccc.filter(x => x != null), 70, 18, false) : ''}</span></div></div>` + `<div style="margin-top:10px">${flagsHTML(v.flags)}</div>`;
  } else if (k === 'cash') {
    body = cashChart(v) + `<div class="note">${esc(v.fcf_note)} ${v.cum_conversion != null ? `Cumulative conversion: <b class="${v.cum_conversion < .75 ? 'dn' : 'up'}">${v.cum_conversion}×</b>` : ''}</div><div style="margin-top:8px">${flagsHTML(v.flags)}</div>`;
  } else if (k === 'guidance') {
    const sb = v.scoreboard.filter(x => x.status !== 'pending'), pend = v.scoreboard.filter(x => x.status === 'pending');
    const tally = ['delivered', 'near', 'missed'].map(s => `<span class="pill"><b class="${s === 'delivered' ? 'up' : s === 'missed' ? 'dn' : ''}">${sb.filter(x => x.status === s).length}</b> ${s}</span>`).join(' ');
    const one = x => {
      const range = x.hi != null && x.hi !== x.lo ? `${x.lo}–${x.hi}` : `${x.lo}`;
      return `<div class="sb"><div class="h"><b>${esc(x.target)} · ${MET[x.metric] || x.metric}</b><span class="st-${x.status}">${x.status}</span></div>${band(x)}
      <div class="meta"><span>Promised ${range}%${x.history?.length ? ' (restated ' + x.history.length + '×)' : ''}</span><span>${x.actual != null ? `Actual <b class="${x.status === 'missed' ? 'dn' : x.status === 'delivered' ? 'up' : ''}">${x.actual}%</b>` : 'Not reported yet'}</span></div>
      <details><summary>What management said · ${esc(x.call)} call</summary><q>${esc(x.quote)}</q></details></div>`;
    };
    body = `<div style="margin-bottom:12px">${tally} <span class="note">last ${v.calls.length} calls · quotes verified against transcript: ${v.meta.quotes_verified}</span></div>` + sb.map(one).join('') +
      (pend.length ? `<div class="sec-h" style="margin:16px 0 4px"><b>Still to be proven</b></div>${pend.map(one).join('')}` : '') +
      (v.capex?.length ? `<div class="note" style="margin-top:12px">Capex guided: ${v.capex.slice(0, 2).map(c => `₹${fmt(c.value)} cr for ${esc(c.target)}`).join(' · ')}</div>` : '');
  } else if (k === 'narrative') {
    body = v.map(n => `<div class="nv"><span class="v ${n.verdict}">${n.verdict === 'diverges' ? 'Diverges' : 'Agrees'}</span><b>${esc(n.topic)}</b>
      ${n.call ? `<div class="said">“${esc(n.said)}” <span class="note">— ${esc(n.call)} call</span></div>` : `<div class="real" style="margin:6px 0">${esc(n.said)}</div>`}<div class="real"><b>Numbers:</b> ${esc(n.reality)}</div></div>`).join('');
  } else if (k === 'bullbear') {
    const li = a => a.map(x => `<li>${esc(x.point)}<small>${esc(x.evidence)}</small></li>`).join('') || '<li class="mu">Nothing strong enough to claim.</li>';
    body = `<div class="bb"><h5 class="up">Bull</h5><ul>${li(v.bull)}</ul><h5 class="dn">Bear</h5><ul>${li(v.bear)}</ul><div class="note">Built by ${esc(v.by)}.</div></div>`;
  }
  return `<div class="blk"><h4>${T}</h4>${body}</div>`;
}
function takeaway(r) {
  const S_ = r.sections, fl = [];
  (S_.narrative || []).filter(n => n.verdict === 'diverges').forEach(n => fl.push(['red', `${n.topic}: ${n.reality}`]));
  [S_.trajectory, S_.balance, S_.cash].forEach(s => s?.flags?.forEach(f => fl.push(f)));
  const rank = { red: 0, amber: 1, green: 2 };
  return fl.sort((a, b) => rank[a[0]] - rank[b[0]]).slice(0, 3);
}
function researchHTML(r, order) {
  const tk = takeaway(r), g = r.grounding || {};
  const srcs = g.sources || [], ar = srcs.find(x => x.startsWith('Annual')), nc = srcs.filter(x => x.startsWith('Concall')).length;
  const gl = [ar ? ar.replace('Annual report · Financial Year', 'Annual report FY').replace('Annual report · ', 'Annual report ') : null, nc ? `${nc} concall transcript${nc > 1 ? 's' : ''}` : null, 'statement tables'].filter(Boolean).join(' · ');
  const head = `<div class="rh"><h2>${esc(r.name)}</h2><div class="src">Primary sources only: ${esc(gl)}.${g.llm ? ` Synthesis by ${esc(g.llm)} model.` : ' No LLM key: computed numbers and verified quotes only.'}</div></div>`;
  const tkh = tk.length && (order || ORDER).filter(k => r.sections[k]).length >= 5 ? `<div class="blk"><h4>Read first</h4>${flagsHTML(tk)}</div>` : '';
  const keys = (order || ORDER).filter(k => r.sections[k]);
  return head + tkh + keys.map(k => section(k, r.sections[k], r)).join('');
}

/* ---------------- sheet ---------------- */
function openSheet(html) { $('#sbody').innerHTML = html; $('#sheet').classList.add('on'); $('#sbg').classList.add('on'); $('#sbody').scrollTop = 0; }
function closeSheet() { $('#sheet').classList.remove('on'); $('#sbg').classList.remove('on'); }
$('#sbg').onclick = closeSheet; $('#sx').onclick = closeSheet;
(() => { let y0 = null; const g = $('#sheet .grab'); g.addEventListener('touchstart', e => y0 = e.touches[0].clientY); g.addEventListener('touchend', e => { if (y0 != null && e.changedTouches[0].clientY - y0 > 60) closeSheet(); y0 = null; }); })();
async function openResearch(sym) {
  openSheet(`<div class="rh"><h2>${esc(sym)}</h2><div class="src">Reading annual report, concall transcripts and statement tables…</div></div><div class="skel"></div><div class="skel"></div><div class="skel"></div>`);
  try {
    const r = await api('/api/research/' + encodeURIComponent(sym));
    openSheet(researchHTML(r) + `<div class="actions"><button class="btn pri" id="askf">Ask a follow-up</button></div>`);
    $('#askf').onclick = () => { closeSheet(); S.ctx = { symbol: r.symbol, name: r.name }; go('ask'); };
  } catch (e) { openSheet(`<div class="err" style="margin-top:30px">${esc(e.message)}<br><small>Try another ticker.</small></div>`); }
}

/* ---------------- Ask ---------------- */
const SUGG = [['What changed today?', 'digest of your book'], ['Anything unusual in prices or volume?', 'your thresholds'], ['Nimbus — promised vs delivered', 'guidance scoreboard'], ['Is Halcyon’s balance sheet a problem?', 'leverage & cover'], ['Brightfield cash quality', 'profit → cash']];
function renderAsk() {
  const el = $('#t-ask');
  const ex = S.meta?.data?.mode !== 'demo' ? [['What changed today?', 'digest of your book'], ['Anything unusual in prices or volume?', 'your thresholds'], ['Reliance guidance vs delivery', 'last 4 calls'], ['HAL bull vs bear', 'ad-hoc research']] : SUGG;
  if (!S.thread.length) {
    el.innerHTML = `<div class="empty"><h2>Ask FINN<br>anything about your book.</h2><p>Plain language, or tap the mic. Answers come back as cards, not paragraphs.</p>
    <p>Historical research: <a href="/examples/#/research/INFY">Infosys</a> · <a href="/examples/#/research/WIPRO">Wipro</a></p><div class="sugg">${ex.map(([q, s]) => `<button data-q="${esc(q)}">${esc(q)}<span>${esc(s)}</span></button>`).join('')}</div></div>`;
    $$('[data-q]', el).forEach(b => b.onclick = () => ask(b.dataset.q));
  } else {
    el.innerHTML = `<div class="thread">${S.thread.map(m => m.role === 'u' ? `<div class="msg u">${esc(m.text)}</div>` : `<div class="msg a">${m.html}</div>`).join('')}</div><div style="height:120px"></div>`;
    bindCards(el); $$('[data-q]', el).forEach(b => b.onclick = () => ask(b.dataset.q)); $$('[data-sym]', el).forEach(b => b.onclick = () => openResearch(b.dataset.sym));
  }
  const cc = $('#ctxchip'); cc.innerHTML = S.ctx ? `<span class="pill">Context: <b>${esc(S.ctx.name)}</b> <button id="cx" style="margin-left:4px;color:var(--mu)">✕</button></span>` : '';
  if (S.ctx) $('#cx').onclick = () => { S.ctx = null; renderAsk(); };
}
async function ask(q) {
  q = (q || '').trim(); if (!q) return;
  $('#q').value = '';
  S.thread.push({ role: 'u', text: q }); renderAsk();
  const th = $('.thread'); th.insertAdjacentHTML('beforeend', '<div class="msg a" id="typing"><div class="typing"><i></i><i></i><i></i></div></div>'); window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  let html;
  try {
    const r = await api('/api/ask', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ q, symbol: S.ctx?.symbol, rules: rulesBody() }) });
    if (r.intent === 'research') {
      S.ctx = { symbol: r.symbol, name: r.name };
      const order = ORDER.filter(k => r.ask.includes(k));
      html = researchHTML(r.research, order) + followups(r.symbol);
    } else if (r.intent === 'digest') {
      html = `<div class="rh"><h2 style="font-size:22px">${esc(r.title)}</h2><div class="src">${r.pulse.total} filings · ${r.pulse.now} need you · ${r.pulse.look} worth a look · routine hidden</div></div>${r.items.map(card).join('') || '<div class="err">Nothing of note.</div>'}`;
    } else if (r.intent === 'alerts') {
      html = `<div class="rh"><h2 style="font-size:22px">${esc(r.title)}</h2><div class="src">Your rules: price ±${r.rules.price_move_pct}% · volume ${r.rules.volume_mult}× average</div></div>` + (r.alerts.map(a => `<button class="card ${a.severity === 'high' ? 'now' : 'look'}" data-sym="${esc(a.symbol)}" style="width:100%;text-align:left"><div class="top"><span class="tkr">${esc(a.symbol)}</span><span class="cat">${a.kind}</span></div><h3>${esc(a.title)}</h3><div class="why">${esc(a.detail)}</div></button>`).join('') || '<div class="err">Nothing has crossed your thresholds.</div>');
    } else html = `<div class="blk"><h4>${esc(r.title || '')}</h4>${esc(r.message || '')}</div>`;
  } catch (e) { html = `<div class="err">${esc(e.message)}</div>`; }
  S.thread.push({ role: 'a', html }); renderAsk();
  const last = $$('.msg.a').pop(); if (last) last.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function followups(sym) {
  const f = ['Promised vs delivered', 'Bull vs bear', 'Cash quality', 'Balance sheet', 'Trajectory'];
  return `<div class="chips">${f.map(x => `<button class="chip" data-q="${esc(x)}">${x}</button>`).join('')}</div>`;
}
$('#send').onclick = () => ask($('#q').value);
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter') ask($('#q').value); });
(() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition, mic = $('#mic');
  if (!SR) { mic.style.display = 'none'; return; }
  let rec = null;
  mic.onclick = () => {
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = 'en-IN'; rec.interimResults = true;
    mic.classList.add('rec');
    rec.onresult = e => { const t = [...e.results].map(r => r[0].transcript).join(' '); $('#q').value = t; if (e.results[e.results.length - 1].isFinal) { rec.stop(); ask(t); } };
    rec.onend = () => { mic.classList.remove('rec'); rec = null; };
    rec.onerror = () => { mic.classList.remove('rec'); rec = null; };
    rec.start();
  };
})();

/* ---------------- Rules ---------------- */
async function renderRules() {
  const el = $('#t-rules'), r = S.rules, cats = S.meta?.categories || [];
  const st = await api('/api/stats').catch(() => null);
  const calls = st ? st.llm.calls.cheap + st.llm.calls.strong : 0;
  el.innerHTML = `<div class="pulse">${d.data.mode === 'snapshot' ? '<p class="note">Portfolio snapshot · '+esc(d.data.asof.replace('T',' ').slice(0,16))+' IST · Past '+winLabel+'</p>' : ''}<div class="big">You decide what’s <em>unusual</em>.</div><div class="sub">FINN watches your end-of-day data and filings against these rules.</div></div>
  <div class="rule"><div class="l"><b>Price move</b><span id="v1">±${r.price_move_pct}%</span></div><p>Alert when a stock closes beyond this in a day.</p><input type="range" id="r1" min="1" max="10" step=".5" value="${r.price_move_pct}"></div>
  <div class="rule"><div class="l"><b>Volume spike</b><span id="v2">${r.volume_mult}×</span></div><p>Alert when volume exceeds this multiple of its 20-day average.</p><input type="range" id="r2" min="1.2" max="5" step=".1" value="${r.volume_mult}"></div>
  <div class="rule"><div class="l"><b>Filing types</b><span style="font-size:13px;color:var(--mu)">tap to cycle</span></div><p><b style="color:var(--ac)">Watch</b> raises priority and triggers alerts · <b>Normal</b> · <b>Mute</b> buries it.</p>
   <div class="cats">${cats.map(c => { const v = r.cats[c] || 'normal'; return `<button class="cb ${v}" data-c="${c}"><span>${lab(c)}</span><small>${v}</small></button>`; }).join('')}</div></div>
  <div class="rule"><div class="l"><b>Push notifications</b></div><p>Get a system notification the moment a high-severity trigger fires while FINN is open.</p><button class="btn" id="np">${'Notification' in window ? (Notification.permission === 'granted' ? 'Enabled ✓' : 'Enable notifications') : 'Not supported here'}</button> <button class="btn ghost" id="tt">Send a test</button></div>
  <div class="rule" style="border:0"><div class="l"><b>Efficiency</b></div><p>Rules first, regex before LLM, cheap model for bulk, strong model only for synthesis, everything cached.</p>
   <div class="eff"><div><b>${calls}</b><small>LLM calls</small></div><div><b>${st ? st.llm.cached : 0}</b><small>LLM cache hits</small></div><div><b>${st ? st.cache.hit : 0}</b><small>data cache hits</small></div></div>
   <div class="note">Mode: ${esc(st?.provider || 'no LLM key — deterministic')} · data: ${esc(st?.data?.mode || '')}</div><div class="actions"><button class="btn ghost" id="rs">Reset rules</button></div></div>`;
  const bind = (id, vid, key, f) => { const i = $(id, el); i.oninput = () => { S.rules[key] = +i.value; $(vid, el).textContent = f(i.value); saveRules(); }; i.onchange = () => { S.digest = null; }; };
  bind('#r1', '#v1', 'price_move_pct', v => `±${v}%`); bind('#r2', '#v2', 'volume_mult', v => `${v}×`);
  $$('.cb', el).forEach(b => b.onclick = () => { const o = ['normal', 'watch', 'mute'], c = b.dataset.c; const n = o[(o.indexOf(S.rules.cats[c] || 'normal') + 1) % 3]; S.rules.cats[c] = n; saveRules(); b.className = 'cb ' + n; $('small', b).textContent = n; S.digest = null; });
  $('#np', el).onclick = async () => { if ('Notification' in window) { await Notification.requestPermission(); renderRules(); } };
  $('#tt', el).onclick = () => notifyTest();
  $('#rs', el).onclick = () => { S.rules = JSON.parse(JSON.stringify(DEF)); saveRules(); S.digest = null; renderRules(); };
}
function notifyTest() { toast('Test alert · QUANTACKT +5.6%', 'This is how a triggered alert looks.'); if ('Notification' in window && Notification.permission === 'granted') new Notification('FINN · test alert', { body: 'QUANTACKT +5.6% on 3.4× volume' }); }

/* ---------------- nav ---------------- */
function go(t) {
  $$('.tab').forEach(x => x.classList.toggle('on', x.id === 't-' + t));
  $$('nav.bar button').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  $('#composer').classList.toggle('on', t === 'ask');
  if (t === 'ask') renderAsk(); if (t === 'rules') renderRules(); if (t === 'today' && !S.digest) loadToday(); if (t === 'book' && !S.digest) loadToday();
  window.scrollTo({ top: 0 });
}
$$('nav.bar button').forEach(b => b.onclick = () => { if (b.dataset.t === 'today' && $('#t-today').classList.contains('on') === false) { go('today'); if (!S.digest) loadToday(); } else go(b.dataset.t); });
(async function init() {
  try {
    S.meta = await api('/api/meta');
    if (!Object.keys(S.rules.cats || {}).length) { S.rules.cats = {}; (S.meta.defaults.watch || []).forEach(c => S.rules.cats[c] = 'watch'); saveRules(); }
    const demo = S.meta.data.mode === 'demo';
    $('#badge').className = 'badge ' + (demo ? 'demo' : ''); $('#badge span').textContent = demo ? 'Demo data' : S.meta.data.mode === 'snapshot' ? 'Saved portfolio' : 'Live';
    $('#badge').title = demo ? 'Synthetic data (fictional companies). ' + (S.meta.data.reason || '') : 'Live NSE / Yahoo / screener.in';
  } catch (e) { }
  loadToday();
})();
