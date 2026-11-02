// FINN prototype: one app, hash-routed. Company facts live in data/*.json; this file is layout + state only.
(() => {
  const view = document.getElementById('view');
  const navLinks = [...document.querySelectorAll('.nav a')];

  // ---- tiny helpers -------------------------------------------------------
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === false || v == null) continue;
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v;
      else n.setAttribute(k, v === true ? '' : v);
    }
    kids.flat().forEach(c => { if (c != null && c !== false) n.append(c); });
    return n;
  };
  const utc = iso => new Date(iso + 'T00:00:00Z');
  const fmtDate = iso => new Intl.DateTimeFormat('en-GB',
    { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(utc(iso));
  const monthName = iso => new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' }).format(utc(iso));
  const num = (n, signed) => (n < 0 ? '−' : signed && n > 0 ? '+' : '') + Math.abs(n).toFixed(1);
  const pct = n => num(n) + '%';
  const range = (a, b) => (a < 0 || b < 0) ? `${num(a, true)}% to ${num(b, true)}%` : `${num(a)}–${num(b)}%`;
  const getJSON = async path => {
    const r = await fetch(path, { cache: 'no-store' });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  };

  // Source link. A PDF source opens at its page (#page=N, added exactly once);
  // an HTML source uses a text fragment so supporting browsers highlight the passage.
  const href = s => s.pdf
    ? s.pdf.split('#')[0] + (s.page ? `#page=${s.page}` : '')
    : s.url + (s.find ? '#:~:text=' + encodeURIComponent(s.find).replace(/-/g, '%2D') : '');
  const link = (s, cls = 'src') => el('a', { class: cls, href: href(s), target: '_blank', rel: 'noopener' },
    s.label, s.page ? ` · p. ${s.page}` : '', ' ↗');
  const hint = s => s.hint ? el('p', { class: 'hint', text: s.hint }) : null;

  // ---- state: the time window survives navigation and reloads --------------
  const WINDOWS = { '6h': 6, '24h': 24 };
  let win = '24h';
  try { const s = localStorage.getItem('finn.window'); if (WINDOWS[s]) win = s; } catch (_) {}
  const setWindow = w => { win = w; try { localStorage.setItem('finn.window', w); } catch (_) {} };

  let alerts = { updatedAt: null, items: [] };
  const examples = new Map();   // ticker -> card data

  // ---- Dashboard (today's alerts only) -------------------------------------
  function ago(iso) {
    const m = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
    return m < 60 ? `${m}m ago` : `${Math.floor(m / 60)}h ago`;
  }
  function dashboard() {
    const body = el('div');
    const draw = () => {
      const cutoff = Date.now() - WINDOWS[win] * 3600e3;
      const items = alerts.items.filter(i => Date.parse(i.at) >= cutoff)
        .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
      body.replaceChildren(
        el('p', { class: 'count' }, el('b', { text: String(items.length) }),
          ` ${items.length === 1 ? 'item' : 'items'} in the last ${win}`),
        items.length ? el('ul', { class: 'list' }, items.map(i => el('li', { class: 'item' },
          el('div', { class: 'meta' }, el('b', { text: i.ticker }), el('span', { class: 'chip', text: i.category }),
            el('span', { text: ago(i.at) })),
          el('p', { text: i.headline }),
          i.source ? link(i.source) : null)))
          : el('div', { class: 'empty' },
            el('strong', { text: alerts.updatedAt ? 'Nothing new in this window' : 'No live feed is connected yet' }),
            el('span', { text: alerts.updatedAt
              ? 'No portfolio filings or unusual moves in this window.'
              : 'This prototype has no live announcements or prices, so nothing here is real-time. Past examples are under Research.' })));
    };
    const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Time window' },
      Object.keys(WINDOWS).map(w => {
        const b = el('button', { type: 'button', 'data-window': w, 'aria-pressed': String(w === win), text: w });
        b.addEventListener('click', () => {
          setWindow(w);
          seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.window === w)));
          draw();
        });
        return b;
      }));
    draw();
    return [el('h1', { text: 'Portfolio' }), el('p', { class: 'sub', text: 'What changed, newest first' }), seg, body];
  }

  // ---- Research: choose a historical example -------------------------------
  function research() {
    return [el('h1', { text: 'Research' }),
      el('p', { class: 'notice', text: 'Historical examples. These are past announcements, not today’s alerts.' }),
      el('div', { class: 'picks' }, [...examples.values()].map(d => el('a', { class: 'pick', href: `#/research/${d.ticker}` },
        el('div', { class: 't' }, el('span', { text: d.name }), el('span', { text: d.periodLabel })),
        el('div', { class: 'm', text: d.claim.metric }))))];
  }

  // ---- The claim card -------------------------------------------------------
  function card(d) {
    const { claim, timeline } = d;
    const v = claim.result.value, lo = claim.guidance.low, hi = claim.guidance.high;
    const cmp = claim.marker || { value: v, label: pct(v) };      // the figure compared with the forecast
    const month = monthName(claim.guidance.asOf);                  // derived, never hard-coded
    const min = Math.min(lo, cmp.value) - 0.5, max = Math.max(hi, cmp.value) + 0.5;
    const at = x => ((x - min) / (max - min) * 100) + '%';
    const where = x => x >= lo && x <= hi ? 'Inside' : x > hi ? 'Above' : 'Below';

    const pinLabel = claim.marker && claim.marker.source
      ? el('a', { class: 'pinlabel', href: href(claim.marker.source), target: '_blank', rel: 'noopener',
          style: `left:${at(cmp.value)}`, 'data-figure': 'marker' }, cmp.label, ' ↗')
      : el('span', { class: 'pinlabel', style: `left:${at(cmp.value)}`, text: cmp.label });
    const scale = el('div', { class: 'scale', role: 'img',
        'aria-label': `${cmp.label} on a scale showing the ${month} range ${range(lo, hi)}` },
      el('div', { class: 'track' }),
      el('div', { class: 'band', style: `left:${at(lo)};width:calc(${at(hi)} - ${at(lo)})` }),
      el('div', { class: 'pin', style: `left:${at(cmp.value)}` }), pinLabel,
      ...[lo, hi].map(x => el('span', { class: 'tick', style: `left:${at(x)}`, text: pct(x) })));

    const events = [...timeline].sort((a, b) => a.date.localeCompare(b.date));
    const list = el('ol', { class: 'changes', id: 'changes', hidden: true },
      events.map(e => el('li', { class: 'ev' },
        el('div', { class: 'd' }, el('time', { datetime: e.date, text: fmtDate(e.date) }), el('em', { text: e.kind })),
        el('h3', {}, el('span', { text: e.title }), el('span', { text: e.figure })),
        el('p', { text: e.detail }), link(e.source), hint(e.source))),
      d.timelineNote ? el('li', { class: 'note', text: d.timelineNote }) : null);

    const btn = el('button', { class: 'btn', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'changes' },
      'What changed?', el('span', { class: 'chev', 'aria-hidden': 'true', text: '⌄' }));
    btn.addEventListener('click', () => {
      const open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', String(!open));
      list.hidden = open;
      if (!open) list.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });

    const basis = claim.basisNotes ? el('aside', { class: 'basis' }, el('h2', { text: 'Check the basis' }),
      claim.basisNotes.map(t => el('p', { text: t })),
      claim.marker ? el('p', {}, el('b', { text: `${cmp.label}: ` }), `${where(cmp.value).toLowerCase()} the ${month} range`) : null,
      claim.marker && claim.marker.source ? link(claim.marker.source) : null) : null;

    return [el('a', { class: 'back', href: '#/research', text: '← Research' }),
      el('article', { class: 'card' },
        el('div', { class: 'eyebrow' }, el('b', { text: d.ticker }), `${d.name} · ${d.periodLabel}`,
          el('span', { class: 'badge', text: d.badge })),
        el('p', { class: 'big' }, num(v), el('small', { text: '%' })),
        claim.result.note ? el('span', { class: 'rnote', text: claim.result.note }) : null,
        el('p', { class: 'metric', text: claim.metric }),
        el('p', { class: 'period', text: `${claim.period} · reported ${fmtDate(claim.result.asOf)}` }),
        link(claim.result.source),
        el('div', { class: 'compare' },
          el('div', { class: 'row' }, el('span', { class: 'k', text: `${month} guidance` }),
            el('span', { class: 'v', text: range(lo, hi) })),
          el('p', { class: 'asof', text: `Set ${fmtDate(claim.guidance.asOf)}` }),
          link(claim.guidance.source), scale,
          el('div', { class: 'verdict' + (where(cmp.value) === 'Inside' ? '' : ' out') }, el('i'),
            `${where(cmp.value)} the ${month} range`)),
        basis, btn, list)];
  }

  // ---- router ---------------------------------------------------------------
  function route() {
    const parts = (location.hash.replace(/^#\/?/, '') || '').split('/').filter(Boolean);
    const section = parts[0] === 'research' ? 'research' : 'dash';
    navLinks.forEach(a => a.dataset.route === section
      ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
    let nodes;
    if (section === 'research' && parts[1]) {
      const d = examples.get(parts[1].toUpperCase());
      nodes = d ? card(d) : [el('div', { class: 'err', text: `No historical example for ${parts[1]}.` }),
        el('a', { class: 'back', href: '#/research', text: '← Research' })];
      document.title = d ? `FINN · ${d.ticker} claim check` : 'FINN';
    } else if (section === 'research') { nodes = research(); document.title = 'FINN · Research'; }
    else { nodes = dashboard(); document.title = 'FINN · Portfolio'; }
    view.replaceChildren(...nodes);
    window.scrollTo(0, 0);
  }

  (async () => {
    try {
      const [a, tickers] = await Promise.all([getJSON('data/alerts.json').catch(() => alerts), getJSON('data/examples.json')]);
      alerts = a;
      for (const t of tickers) { const d = await getJSON(`data/${t}.json`); examples.set(d.ticker.toUpperCase(), d); }
      window.addEventListener('hashchange', route);
      route();
    } catch (e) {
      view.replaceChildren(el('div', { class: 'err' }, el('strong', { text: 'Couldn’t load FINN. ' }),
        el('span', { text: e.message + '. If you opened index.html directly, run serve.py instead.' })));
    }
  })();
})();
