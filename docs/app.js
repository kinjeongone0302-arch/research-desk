'use strict';

/* ═══════════ 공통 ═══════════ */
const $ = (s, r) => (r || document).querySelector(s);
const el = (h) => { const t = document.createElement('template'); t.innerHTML = h.trim(); return t.content.firstElementChild; };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const bp = (v, d = 1) => v == null ? '—' : v.toFixed(d);
const sgn = (v, d = 1) => v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(d);
const cls = (v, inv) => v == null ? 'flat' : (inv ? (v > 0 ? 'down' : v < 0 ? 'up' : 'flat') : (v > 0 ? 'up' : v < 0 ? 'down' : 'flat'));
const dayfmt = (s) => s ? s.slice(2).replace(/-/g, '.') : '—';

function won(v) {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(a >= 1e13 ? 1 : 2) + '조';
  if (a >= 1e8) return (v / 1e8).toFixed(0) + '억';
  return v.toLocaleString();
}

/* 시계열이 듬성듬성해서 "N일 전 값" 은 그 날짜 이하의 마지막 관측치로 잡는다 */
function asOf(series, daysAgo) {
  if (!series.length) return null;
  const last = new Date(series[series.length - 1].d);
  const t = new Date(last.getTime() - daysAgo * 864e5).toISOString().slice(0, 10);
  let hit = null;
  for (const p of series) { if (p.d <= t) hit = p; else break; }
  return hit;
}
function chg(series, daysAgo) {
  const now = series[series.length - 1], was = asOf(series, daysAgo);
  return (now && was && was !== now) ? now.bp - was.bp : null;
}

/* ═══════════ 차트 (외부 라이브러리 없이 인라인 SVG) ═══════════ */
/* 체결 기반 시계열은 관측이 없는 날이 많다. 그 구간을 실선으로 이으면 "그동안 평평했다"로
   읽히므로, 간격이 벌어진 구간은 얇은 점선으로 끊어 표시한다. 점이 실제 관측이다. */
const GAP_DAYS = 7;

function lineChart(node, series, opt) {
  opt = opt || {};
  node.innerHTML = '';
  if (!series || series.length < 2) { node.innerHTML = '<div class="empty">표시할 체결이 부족합니다</div>'; return; }
  const W = 640, H = opt.h || 210, L = 46, R = 10, T = 12, B = 24;
  const xs = series.map(p => new Date(p.d).getTime());
  const ys = series.map(p => p.bp);
  const refs = (opt.refs || []).filter(r => r.bp != null);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys, ...refs.map(r => r.bp));
  let y1 = Math.max(...ys, ...refs.map(r => r.bp));
  const pad = (y1 - y0) * .15 || Math.max(1, y1 * .05);
  y0 = Math.max(0, y0 - pad); y1 = y1 + pad;
  const X = t => L + (W - L - R) * (x1 === x0 ? .5 : (t - x0) / (x1 - x0));
  const Y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0 || 1));

  let grid = '';
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4, y = Y(v);
    grid += `<line x1="${L}" y1="${y}" x2="${W - R}" y2="${y}" stroke="var(--line2)"/>`
      + `<text x="${L - 7}" y="${y + 3.5}" text-anchor="end" font-size="10" fill="var(--faint)" class="num">${v.toFixed(0)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const t = x0 + (x1 - x0) * i / 4;
    grid += `<text x="${X(t).toFixed(1)}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}" font-size="10" fill="var(--faint)" class="num">${new Date(t).toISOString().slice(2, 7).replace('-', '.')}</text>`;
  }

  /* 촘촘한 구간(실선)과 빈 구간(점선)을 나눠 그린다 */
  const solid = [], dashed = [];
  let run = [0];
  for (let i = 1; i < series.length; i++) {
    const gap = (xs[i] - xs[i - 1]) / 864e5;
    if (gap <= GAP_DAYS) { run.push(i); continue; }
    if (run.length > 1) solid.push(run);
    dashed.push([i - 1, i]);
    run = [i];
  }
  if (run.length > 1) solid.push(run);
  const path = idx => idx.map((j, n) => `${n ? 'L' : 'M'}${X(xs[j]).toFixed(1)},${Y(ys[j]).toFixed(1)}`).join('');

  const refLines = refs.map(r => `<line x1="${L}" y1="${Y(r.bp).toFixed(1)}" x2="${W - R}" y2="${Y(r.bp).toFixed(1)}"
      stroke="var(--faint)" stroke-width="1" stroke-dasharray="5 4" opacity=".55"/>
    <text x="${W - R - 2}" y="${Y(r.bp) - 4}" text-anchor="end" font-size="9.5" fill="var(--faint)">${esc(r.label)} ${r.bp.toFixed(0)}</text>`).join('');

  const dots = series.length <= 400
    ? series.map((p, i) => `<circle cx="${X(xs[i]).toFixed(1)}" cy="${Y(p.bp).toFixed(1)}" r="1.7" fill="var(--accent)" opacity=".85"/>`).join('')
    : '';

  node.appendChild(el(`<svg viewBox="0 0 ${W} ${H}" style="height:${H}px">
    ${grid}${refLines}
    ${dashed.map(d => `<path d="${path(d)}" fill="none" stroke="var(--accent)" stroke-width="1" stroke-dasharray="3 3" opacity=".45"/>`).join('')}
    ${solid.map(r => `<path d="${path(r)}" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round"/>`).join('')}
    ${dots}
    <circle cx="${X(xs[xs.length - 1]).toFixed(1)}" cy="${Y(ys[ys.length - 1]).toFixed(1)}" r="3.2" fill="var(--accent)"/>
  </svg>`));
}

function curveChart(node, pts, dec) {
  node.innerHTML = '';
  if (!pts || pts.length < 2) { node.innerHTML = '<div class="empty">체결 만기가 부족합니다</div>'; return; }
  const W = 640, H = 210, L = 46, R = 12, T = 12, B = 28;
  const ys = pts.map(p => p.bp);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  const pad = (y1 - y0) * .18 || Math.max(1, y1 * .06);
  y0 = Math.max(0, y0 - pad); y1 += pad;
  const X = i => L + (W - L - R) * (pts.length === 1 ? .5 : i / (pts.length - 1));
  const Y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0 || 1));
  let g = '';
  for (let i = 0; i <= 4; i++) { const y = Y(y0 + (y1 - y0) * i / 4); g += `<line x1="${L}" y1="${y}" x2="${W - R}" y2="${y}" stroke="var(--line2)"/><text x="${L - 7}" y="${y + 3.5}" text-anchor="end" font-size="10" fill="var(--faint)" class="num">${(y0 + (y1 - y0) * i / 4).toFixed(dec || 0)}</text>`; }
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(p.bp).toFixed(1)}`).join('');
  const dots = pts.map((p, i) => `<circle cx="${X(i).toFixed(1)}" cy="${Y(p.bp).toFixed(1)}" r="3" fill="var(--accent)"/>
    <text x="${X(i).toFixed(1)}" y="${Y(p.bp) - 9}" text-anchor="middle" font-size="10" font-weight="700" fill="var(--sub)" class="num">${p.bp.toFixed(dec || 0)}</text>
    <text x="${X(i).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="10.5" font-weight="700" fill="var(--faint)">${p.tenor}</text>
    ${p.n === '' ? '' : `<text x="${X(i).toFixed(1)}" y="${H + 5}" text-anchor="middle" font-size="9" fill="var(--faint)" class="num">n=${p.n}</text>`}`).join('');
  node.appendChild(el(`<svg viewBox="0 0 ${W} ${H + 8}" style="height:${H + 8}px">${g}<path d="${d}" fill="none" stroke="var(--accent)" stroke-width="1.8"/>${dots}</svg>`));
}

function spark(series, w = 76, h = 22) {
  if (!series || series.length < 2) return '';
  const ys = series.map(p => p.bp);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const d = series.map((p, i) => `${i ? 'L' : 'M'}${(w * i / (series.length - 1)).toFixed(1)},${(h - (h - 3) * ((p.bp - y0) / (y1 - y0 || 1)) - 1.5).toFixed(1)}`).join('');
  const rise = ys[ys.length - 1] >= ys[0];
  return `<svg viewBox="0 0 ${w} ${h}" style="width:${w}px;height:${h}px;display:inline-block;vertical-align:middle">
    <path d="${d}" fill="none" stroke="var(--${rise ? 'up' : 'down'})" stroke-width="1.4"/></svg>`;
}

function barChart(node, pts, market, unit) {
  node.innerHTML = '';
  if (!pts.length) { node.innerHTML = '<div class="empty">데이터 없음</div>'; return; }
  const W = 660, H = 230, L = 52, R = 10, T = 14, B = 34;
  const vmax = Math.max(...pts.map(p => p.v)) * 1.12;
  const bw = (W - L - R) / pts.length;
  const Y = v => T + (H - T - B) * (1 - v / (vmax || 1));
  let g = '';
  for (let i = 0; i <= 4; i++) { const v = vmax * i / 4, y = Y(v); g += `<line x1="${L}" y1="${y}" x2="${W - R}" y2="${y}" stroke="var(--line2)"/><text x="${L - 7}" y="${y + 3.5}" text-anchor="end" font-size="10" fill="var(--faint)" class="num">${market === 'US' ? usd(v) : won(v)}</text>`; }
  const bars = pts.map((p, i) => {
    const x = L + bw * i + bw * .16, w = bw * .68, y = Y(p.v);
    const c = p.hl ? 'var(--accent)' : 'var(--accent-line)';
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${(H - B - y).toFixed(1)}" rx="3" fill="${c}"/>
      <text x="${(x + w / 2).toFixed(1)}" y="${H - 20}" text-anchor="middle" font-size="9.5" fill="var(--faint)" class="num" transform="rotate(-32 ${(x + w / 2).toFixed(1)} ${H - 20})">${p.k}</text>`;
  }).join('');
  node.appendChild(el(`<svg viewBox="0 0 ${W} ${H}" style="height:${H}px">${g}${bars}</svg>`));
}

/* ═══════════ 탭 ═══════════ */
function openTab(id) {
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('on', p.id === 'tab-' + id));
  document.querySelectorAll('.navitem').forEach(b => b.classList.toggle('on', b.dataset.tab === id));
  $('#nav').classList.remove('open');
  if (location.hash.slice(1) !== id) history.replaceState(null, '', '#' + id);
  window.scrollTo(0, 0);
  const m = document.querySelector('main'); if (m) m.scrollTop = 0;
}
document.querySelectorAll('.navitem').forEach(b => b.onclick = () => openTab(b.dataset.tab));
$('#menuBtn').onclick = () => $('#nav').classList.toggle('open');
$('#themeToggle').onclick = () => {
  const dark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('rd-theme', dark ? 'dark' : 'light');
  $('#themeToggle').textContent = dark ? '라이트 모드' : '다크 모드';
  render();
};
(function () {
  const saved = localStorage.getItem('rd-theme');
  const dark = saved ? saved === 'dark' : true;
  document.documentElement.classList.toggle('dark', dark);
  $('#themeToggle').textContent = dark ? '라이트 모드' : '다크 모드';
})();

/* ═══════════ 데이터 ═══════════ */
let CDS = null, BL = null;

Promise.all([
  fetch('data/cds.json?t=' + Date.now()).then(r => r.json()).catch(() => null),
  fetch('data/backlog.json?t=' + Date.now()).then(r => r.json()).catch(() => null),
  fetch('data/bonds.json?t=' + Date.now()).then(r => r.json()).catch(() => null),
]).then(([c, b, bo]) => {
  CDS = c; BL = b; BOND = bo;
  $('#stamp').textContent = (c ? 'CDS ' + dayfmt(c.coverage.to) : '') + (b ? ' · 수주 ' + (b.generated_at || '').slice(2, 10).replace(/-/g, '.') : '');
  render();
  if (location.hash) openTab(location.hash.slice(1));
});

/* ═══════════ CDS 표 ═══════════ */
const SEL = { ai: null, sov: null, idx: null };

function cdsRows(group, keys) {
  return keys.map(n => {
    const v = group[n];
    return v && v.series && v.series.length ? { name: n, ...v } : null;
  }).filter(Boolean);
}

function cdsTable(node, rows, kind) {
  rows = rows.slice().sort((a, b) => (b.last_bp ?? -1) - (a.last_bp ?? -1));
  const body = rows.map(r => {
    const w = chg(r.series, 7), m = chg(r.series, 30), q = chg(r.series, 90);
    return `<tr data-n="${esc(r.name)}" class="${SEL[kind] === r.name ? 'on' : ''}">
      <td class="nm">${esc(r.name)}${r.branch === 'high' ? '<span class="sb" title="스프레드가 표준쿠폰 100bp를 넘는 구간">쿠폰↑</span>'
        : r.branch === 'mixed' ? '<span class="sb" title="기간 중 표준쿠폰 선을 넘나든 크레딧">쿠폰 교차</span>' : ''}</td>
      <td class="num" style="font-weight:800">${bp(r.last_bp)}</td>
      <td class="num ${cls(w)}">${sgn(w)}</td>
      <td class="num ${cls(m)}">${sgn(m)}</td>
      <td class="num ${cls(q)}">${sgn(q)}</td>
      <td>${spark(r.series.slice(-60))}</td>
      <td class="num" style="color:var(--faint)">${r.trades.toLocaleString()}</td>
      <td class="num" style="color:var(--faint)">${dayfmt(r.last)}</td>
    </tr>`;
  }).join('');
  node.innerHTML = `<table><thead><tr>
    <th>대상</th><th>5Y (bp)</th><th>1주</th><th>1개월</th><th>3개월</th><th>추이</th><th>체결</th><th>최근</th>
  </tr></thead><tbody>${body}</tbody></table>`;
  node.querySelectorAll('tr[data-n]').forEach(tr => tr.onclick = () => { SEL[kind] = tr.dataset.n; render(); });
}

function cdsCards(node, rows, n) {
  /* 카드는 체결량이 아니라 선언 순서대로 — 한국·오라클처럼 먼저 봐야 할 게 앞에 온다 */
  node.innerHTML = rows.slice(0, n).map(r => {
    const m = chg(r.series, 30);
    return `<button class="card" data-n="${esc(r.name)}">
      <div class="k">${esc(r.name)} <span class="pill">5Y</span></div>
      <div class="v num">${bp(r.last_bp)}<em>bp</em></div>
      <div class="d num ${cls(m)}">${sgn(m)}bp <span style="color:var(--faint);font-weight:600">1개월</span></div>
      <div class="n">체결 ${r.trades.toLocaleString()}건 · 최근 ${dayfmt(r.last)}</div>
    </button>`;
  }).join('');
  node.querySelectorAll('.card[data-n]').forEach(b => b.onclick = () => {
    const k = node.id.replace('Cards', ''); SEL[k] = b.dataset.n; render();
  });
}

function renderCdsGroup(kind, group, order, cardN) {
  const rows = cdsRows(group, order.filter(n => group[n]));
  if (!rows.length) return;
  if (!SEL[kind] || !group[SEL[kind]]) SEL[kind] = rows[0].name;
  const sel = rows.find(r => r.name === SEL[kind]);
  const C = $('#' + kind + 'Cards'), T = $('#' + kind + 'Table');
  if (C) cdsCards(C, rows, cardN);
  if (T) cdsTable(T, rows, kind);
  const ch = $('#' + kind + 'Chart');
  if (ch && sel) {
    $('#' + kind + 'ChartTitle').textContent = sel.name + ' 5Y CDS';
    const w = chg(sel.series, 7), m = chg(sel.series, 30);
    $('#' + kind + 'ChartSub').innerHTML = `${sel.series.length}개 관측 · 1주 ${sgn(w)}bp · 1개월 ${sgn(m)}bp`
      + (sel.quoted ? ` · 이 중 ${sel.quoted}건은 딜러 호가가 공시에 직접 실린 값` : '')
      + (sel.branch === 'high' ? ' · <b>표준쿠폰(100bp) 위에서 거래되는 크레딧</b>'
         : sel.branch === 'mixed' ? ' · <b>기간 중 표준쿠폰 선을 넘어선 크레딧</b>' : '');
    /* 기준선은 스케일이 맞을 때만. 국가 CDS(20~40bp)에 하이일드 지수(300bp)를 얹으면
       차트가 바닥에 눌려버린다 — 기업 크레딧 탭에서, 값이 시계열 범위 안에 들 때만 그린다. */
    const lo = Math.min(...sel.series.map(p => p.bp)), hi = Math.max(...sel.series.map(p => p.bp));
    const bench = kind !== 'ai' ? [] : ['CDX IG', 'CDX HY']
      .map(n => CDS.indices && CDS.indices[n] ? { label: n, bp: CDS.indices[n].last_bp } : null)
      .filter(r => r && r.bp != null && r.bp >= lo * 0.7 && r.bp <= hi * 1.3);
    lineChart(ch, sel.series, { id: kind, refs: bench });
  }
  const cv = $('#' + kind + 'Curve');
  if (cv && sel) curveChart(cv, sel.curve || []);
}

/* ═══════════ 수주잔고 ═══════════ */
let BLSEL = null, BLHI = -1;

function blList(q) {
  const s = (BL.stocks || []).filter(x => x.status === 'ok');
  if (!q) return s.slice().sort((a, b) => (b.yoy ?? -999) - (a.yoy ?? -999)).slice(0, 12);
  const t = q.trim().toLowerCase();
  return s.filter(x => x.name.toLowerCase().includes(t) || x.code.includes(t) || x.sector.toLowerCase().includes(t)).slice(0, 20);
}

function blDrop(q) {
  const d = $('#blDrop'), rows = blList(q);
  if (!rows.length) { d.innerHTML = '<div class="dropitem"><span>일치하는 종목이 없습니다</span></div>'; d.classList.add('on'); return; }
  d.innerHTML = rows.map((x, i) => `<div class="dropitem ${i === BLHI ? 'hi' : ''}" data-c="${x.code}">
    <b>${esc(x.name)}</b><span>${esc(x.sector)} · ${x.code}</span>
    <span class="r num ${cls(x.yoy)}">${x.yoy == null ? '' : sgn(x.yoy, 0) + '%'}</span></div>`).join('');
  d.classList.add('on');
  d.querySelectorAll('[data-c]').forEach(n => n.onmousedown = (e) => { e.preventDefault(); blPick(n.dataset.c); });
}

function blPick(code) {
  BLSEL = code; BLHI = -1;
  $('#blDrop').classList.remove('on');
  const x = BL.stocks.find(s => s.code === code);
  if (x) $('#blSearch').value = x.name;
  renderBacklog();
}

function renderBacklog() {
  if (!BL) return;
  const meta = $('#blMeta'), body = $('#blBody');
  const ok = BL.stocks.filter(s => s.status === 'ok');
  meta.innerHTML = `${ok.length}개 종목 · ${esc(BL.source)} · 갱신 ${dayfmt((BL.generated_at || '').slice(0, 10))}`;

  const x = BLSEL ? BL.stocks.find(s => s.code === BLSEL) : null;
  if (!x) {
    const top = ok.slice().sort((a, b) => (b.yoy ?? -999) - (a.yoy ?? -999));
    body.innerHTML = `<div class="sec">전년동기비 증가 상위 <small>종목을 검색하거나 아래에서 고르세요</small></div>
      <div class="box">${blTableHTML(top.slice(0, 25))}</div>`;
    body.querySelectorAll('tr[data-c]').forEach(tr => tr.onclick = () => blPick(tr.dataset.c));
    return;
  }

  const ps = x.periods, last = ps[ps.length - 1];
  body.innerHTML = `
    <div class="cards">
      <div class="card"><div class="k">수주잔고 <span class="pill">${esc(x.last)}</span></div>
        <div class="v num">${won(x.last_backlog)}</div>
        <div class="d num ${cls(x.qoq)}">${sgn(x.qoq)}% <span style="color:var(--faint);font-weight:600">직전 대비</span></div>
        <div class="n">기준일 ${last.asof || '—'}</div></div>
      <div class="card"><div class="k">전년동기비</div>
        <div class="v num ${cls(x.yoy)}">${sgn(x.yoy)}<em>%</em></div>
        <div class="n">같은 분기 공시 대비</div></div>
      <div class="card"><div class="k">매출 대비 <span class="pill">커버리지</span></div>
        <div class="v num">${x.cover == null ? '—' : x.cover.toFixed(2)}<em>x</em></div>
        <div class="n">${x.revenue_year || ''}년 매출 ${won(x.revenue)} 기준</div></div>
      <div class="card"><div class="k">공시 이력</div>
        <div class="v num">${ps.length}<em>개</em></div>
        <div class="n">${esc(ps[0].period)} ~ ${esc(x.last)}</div></div>
    </div>
    <div class="chartbox"><h4>${esc(x.name)} 수주잔고 추이</h4><p>${esc(x.sector)} · ${x.code} · DART 정기보고서</p><div id="blChart"></div></div>
    <div class="sec">공시별</div>
    <div class="box"><table><thead><tr><th>기준</th><th>수주잔고</th><th>직전비</th><th>전년동기비</th><th>기준일</th><th>공시</th></tr></thead>
      <tbody>${ps.slice().reverse().map(p => `<tr style="cursor:default">
        <td class="nm">${esc(p.period)}</td>
        <td class="num" style="font-weight:700">${won(p.backlog)}</td>
        <td class="num ${cls(p.qoq)}">${sgn(p.qoq)}%</td>
        <td class="num ${cls(p.yoy)}">${sgn(p.yoy)}%</td>
        <td class="num" style="color:var(--faint)">${p.asof || '—'}</td>
        <td>${p.rcept ? `<a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${p.rcept}" target="_blank" rel="noopener">원문</a>` : '—'}</td>
      </tr>`).join('')}</tbody></table></div>
    ${last.breakdown && last.breakdown.length ? `<div class="sec">구성 <small>${esc(x.last)} 기준</small></div>
      <div class="box"><table><thead><tr><th>구분</th><th>잔고</th><th>비중</th></tr></thead><tbody>
      ${last.breakdown.map(b => `<tr style="cursor:default"><td class="nm">${esc(b.k)}</td><td class="num">${won(b.v)}</td>
        <td class="num" style="color:var(--faint)">${(b.v / last.backlog * 100).toFixed(1)}%</td></tr>`).join('')}
      </tbody></table></div>` : ''}`;
  barChart($('#blChart'), ps.map((p, i) => ({ k: p.period, v: p.backlog, hl: i === ps.length - 1 })));
}

function blTableHTML(rows) {
  return `<table><thead><tr><th>종목</th><th>섹터</th><th>수주잔고</th><th>직전비</th><th>전년동기비</th><th>커버리지</th><th>기준</th></tr></thead>
    <tbody>${rows.map(x => `<tr data-c="${x.code}">
      <td class="nm">${esc(x.name)}<span class="sb">${x.code}</span></td>
      <td style="text-align:left;color:var(--sub)">${esc(x.sector)}</td>
      <td class="num" style="font-weight:700">${won(x.last_backlog)}</td>
      <td class="num ${cls(x.qoq)}">${sgn(x.qoq)}%</td>
      <td class="num ${cls(x.yoy)}">${sgn(x.yoy)}%</td>
      <td class="num">${x.cover == null ? '—' : x.cover.toFixed(2) + 'x'}</td>
      <td class="num" style="color:var(--faint)">${esc(x.last)}</td>
    </tr>`).join('')}</tbody></table>`;
}

$('#blSearch').addEventListener('input', e => { BLHI = -1; blDrop(e.target.value); });
$('#blSearch').addEventListener('focus', e => blDrop(e.target.value));
$('#blSearch').addEventListener('blur', () => setTimeout(() => $('#blDrop').classList.remove('on'), 120));
$('#blSearch').addEventListener('keydown', e => {
  const rows = blList($('#blSearch').value);
  if (e.key === 'ArrowDown') { BLHI = Math.min(BLHI + 1, rows.length - 1); blDrop($('#blSearch').value); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { BLHI = Math.max(BLHI - 1, 0); blDrop($('#blSearch').value); e.preventDefault(); }
  else if (e.key === 'Enter') { const r = rows[BLHI < 0 ? 0 : BLHI]; if (r) blPick(r.code); }
  else if (e.key === 'Escape') { $('#blDrop').classList.remove('on'); }
});

/* ═══════════ 홈 ═══════════ */
function renderHome() {
  const c = $('#homeCards');
  const out = [];
  if (CDS) {
    const kr = CDS.sovereigns['한국'], or = CDS.ai && CDS.ai['Oracle'], ms = CDS.ai && CDS.ai['Microsoft'];
    if (kr) { const m = chg(kr.series, 30); out.push(`<div class="card"><div class="k">한국 국가 CDS <span class="pill">5Y</span></div>
      <div class="v num">${bp(kr.last_bp)}<em>bp</em></div><div class="d num ${cls(m)}">${sgn(m)}bp <span style="color:var(--faint);font-weight:600">1개월</span></div>
      <div class="n">최근 체결 ${dayfmt(kr.last)}</div></div>`); }
    if (or) { const m = chg(or.series, 30); out.push(`<div class="card"><div class="k">오라클 <span class="pill">AI 캐펙스</span></div>
      <div class="v num">${bp(or.last_bp)}<em>bp</em></div><div class="d num ${cls(m)}">${sgn(m)}bp <span style="color:var(--faint);font-weight:600">1개월</span></div>
      <div class="n">체결 ${or.trades.toLocaleString()}건 — 기업 단일물 최다</div></div>`); }
    if (or && ms) out.push(`<div class="card"><div class="k">오라클 − 마이크로소프트</div>
      <div class="v num">${bp(or.last_bp - ms.last_bp, 0)}<em>bp</em></div>
      <div class="d" style="color:var(--faint);font-weight:600">AI 부채조달 프리미엄</div>
      <div class="n">MS ${bp(ms.last_bp)}bp 대비</div></div>`);
  }
  if (BL) {
    const ok = BL.stocks.filter(s => s.status === 'ok' && s.yoy != null);
    const up = ok.filter(s => s.yoy > 0).length;
    out.push(`<div class="card"><div class="k">수주잔고 증가 종목</div>
      <div class="v num">${up}<em>/${ok.length}</em></div>
      <div class="d" style="color:var(--faint);font-weight:600">전년동기비 증가</div>
      <div class="n">DART 정기보고서 · ${dayfmt((BL.generated_at || '').slice(0, 10))} 갱신</div></div>`);
  }
  c.innerHTML = out.join('');

  if (CDS && CDS.ai) {
    const rows = cdsRows(CDS.ai, Object.keys(CDS.ai)).sort((a, b) => (b.last_bp ?? -1) - (a.last_bp ?? -1));
    $('#homeAI').innerHTML = `<table><thead><tr><th>기업</th><th>5Y (bp)</th><th>1개월</th><th>3개월</th><th>추이</th></tr></thead>
      <tbody>${rows.map(r => `<tr data-go="ai" data-n="${esc(r.name)}"><td class="nm">${esc(r.name)}</td>
        <td class="num" style="font-weight:800">${bp(r.last_bp)}</td>
        <td class="num ${cls(chg(r.series, 30))}">${sgn(chg(r.series, 30))}</td>
        <td class="num ${cls(chg(r.series, 90))}">${sgn(chg(r.series, 90))}</td>
        <td>${spark(r.series.slice(-60))}</td></tr>`).join('')}</tbody></table>`;
    $('#homeAI').querySelectorAll('tr[data-n]').forEach(tr => tr.onclick = () => { SEL.ai = tr.dataset.n; render(); openTab('ai'); });
  }
  if (BL) {
    const top = BL.stocks.filter(s => s.status === 'ok').sort((a, b) => (b.yoy ?? -999) - (a.yoy ?? -999)).slice(0, 10);
    $('#homeBacklog').innerHTML = blTableHTML(top);
    $('#homeBacklog').querySelectorAll('tr[data-c]').forEach(tr => tr.onclick = () => { blPick(tr.dataset.c); openTab('backlog'); });
  }
}

function renderMethod() {
  if (!CDS) return;
  $('#methBody').innerHTML = `
    <h4>CDS — 무엇을 긁어서 어떻게 계산했나</h4>
    출처는 <b>DTCC 공개 스왑 체결 공시</b>(<code>pddata.dtcc.com</code>). 미국 규제상 모든 스왑 체결은
    실시간으로 공개돼야 해서, CDS 체결이 매일 CSV 로 공시된다. 인증도 요금도 없다.
    수집 범위는 ${CDS.coverage.from} ~ ${CDS.coverage.to}, ${CDS.coverage.days.toLocaleString()}영업일.
    <h4>공시에는 스프레드가 없다</h4>
    표준화 이후 단일물 CDS 는 <b>고정쿠폰</b>(투자등급 100bp / 하이일드 500bp)으로 거래하고 차액을
    업프론트 현금으로 주고받는다. 그래서 공시에 남는 건 <code>Other payment amount</code> 의 현금액뿐이다.
    이걸 ISDA 표준모형(회수율 40%)으로 되돌려 par spread 를 뽑는다.
    <h4>세 가지 함정</h4>
    <ul>
      <li><b>노셔널 마스킹</b> — $5m 초과 거래는 <code>5,000,000+</code> 로 가려진다. 하한값으로 계산한다.
        노셔널이 그대로 공시된 소액 거래(한국물 174건)로 검증해보면 5Y 기준 두 방식의 중앙값 차이가 0.5bp 안쪽이다.</li>
      <li><b>미수이자</b> — 공시 현금에는 직전 IMM(3·6·9·12월 20일) 이후 경과쿠폰이 섞여 있다. 잘못 처리하면
        분기 롤마다 스프레드가 계단처럼 튄다. 한국물 700건으로 롤 전후 점프를 재서 부호를 정했다 —
        무시하면 +6.4bp, 반대부호는 +10.8bp, 채택한 방식은 +2.0bp.</li>
      <li><b>업프론트 부호</b> — 누가 냈는지가 공시되지 않아 현금 하나에 해가 둘 붙는다(쿠폰보다 낮은 해, 높은 해).
        종목 단위로 하나만 정하면 안 된다 — 오라클은 2025년 35~57bp 로 쿠폰(100bp) 아래에 있다가
        2026년 200bp 로 올라섰다. 그래서 <b>하루 단위로</b> 정한다. 단일물 체결의 약 4분의 1은 딜러 호가가
        공시에 그대로 실리는데, 그 날은 호가를 쓰고 나머지 날은 앞뒤 호가를 이어 만든 값에 가까운 해를 고른다.
        표에서 '쿠폰 교차' 로 표시된 종목이 그 사이를 넘어선 크레딧이다.</li>
    </ul>
    <h4>검증</h4>
    호가가 실린 날의 딜러 값과 같은 날 역산값을 맞대보면 절대오차 중앙값이
    <b>마이크로소프트 0.5bp · Meta 0.5 · NVIDIA 0.7 · 브로드컴 0.6 · 알파벳 0.7 · 오라클 7.5bp</b> 다.
    지수 CDS 도 기준선이 된다 — 다만 CDX.NA.HY 는 스프레드가 아니라 가격(100 기준)으로 호가되는데
    공시는 그 값을 같은 칸에 넣는다. 108 처럼 보이지만 가격 107.9 이고, 쿠폰 500bp 로 되돌리면 301bp 다.
    국가별 서열(한국 &lt; 일본 &lt; 중국 &lt; 필리핀 &lt; 브라질 &lt; 튀르키예)도 시장 통념과 일치한다.
    <h4>한계</h4>
    체결 기반이라 <b>호가가 아니다</b>. 한국물은 하루 1~3건이고 아예 없는 날도 있다. 종가 기준 공식 시세와는
    다르며, 수준과 방향을 보는 용도다. 국내 기업 단일물은 체결이 훨씬 드물어 시계열보다 체결 내역 자체를 본다.
    <h4>회사채 스프레드</h4>
    ICE BofA 등급별 지수 OAS(FRED)와 미 재무부 일별 금리곡선. 둘 다 인증이 필요 없다.
    OAS 는 같은 만기 국채 대비 초과수익률이라 <b>CDS 와 정의가 다르다</b> — CDS 는 부도보험 요율이다.
    레벨을 맞대지 말고 같은 지표끼리만 비교할 것. 개별 회사채 체결(FINRA TRACE)은 무료지만
    계정 등록이 필요해 아직 붙이지 않았다.
    <h4>기업 분석 — 티커에서 개요·재무제표까지</h4>
    정적 페이지라 브라우저가 DART·EDGAR 를 직접 부를 수 없다(CORS). 빌드 때 미리 말아둔다.
    <ul>
      <li><b>국내</b> — DART 다중회사 주요계정. 한 번에 100개사를 받고 응답에 당기·전기·전전기가
        함께 실려, 40회 남짓 호출로 상장사 전체 6년치가 나온다. 개요(company.json)만 종목당
        1회라 매출 큰 순으로 회차를 나눠 받는다 — 한 번에 몰아치면 DART 가 IP 를 막는다.</li>
      <li><b>미국</b> — EDGAR XBRL frames. 기업별 companyfacts 는 한 곳당 3~5MB 라 1만 종목엔
        못 쓴다. frames 는 "개념 하나 × 기간 하나"를 전 종목에 대해 한 번에 주므로 170회로 덮는다.
        frames 가 역년(CY) 기준이라 5월 결산 오라클 같은 회사와 IFRS 로 내는 외국 발행사(ADR)가
        빠지는데, 그 종목만 companyfacts 로 따로 보완한다.</li>
      <li>외국 발행사는 신고 통화가 USD 가 아니다(TSM 은 TWD, 알리바바는 CNY). 화면에 통화를
        함께 띄운다.</li>
    </ul>
    <h4>수주잔고</h4>
    DART 정기보고서 원문에서 수주잔고 표를 파싱한다(<code>~/backlog-bot</code>, 매일 08:30 자동 수집).
    수주산업만 공시 의무가 있어 대상은 ${BL ? BL.stocks.filter(s => s.status === 'ok').length : '—'}개 종목이다.
    확정 잔고는 분기말 기준이라 공시 시점에 이미 45~90일 지난 값이라는 점을 감안해야 한다.
    각 행의 '원문' 링크로 실제 공시를 바로 확인할 수 있다.`;
}

function render() {
  if (CDS) {
    renderCdsGroup('ai', CDS.ai || {}, Object.keys(CDS.ai || {}), 4);
    renderCdsGroup('sov', CDS.sovereigns || {}, Object.keys(CDS.sovereigns || {}), 4);
    renderCdsGroup('idx', CDS.indices || {}, Object.keys(CDS.indices || {}), 4);
    renderKr();
  }
  renderBacklog();
  renderBond();
  renderHome();
  renderMethod();
}

function renderKr() {
  const g = CDS.corps || {};
  const rows = Object.entries(g).map(([n, v]) => ({ name: n, ...v })).filter(r => r.recent && r.recent.length);
  if (!rows.length) { $('#krTable').innerHTML = '<div class="empty"><b>최근 체결이 없습니다</b>국내 기업 단일물은 체결이 매우 드뭅니다</div>'; return; }
  rows.sort((a, b) => b.trades - a.trades);
  $('#krTable').innerHTML = `<table><thead><tr><th>대상</th><th>최근 5Y (bp)</th><th>체결</th><th>최근 체결일</th><th>최근 만기</th></tr></thead>
    <tbody>${rows.map(r => {
      const t = r.recent[0];
      return `<tr style="cursor:default"><td class="nm">${esc(r.name)}</td>
        <td class="num" style="font-weight:800">${r.last_bp != null ? bp(r.last_bp) : bp(t.bp)}</td>
        <td class="num">${r.trades.toLocaleString()}</td>
        <td class="num" style="color:var(--faint)">${dayfmt(t.date)}</td>
        <td class="num" style="color:var(--faint)">${t.maturity} <span class="sb">${t.tenor.toFixed(1)}Y</span></td></tr>`;
    }).join('')}</tbody></table>`;
  $('#krNote').innerHTML = '국내 기업 달러 CDS 는 체결이 드물어(대부분 20개월간 수십 건) 일별 시세로 보기 어렵다. 표의 값은 가장 최근 체결에서 역산한 수준이다.';
}

window.addEventListener('hashchange', () => openTab(location.hash.slice(1) || 'home'));

/* ═══════════ 기업 분석 (DART · EDGAR) ═══════════ */
let FIN = null, COSEL = null, COHI = -1, COCACHE = {};

function usd(v) {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B';
  if (a >= 1e6) return (v / 1e6).toFixed(0) + 'M';
  return v.toLocaleString();
}
/* 외국 발행사는 USD 가 아니라 신고 통화(TWD·CNY 등)로 낸다 — 통화를 같이 표시해야 오독이 없다 */
const money = (v, m, unit) => m === 'US'
  ? (v == null ? '—' : usd(v) + (unit && unit !== 'USD' ? ' ' + unit : ''))
  : won(v);
const ratio = (a, b) => (a == null || !b) ? null : a / b * 100;

/* 국내는 DART 주요계정, 미국은 XBRL 태그라 계정 구성이 다르다 */
const ROWS_KR = [
  ['rev', '매출액'], ['op', '영업이익'], ['pre', '법인세차감전이익'], ['net', '당기순이익'],
  ['assets', '자산총계'], ['ca', '유동자산'], ['nca', '비유동자산'],
  ['liab', '부채총계'], ['cl', '유동부채'], ['ncl', '비유동부채'],
  ['equity', '자본총계'], ['cap', '자본금'], ['re', '이익잉여금'],
];
const ROWS_US = [
  ['revenue', '매출'], ['gross', '매출총이익'], ['op', '영업이익'], ['net', '순이익'],
  ['ocf', '영업활동현금흐름'], ['capex', 'CapEx'],
  ['assets', '자산'], ['liab', '부채'], ['equity', '자본'],
  ['cash', '현금성자산'], ['debt', '장기차입금'],
];

function coList(q) {
  if (!FIN) return [];
  const t = (q || '').trim().toLowerCase();
  if (!t) return FIN.rows.slice(0, 12);
  const starts = [], has = [];
  for (const r of FIN.rows) {
    const tk = r.t.toLowerCase(), nm = (r.n || '').toLowerCase(), en = (r.e || '').toLowerCase();
    if (tk === t) { starts.unshift(r); continue; }
    if (tk.startsWith(t) || nm.startsWith(t)) starts.push(r);
    else if (nm.includes(t) || en.includes(t) || tk.includes(t)) has.push(r);
    if (starts.length > 30) break;
  }
  return starts.concat(has).slice(0, 20);
}

function coDrop(q) {
  const d = $('#coDrop');
  if (!FIN) { d.innerHTML = '<div class="dropitem"><span>목록 불러오는 중…</span></div>'; d.classList.add('on'); return; }
  const rows = coList(q);
  if (!rows.length) { d.innerHTML = '<div class="dropitem"><span>일치하는 기업이 없습니다</span></div>'; d.classList.add('on'); return; }
  d.innerHTML = rows.map((x, i) => `<div class="dropitem ${i === COHI ? 'hi' : ''}" data-k="${x.m}:${esc(x.t)}">
    <b>${esc(x.n)}</b><span>${x.m === 'KR' ? '' : x.m + ' · '}${esc(x.t)}${x.e && x.m === 'US' ? ' · ' + esc(x.e) : ''}</span>
    <span class="r num" style="color:var(--faint)">${x.rev ? money(x.rev, x.m, x.u) : ''}</span></div>`).join('');
  d.classList.add('on');
  d.querySelectorAll('[data-k]').forEach(n => n.onmousedown = (e) => { e.preventDefault(); coPick(n.dataset.k); });
}

function coPick(key) {
  COSEL = key; COHI = -1;
  $('#coDrop').classList.remove('on');
  const [m, t] = key.split(':');
  const row = FIN && FIN.rows.find(r => r.m === m && r.t === t);
  if (row) $('#coSearch').value = row.n;
  if (COCACHE[key]) { renderCo(); return; }
  $('#coBody').innerHTML = '<div class="empty">불러오는 중…</div>';
  fetch(`data/fin/${m}/${encodeURIComponent(t)}.json?t=` + Date.now())
    .then(r => r.ok ? r.json() : null).catch(() => null)
    .then(d => { COCACHE[key] = d || 'none'; renderCo(); });
}

function coEnsure() {
  if (FIN) return;
  fetch('data/fin_index.json?t=' + Date.now()).then(r => r.json()).then(d => {
    FIN = d;
    $('#coMeta').innerHTML = `${d.count.toLocaleString()}개 기업 · 국내 DART 주요계정 · 미국 EDGAR XBRL`;
    if (COSEL) coPick(COSEL); else renderCo();
  }).catch(() => { $('#coMeta').textContent = '기업 목록을 불러오지 못했습니다'; });
}

function statCards(d) {
  const m = d.market, u = d.unit, A = d.annual || [];
  const last = A[A.length - 1], prev = A[A.length - 2];
  const rk = m === 'US' ? 'revenue' : 'rev';
  if (!last) return '';
  const g = (prev && prev[rk] && last[rk]) ? (last[rk] / prev[rk] - 1) * 100 : null;
  const opm = ratio(last.op, last[rk]);
  const npm = ratio(last.net, last[rk]);
  const lev = (last.liab != null && last.equity) ? last.liab / last.equity * 100 : null;
  return `<div class="cards">
    <div class="card"><div class="k">매출 <span class="pill">${esc(last.period)}</span></div>
      <div class="v num">${money(last[rk], m, u)}</div>
      <div class="d num ${cls(g)}">${sgn(g)}% <span style="color:var(--faint);font-weight:600">전년비</span></div></div>
    <div class="card"><div class="k">영업이익률</div>
      <div class="v num">${opm == null ? '—' : opm.toFixed(1)}<em>%</em></div>
      <div class="n">영업이익 ${money(last.op, m, u)}</div></div>
    <div class="card"><div class="k">순이익률</div>
      <div class="v num">${npm == null ? '—' : npm.toFixed(1)}<em>%</em></div>
      <div class="n">순이익 ${money(last.net, m, u)}</div></div>
    <div class="card"><div class="k">부채비율</div>
      <div class="v num">${lev == null ? '—' : lev.toFixed(0)}<em>%</em></div>
      <div class="n">부채 ${money(last.liab, m, u)} / 자본 ${money(last.equity, m, u)}</div></div>
  </div>`;
}

function finTable(rows, spec, m, unit) {
  if (!rows.length) return '';
  const head = rows.map(r => `<th>${esc(r.period)}</th>`).join('');
  const body = spec.filter(([k]) => rows.some(r => r[k] != null)).map(([k, label]) =>
    `<tr style="cursor:default"><td class="nm">${label}</td>${rows.map(r =>
      `<td class="num">${r[k] == null ? '—' : money(r[k], m, unit)}</td>`).join('')}</tr>`).join('');
  return `<div class="box" style="overflow-x:auto"><table><thead><tr><th>계정</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderCo() {
  const body = $('#coBody');
  if (!FIN) { body.innerHTML = '<div class="empty">불러오는 중…</div>'; return; }
  if (!COSEL) {
    body.innerHTML = '<div class="empty"><b>티커나 종목명을 입력하세요</b>국내 상장사와 미국 상장사를 함께 검색합니다</div>';
    return;
  }
  const d = COCACHE[COSEL];
  if (!d) { body.innerHTML = '<div class="empty">불러오는 중…</div>'; return; }
  if (d === 'none') { body.innerHTML = '<div class="empty"><b>재무 데이터가 없습니다</b>공시 이력이 없거나 아직 수집되지 않은 종목입니다</div>'; return; }

  const m = d.market, spec = m === 'US' ? ROWS_US : ROWS_KR;
  const p = d.profile || {};
  const est = p.est_dt ? `${p.est_dt.slice(0, 4)}.${p.est_dt.slice(4, 6)}.${p.est_dt.slice(6, 8)}` : null;
  const meta = m === 'KR'
    ? [['정식명', p.corp_name], ['영문명', p.corp_name_eng], ['대표', p.ceo_nm], ['설립', est],
       ['시장', { Y: '유가증권', K: '코스닥', N: '코넥스', E: '기타' }[p.corp_cls] || p.corp_cls],
       ['결산월', p.acc_mt ? p.acc_mt + '월' : null], ['업종코드', p.induty_code], ['주소', p.adres]]
    : [['영문명', d.name], ['거래소', d.exchange], ['CIK', d.cik],
       ['기준', d.fiscal ? '회계연도 (비역년 결산)' : '역년 (CY)'],
       ['신고통화', d.unit && d.unit !== 'USD' ? d.unit : 'USD']];

  const links = [];
  if (m === 'KR') {
    links.push(`<a href="https://dart.fss.or.kr/dsab007/main.do?textCrpNm=${encodeURIComponent(d.name)}" target="_blank" rel="noopener">DART 공시</a>`);
    links.push(`<a href="https://finance.naver.com/item/main.naver?code=${d.code}" target="_blank" rel="noopener">네이버 증권</a>`);
    if (BL && BL.stocks.some(s => s.code === d.code && s.status === 'ok'))
      links.push(`<a href="#backlog" data-bl="${d.code}">수주잔고 보기</a>`);
  } else {
    links.push(`<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${d.cik}&type=10-K" target="_blank" rel="noopener">EDGAR</a>`);
    const hit = CDS && CDS.ai && Object.keys(CDS.ai).find(n => n.toLowerCase() === (d.ticker || '').toLowerCase()
      || (d.name || '').toLowerCase().startsWith(n.toLowerCase()));
    if (hit) links.push(`<a href="#ai" data-cds="${esc(hit)}">CDS 보기</a>`);
  }

  body.innerHTML = `
    <div class="sec">${esc(d.name)} <small>${m === 'KR' ? d.code : d.ticker} · ${m === 'KR' ? '국내' : '미국'}</small></div>
    ${statCards(d)}
    <div class="box" style="padding:16px 18px">
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px 24px;font-size:12.5px">
      ${meta.filter(([, v]) => v).map(([k, v]) =>
        `<div><span style="color:var(--faint);font-weight:600">${k}</span>
         <div style="font-weight:600;margin-top:2px;word-break:break-all">${esc(v)}</div></div>`).join('')}
      </div>
      ${links.length ? `<div style="margin-top:14px;display:flex;gap:14px;font-size:12.5px;font-weight:600">${links.join('')}</div>` : ''}
    </div>
    <div class="chartbox" style="margin-top:14px"><h4>매출 · 영업이익 추이</h4>
      <p>연간 · ${m === 'KR' ? '연결 기준 (DART 주요계정)' : 'EDGAR XBRL'}</p><div id="coChart"></div></div>
    <div class="sec">연간 재무제표</div>
    ${finTable(d.annual || [], spec, m, d.unit)}
    ${(d.quarter || []).length ? `<div class="sec">분기</div>${finTable(d.quarter, spec, m, d.unit)}` : ''}`;

  const rk = m === 'US' ? 'revenue' : 'rev';
  barChart($('#coChart'), (d.annual || []).filter(a => a[rk] != null)
    .map((a, i, arr) => ({ k: a.period, v: a[rk], hl: i === arr.length - 1 })), m, d.unit);

  body.querySelectorAll('[data-bl]').forEach(a => a.onclick = (e) => { e.preventDefault(); blPick(a.dataset.bl); openTab('backlog'); });
  body.querySelectorAll('[data-cds]').forEach(a => a.onclick = (e) => { e.preventDefault(); SEL.ai = a.dataset.cds; render(); openTab('ai'); });
}

$('#coSearch').addEventListener('input', e => { COHI = -1; coDrop(e.target.value); });
$('#coSearch').addEventListener('focus', e => { coEnsure(); coDrop(e.target.value); });
$('#coSearch').addEventListener('blur', () => setTimeout(() => $('#coDrop').classList.remove('on'), 120));
$('#coSearch').addEventListener('keydown', e => {
  const rows = coList($('#coSearch').value);
  if (e.key === 'ArrowDown') { COHI = Math.min(COHI + 1, rows.length - 1); coDrop($('#coSearch').value); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { COHI = Math.max(COHI - 1, 0); coDrop($('#coSearch').value); e.preventDefault(); }
  else if (e.key === 'Enter') { const r = rows[COHI < 0 ? 0 : COHI]; if (r) coPick(r.m + ':' + r.t); }
  else if (e.key === 'Escape') { $('#coDrop').classList.remove('on'); }
});
document.querySelectorAll('.navitem[data-tab="co"]').forEach(b => b.addEventListener('click', coEnsure));

/* ═══════════ 회사채 스프레드 (지수 OAS · 국채곡선) ═══════════ */
let BOND = null, BSEL = '투자등급';

function renderBond() {
  if (!BOND) return;
  const names = Object.keys(BOND.oas);
  if (!names.length) return;
  if (!BOND.oas[BSEL]) BSEL = names[0];

  const card = ['투자등급', 'AA', 'BBB', '하이일드'].filter(n => BOND.oas[n]);
  $('#bondCards').innerHTML = card.map(n => {
    const v = BOND.oas[n], m = chg(v.series, 30);
    return `<button class="card" data-b="${esc(n)}">
      <div class="k">${esc(n)} <span class="pill">OAS</span></div>
      <div class="v num">${v.last_bp.toFixed(0)}<em>bp</em></div>
      <div class="d num ${cls(m)}">${sgn(m, 0)}bp <span style="color:var(--faint);font-weight:600">1개월</span></div>
      <div class="n">ICE BofA · ${dayfmt(v.last)}</div></button>`;
  }).join('');
  $('#bondCards').querySelectorAll('[data-b]').forEach(b => b.onclick = () => { BSEL = b.dataset.b; renderBond(); });

  const sel = BOND.oas[BSEL];
  $('#bondChartTitle').textContent = BSEL + ' 회사채 OAS';
  $('#bondChartSub').innerHTML = `국채 대비 초과수익률 · 1주 ${sgn(chg(sel.series, 7), 0)}bp · 1개월 ${sgn(chg(sel.series, 30), 0)}bp`;
  lineChart($('#bondChart'), sel.series, { id: 'bond' });

  $('#bondTable').innerHTML = `<table><thead><tr>
      <th>등급</th><th>OAS (bp)</th><th>1주</th><th>1개월</th><th>3개월</th><th>추이</th><th>기준</th>
    </tr></thead><tbody>${names.map(n => {
      const v = BOND.oas[n];
      return `<tr data-b="${esc(n)}" class="${BSEL === n ? 'on' : ''}">
        <td class="nm">${esc(n)}</td>
        <td class="num" style="font-weight:800">${v.last_bp.toFixed(0)}</td>
        <td class="num ${cls(chg(v.series, 7))}">${sgn(chg(v.series, 7), 0)}</td>
        <td class="num ${cls(chg(v.series, 30))}">${sgn(chg(v.series, 30), 0)}</td>
        <td class="num ${cls(chg(v.series, 90))}">${sgn(chg(v.series, 90), 0)}</td>
        <td>${spark(v.series.slice(-90))}</td>
        <td class="num" style="color:var(--faint)">${dayfmt(v.last)}</td></tr>`;
    }).join('')}</tbody></table>`;
  $('#bondTable').querySelectorAll('[data-b]').forEach(tr => tr.onclick = () => { BSEL = tr.dataset.b; renderBond(); });

  const cur = BOND.treasury[BOND.treasury.length - 1] || {};
  const ord = ['1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '20Y', '30Y'].filter(t => cur[t] != null);
  $('#ustSub').textContent = `${dayfmt(cur.d)} 기준 · 단위 %`;
  curveChart($('#ustChart'), ord.map(t => ({ tenor: t, bp: cur[t], n: '' })), 2);

  $('#bondNote').innerHTML = `${esc(BOND.source)} · 갱신 ${dayfmt((BOND.generated_at || '').slice(0, 10))}<br>${esc(BOND.note)}`;
}
