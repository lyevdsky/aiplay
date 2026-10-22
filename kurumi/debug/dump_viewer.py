"""把 dump 文件夹生成一个可直接双击打开的 viewer.html，逐帧查看：
帧图片、watcher 的 step 识别输出、put 入队、main 的消费 / phase / mjai、gamestate。

用法一（自动）：recorder.dump() 写完文件后会自动生成 <dump>/viewer.html。
用法二（旧 dump / 手动）：改下面的 DUMP_FOLDER，直接运行  python dump_viewer.py

viewer.html 放在 dump 文件夹里，图片用相对路径 frames/xxxx.png 引用，数据内嵌在页面中，
所以整个文件夹可以整体拷走、压缩发给别人，用浏览器打开即可（不需要服务器、不联网）。
"""
import json
import os

# ───────────────────────── 参数（在这里改）─────────────────────────
DUMP_FOLDER = './logs/dump/20261020_223324_exception'   # 要生成查看器的 dump 文件夹
# ──────────────────────────────────────────────────────────────────


def _jl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def build_viewer(folder, name='viewer.html'):
    """读取 folder 下的 frames/events/states/meta，写出 folder/viewer.html，返回路径。"""
    meta = {}
    mp = os.path.join(folder, 'meta.json')
    if os.path.exists(mp):
        with open(mp, encoding='utf-8') as f:
            meta = json.load(f)
    data = {
        'meta': meta,
        'frames': _jl(os.path.join(folder, 'frames.jsonl')),
        'events': _jl(os.path.join(folder, 'events.jsonl')),
        'states': _jl(os.path.join(folder, 'states.jsonl')),
    }
    # 嵌进 <script> 里：避免 "</script>" 提前结束标签
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    html = TEMPLATE.replace('__DATA__', payload)
    out = os.path.join(folder, name)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    return out


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dump 查看器</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #eceff3; --panel: #ffffff; --panel2: #f5f7fa; --line: #d5dae3;
  --ink: #1b2430; --dim: #6b7587; --accent: #0b6e99;
  --put: #1b8a52; --consume: #2457c5; --phase: #b3690f; --hit: #7a3fc4; --race: #c63b3b; --exc: #d6123f;
  --mono: "Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, monospace;
  --sans: "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14181f; --panel: #1c222c; --panel2: #232a36; --line: #323b4a;
    --ink: #dfe5ef; --dim: #8993a6; --accent: #5ab4e0;
    --put: #4cc58a; --consume: #6b9cf5; --phase: #e0a444; --hit: #b98af0; --race: #f06f6f; --exc: #ff6b87;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink);
  font: 13px/1.5 var(--sans); }
code, .mono { font-family: var(--mono); font-size: 12px; }
button, select, input { font: inherit; color: inherit; }
button { background: var(--panel); border: 1px solid var(--line); border-radius: 5px;
  padding: 3px 10px; cursor: pointer; }
button:hover { border-color: var(--accent); }
button:focus-visible, select:focus-visible, input:focus-visible, a:focus-visible,
.cell:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
select, input[type=text] { background: var(--panel); border: 1px solid var(--line);
  border-radius: 5px; padding: 3px 6px; }
a { color: var(--accent); text-decoration: none; border-bottom: 1px dotted var(--accent); }
.dim, .nul { color: var(--dim); }

header { position: sticky; top: 0; z-index: 10; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 8px 14px 10px; }
.titlebar { display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; }
.titlebar b { font-size: 14px; }
.ctl { display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; margin: 6px 0; }
.ctl .sep { width: 1px; height: 18px; background: var(--line); margin: 0 4px; }
#jump { width: 72px; font-family: var(--mono); }
#slider { width: 100%; margin: 2px 0 6px; accent-color: var(--accent); }

.lanes { display: grid; grid-template-columns: 44px 1fr; gap: 2px 8px; align-items: center; }
.lanes .lbl { color: var(--dim); font-size: 11px; text-align: right; }
.cells { display: grid; gap: 1px; height: 9px; }
.cell { background: var(--panel2); cursor: pointer; border-radius: 1px; }
.cell.on.put { background: var(--put); } .cell.on.hit { background: var(--hit); }
.cell.on.consume { background: var(--consume); } .cell.on.phase { background: var(--phase); }
.cell.on.race { background: var(--race); opacity: .55; }
.cell.on.exc { background: var(--exc); }
.cell.cur { outline: 2px solid var(--ink); outline-offset: 0; z-index: 1; position: relative; }

main { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 14px;
  padding: 14px; align-items: start; }
@media (max-width: 1000px) { main { grid-template-columns: minmax(0, 1fr); } #left { position: static !important; } }
#left { position: sticky; top: var(--hh, 150px); }
#shotwrap { background: #000; border: 1px solid var(--line); border-radius: 6px;
  overflow: auto; max-height: calc(100vh - var(--hh, 150px) - 70px); cursor: zoom-in; }
#shotwrap.full { cursor: zoom-out; }
#shot { display: block; width: 100%; height: auto; }
#shotwrap.full #shot { width: auto; max-width: none; }
#shotmiss { padding: 40px; text-align: center; color: #aaa; display: none; }
#framemeta { margin-top: 6px; color: var(--dim); font-size: 12px; }

.fhead { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; margin-bottom: 10px; }
.fhead .big { font: 600 22px/1 var(--mono); }
.badge { display: inline-block; padding: 0 7px; border-radius: 9px; font-size: 11px;
  border: 1px solid var(--line); background: var(--panel2); }
.badge.race { color: var(--race); border-color: var(--race); }
.badge.newsnap { color: var(--accent); border-color: var(--accent); }

.card { background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  margin-bottom: 10px; }
.card > h3 { margin: 0; padding: 6px 10px; font-size: 12.5px; font-weight: 600;
  border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; }
.card > .body { padding: 8px 10px; }
.empty { color: var(--dim); }

table.kv { border-collapse: collapse; width: 100%; }
table.kv td { padding: 2px 6px 2px 0; vertical-align: top; border-bottom: 1px solid var(--panel2); }
table.kv td:first-child { color: var(--dim); width: 96px; white-space: nowrap; font-family: var(--mono); font-size: 12px; }
table.kv tr.hl td:last-child { font-weight: 600; color: var(--hit); }
table.kv tr.skip td:last-child { color: var(--dim); font-style: italic; }

.ev { border-left: 3px solid var(--line); padding: 3px 0 3px 9px; margin: 6px 0; }
.ev .top { display: flex; flex-wrap: wrap; gap: 2px 10px; align-items: baseline; }
.ev .kind { font-weight: 600; }
.ev .meta { color: var(--dim); font-size: 11px; }
.ev pre { margin: 2px 0 0; white-space: pre-wrap; word-break: break-all;
  font: 12px/1.45 var(--mono); }
.ev.k-put { border-color: var(--put); } .ev.k-put .kind { color: var(--put); }
.ev.k-consume { border-color: var(--consume); } .ev.k-consume .kind { color: var(--consume); }
.ev.k-phase { border-color: var(--phase); } .ev.k-phase .kind { color: var(--phase); }
.ev.k-mjai { border-color: var(--hit); } .ev.k-mjai .kind { color: var(--hit); }
.ev.k-crash, .ev.k-exception { border-color: var(--exc); border-left-width: 4px; background: color-mix(in srgb, var(--exc) 7%, transparent); }
.ev.k-crash .kind, .ev.k-exception .kind { color: var(--exc); }
.ev.k-exception pre, .ev.k-crash pre { max-height: 360px; overflow: auto; }
#excbar { margin-top: 6px; }
#excbar .exc { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline;
  padding: 4px 10px; border: 1px solid var(--exc); border-radius: 5px; margin-top: 4px;
  color: var(--exc); }
#excbar .exc code { color: var(--ink); }

table.pl { border-collapse: collapse; width: 100%; margin-top: 6px; }
table.pl th, table.pl td { border: 1px solid var(--line); padding: 2px 6px; text-align: left; }
table.pl th { background: var(--panel2); font-weight: 500; color: var(--dim); }
.chg { font-family: var(--mono); font-size: 12px; }
.chg .o { color: var(--race); text-decoration: line-through; }
.chg .n { color: var(--put); }
details > summary { cursor: pointer; color: var(--dim); margin-top: 6px; }
details pre { max-height: 320px; overflow: auto; font: 11.5px/1.4 var(--mono); margin: 4px 0 0;
  background: var(--panel2); padding: 6px; border-radius: 4px; }

#evpanel { margin: 0 14px 30px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 6px; }
#evpanel > summary { padding: 8px 12px; margin: 0; color: var(--ink); font-weight: 600; }
#evpanel .tools { display: flex; gap: 8px; padding: 0 12px 8px; flex-wrap: wrap; align-items: center; }
#evtable { width: 100%; border-collapse: collapse; }
#evtable th, #evtable td { padding: 2px 8px; border-top: 1px solid var(--line); text-align: left;
  vertical-align: top; }
#evtable td.s { font-family: var(--mono); font-size: 11.5px; word-break: break-all; }
#evtable tr:hover { background: var(--panel2); cursor: pointer; }
.evscroll { max-height: 420px; overflow: auto; }
@media (prefers-reduced-motion: no-preference) { .cell { transition: background .1s; } }
</style>
</head>
<body>
<header id="top">
  <div class="titlebar"><b>Dump 查看器</b><span id="meta" class="dim"></span></div>
  <div id="excbar"></div>
  <div class="ctl">
    <button id="first" title="Home">⏮ 第一帧</button>
    <button id="prev" title="←">◀ 上一帧</button>
    <button id="next" title="→">下一帧 ▶</button>
    <button id="last" title="End">最后一帧 ⏭</button>
    <label>跳到 fid <input id="jump" type="text" inputmode="numeric" autocomplete="off"></label>
    <button id="go">跳转</button>
    <span id="pos" class="dim mono"></span>
    <span class="sep"></span>
    <label>按事件跳转
      <select id="kind"></select></label>
    <button id="kprev" title="Shift+←">◀ 上一个</button>
    <button id="knext" title="Shift+→">下一个 ▶</button>
  </div>
  <input id="slider" type="range" min="0" value="0" aria-label="帧位置">
  <div class="lanes" id="lanes"></div>
</header>

<main>
  <section id="left">
    <div id="shotwrap" title="点击放大到原始尺寸 / 再点还原">
      <img id="shot" alt="当前帧">
      <div id="shotmiss">这一帧的图片文件不存在</div>
    </div>
    <div id="framemeta"></div>
  </section>
  <section id="right">
    <div class="fhead" id="fhead"></div>
    <div class="card"><h3><span>识别（watcher step）</span><span class="dim" id="stepnote"></span></h3>
      <div class="body" id="c-step"></div></div>
    <div class="card"><h3><span>入队（watcher put）</span></h3>
      <div class="body" id="c-put"></div></div>
    <div class="card"><h3><span>这一帧之后、下一帧之前发生的事件</span>
      <span class="dim">main 消费 / phase / mjai</span></h3>
      <div class="body" id="c-after"></div></div>
    <div class="card"><h3><span>状态（gamestate 与私有状态）</span></h3>
      <div class="body" id="c-state"></div></div>
  </section>
</main>

<details id="evpanel">
  <summary>全部事件（<span id="evcount"></span>）</summary>
  <div class="tools">
    <label>来源 <select id="fsrc"></select></label>
    <label>类型 <select id="fkind"></select></label>
    <label>包含 <input id="fq" type="text" placeholder="搜索内容" autocomplete="off"></label>
    <span class="dim">点击一行跳到对应的帧</span>
  </div>
  <div class="evscroll"><table id="evtable">
    <thead><tr><th>seq</th><th>fid</th><th>来源</th><th>类型</th><th>内容</th></tr></thead>
    <tbody></tbody></table></div>
</details>

<script id="data" type="application/json">__DATA__</script>
<script>
(() => {
const D = JSON.parse(document.getElementById('data').textContent);
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

const frames = D.frames.slice().sort((a, b) => a.seq - b.seq);
const events = D.events.slice().sort((a, b) => a.seq - b.seq);
const states = D.states.slice().sort((a, b) => a.fid - b.fid);
const N = frames.length;
if (!N) { document.querySelector('main').innerHTML = '<p class="empty">这个 dump 里没有帧。</p>'; return; }

// ───────── 预处理：把事件挂到帧上 ─────────
frames.forEach((f, i) => { f.idx = i; f.rec = []; f.after = []; });
const idxByFid = new Map(frames.map(f => [f.fid, f.idx]));
const evBySeq = new Map(events.map(e => [e.seq, e]));

function lastFrameBefore(seq) {            // 最后一个 seq 小于给定值的帧下标，没有返回 -1
  let lo = 0, hi = N - 1, r = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (frames[m].seq < seq) { r = m; lo = m + 1; } else hi = m - 1; }
  return r;
}
const stable = v => JSON.stringify(v, (k, x) => (x && typeof x === 'object' && !Array.isArray(x))
  ? Object.keys(x).sort().reduce((o, kk) => (o[kk] = x[kk], o), {}) : x);

const lastPut = {};
events.forEach(ev => {
  ev.after = lastFrameBefore(ev.seq);
  if (ev.kind === 'put') {                    // put 与 consume 按「队列 + 内容」配对
    ev.key = ev.q + '|' + stable(ev.item); lastPut[ev.key] = ev;
  } else if (ev.kind === 'consume') {
    const p = lastPut[ev.q + '|' + stable(ev.item)];
    if (p && p.consumedSeq == null) { p.consumedSeq = ev.seq; ev.fromSeq = p.seq; }
  }
  const own = ev.src === 'watcher' && idxByFid.has(ev.fid) && ['step', 'put'].includes(ev.kind);
  ev.home = own ? idxByFid.get(ev.fid) : Math.max(ev.after, 0);
  if (own) frames[ev.home].rec.push(ev);
  else if (ev.after >= 0) frames[ev.after].after.push(ev);
});

function stateIdx(fid) {                      // 不晚于 fid 的最新快照
  let lo = 0, hi = states.length - 1, r = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (states[m].fid <= fid) { r = m; lo = m + 1; } else hi = m - 1; }
  return r;
}
const isExc = e => e.kind === 'exception' || e.kind === 'crash';
const OUT_KEYS = ['interrupt', 'end', 'cur', 'last', 'active', 'tsumo', 'dahai', 'meld'];
let ph = null, ei = 0;
frames.forEach(f => {
  while (ei < events.length && events[ei].seq < f.seq) { if (events[ei].kind === 'phase') ph = events[ei].new; ei++; }
  f.phase = ph;
  f.step = f.rec.find(e => e.kind === 'step') || null;
  const o = f.step ? f.step.out || {} : {};
  f.hit = !!(o.interrupt || o.end || o.tsumo || o.dahai || o.meld);
  f.race = !!(f.step && f.step.gs_changed);
  f.si = stateIdx(f.fid);
  f.newSnap = f.si >= 0 && states[f.si].fid === f.fid;
});

// ───────── 时间线（5 条泳道）+ 跳转类型 ─────────
const LANES = [
  { key: 'put', label: 'put', test: f => f.rec.some(e => e.kind === 'put'), name: '有 put 入队的帧' },
  { key: 'hit', label: '识别', test: f => f.hit, name: '识别到内容的帧（摸牌/打牌/副露/中断）' },
  { key: 'consume', label: '消费', test: f => f.after.some(e => e.kind === 'consume'), name: 'main 有消费的帧' },
  { key: 'phase', label: 'phase', test: f => f.after.some(e => e.kind === 'phase'), name: 'phase 变化的帧' },
  { key: 'race', label: '竞态', test: f => f.race, name: 'step 期间 gamestate 被改动的帧' },
  { key: 'exc', label: '异常', test: f => f.after.some(isExc), name: '有异常记录的帧' },
];
const KINDS = [...LANES,
  { key: 'mjai', test: f => f.after.some(e => e.kind === 'mjai'), name: '产生 mjai 事件的帧' },
  { key: 'snap', test: f => f.newSnap, name: '状态快照变化的帧' },
  { key: 'mainframe', test: f => f.thread !== 'watcher', name: 'main 线程取的帧' }];
$('#kind').innerHTML = KINDS.map(k => `<option value="${k.key}">${esc(k.name)}</option>`).join('');

const lanesEl = $('#lanes');
lanesEl.innerHTML = LANES.map(l => `<div class="lbl">${l.label}</div>` +
  `<div class="cells" id="lane-${l.key}" style="grid-template-columns:repeat(${N},minmax(2px,1fr))"></div>`).join('');
LANES.forEach(l => {
  const el = $('#lane-' + l.key);
  el.innerHTML = frames.map(f => `<div class="cell ${l.key}${l.test(f) ? ' on' : ''}" data-jump="${f.idx}" title="fid ${f.fid}"></div>`).join('');
});

// ───────── 渲染 ─────────
const slider = $('#slider'); slider.max = N - 1;
let cur = -1;
const fmt = v => (v === null || v === undefined) ? '<span class="nul">null</span>'
  : (typeof v === 'object' ? '<code>' + esc(JSON.stringify(v)) + '</code>' : esc(v));
const HIDE = new Set(['fid', 'kind', 'src', 'thread', 'seq', 't', 'after', 'key', 'home', 'consumedSeq', 'fromSeq']);
function payloadPre(ev, skip) {
  const lines = Object.keys(ev).filter(k => !HIDE.has(k) && !(skip && skip.has(k)))
    .map(k => esc(k) + ': ' + esc(typeof ev[k] === 'object' ? JSON.stringify(ev[k]) : ev[k]));
  return lines.length ? '<pre>' + lines.join('\n') + '</pre>' : '';
}
const rel = t => ((t - frames[0].t) >= 0 ? '+' : '') + (t - frames[0].t).toFixed(3) + 's';
const linkTo = (idx, text) => `<a href="#" data-jump="${idx}">${esc(text)}</a>`;

function evCard(ev) {
  const meta = `<span class="meta">seq ${ev.seq}　${esc(ev.src)}／${esc(ev.thread)}　${rel(ev.t)}</span>`;
  let head = `<span class="kind">${esc(ev.kind)}</span>`, body = '', extra = '';
  if (ev.kind === 'put') {
    head += ` <code>${esc(ev.q)}</code>`;
    const c = ev.consumedSeq != null ? evBySeq.get(ev.consumedSeq) : null;
    extra = c ? `<div>已被 main 消费，见 ${linkTo(c.home, 'fid ' + c.fid)}</div>`
              : '<div class="dim">没有匹配到 main 的消费（被后一次 put 覆盖，或 main 还没取）</div>';
    body = '<pre>' + esc(JSON.stringify(ev.item)) + '</pre>';
  } else if (ev.kind === 'consume') {
    head += ` <code>${esc(ev.q)}</code>`;
    const p = ev.fromSeq != null ? evBySeq.get(ev.fromSeq) : null;
    extra = p ? `<div>取自 ${linkTo(p.home, 'fid ' + p.fid + ' 的 put')}</div>`
              : '<div class="dim">没有找到对应的 put（可能在窗口之前，或 reset 清掉了队列）</div>';
    body = '<pre>' + esc(JSON.stringify(ev.item)) + '</pre>';
  } else if (ev.kind === 'phase') {
    head += ` <code>${esc(ev.old)} → ${esc(ev.new)}</code>`;
  } else if (isExc(ev)) {
    head = `<span class="kind">${ev.kind === 'crash' ? 'watcher 线程崩溃' : '异常'}</span> <code>${esc(ev.type || '')}</code> ${esc(ev.msg ?? ev.err ?? '')}`;
    body = '<pre>' + esc(ev.tb || '') + '</pre>';
  } else if (ev.kind === 'mjai') {
    const m = ev.msg || {};
    head += ` <code>${esc(m.type || '')}</code>`;
    body = '<pre>' + esc(JSON.stringify(m)) + '</pre>';
  } else {
    body = payloadPre(ev);
  }
  return `<div class="ev k-${esc(ev.kind)}"><div class="top">${head}${meta}</div>${extra}${body}</div>`;
}

function stepHTML(f) {
  if (!f.step) return `<div class="empty">这一帧由 <b>${esc(f.thread)}</b> 线程取得（${esc(f.caller)}），没有经过 watcher 识别。</div>`;
  const o = f.step.out || {};
  const keys = OUT_KEYS.concat(Object.keys(o).filter(k => !OUT_KEYS.includes(k)));
  const rows = keys.map(k => {
    if (!(k in o)) return `<tr class="skip"><td>${k}</td><td>本轮没有执行</td></tr>`;
    const v = o[k], hl = v !== null && v !== false && !['cur', 'last', 'active'].includes(k);
    return `<tr class="${hl ? 'hl' : ''}"><td>${k}</td><td>${fmt(v)}</td></tr>`;
  }).join('');
  return `<table class="kv">${rows}</table>`;
}

function flat(o, p, out) {
  if (o && typeof o === 'object') {
    const ks = Object.keys(o);
    if (!ks.length) out[p] = Array.isArray(o) ? '[]' : '{}';
    ks.forEach(k => flat(o[k], p ? p + '.' + k : k, out));
  } else out[p] = o;
  return out;
}
function stateHTML(f) {
  if (f.si < 0) return '<div class="empty">窗口内没有状态快照。</div>';
  const st = states[f.si].state, gs = st.gs || {}, ex = st.extra || {}, w = ex.watcher || {}, g = ex.game || {};
  const top = [['phase', gs.phase], ['current_player', gs.current_player], ['last_player', gs.last_player],
    ['last_dahai', gs.last_dahai], ['my_id', gs.my_id], ['oya', gs.oya], ['dora_markers', gs.dora_markers]];
  let h = `<div class="dim" style="margin-bottom:4px">取自 fid ${states[f.si].fid} 的快照${f.newSnap ? '（本帧新记录）' : '（本帧无变化）'}</div>`;
  h += '<table class="kv">' + top.map(([k, v]) => `<tr><td>${k}</td><td>${fmt(v)}</td></tr>`).join('') + '</table>';
  const pi = gs.player_info || [];
  if (pi.length) {
    h += '<table class="pl"><tr><th>id</th><th>位置</th><th>kawa_index</th><th>riichi_index</th><th>riichi</th><th>副露</th></tr>' +
      pi.map((p, i) => `<tr><td>${i}</td><td>${esc((gs.position || [])[i] ?? '')}</td><td>${fmt(p.kawa_index)}</td>` +
        `<td>${fmt(p.riichi_index)}</td><td>${fmt(p.riichi)}</td>` +
        `<td>${esc((p.melds || []).map(m => m.type).join(', ') || '—')}</td></tr>`).join('') + '</table>';
  }
  if (Object.keys(w).length) {
    const qs = Object.entries(w.queues || {}).filter(([, v]) => v.length)
      .map(([k, v]) => `${k}(${v.length})`).join(', ') || '全部为空';
    h += `<div style="margin-top:6px"><span class="dim">watcher</span> current_player ${fmt(w.current_player)}，队列：${esc(qs)}</div>`;
  }
  if (Object.keys(g).length) h += `<div><span class="dim">game</span> <code>${esc(JSON.stringify(g))}</code></div>`;
  if (f.newSnap && f.si > 0) {
    const a = flat(states[f.si - 1].state, '', {}), b = flat(st, '', {});
    const diff = [...new Set([...Object.keys(a), ...Object.keys(b)])]
      .filter(k => JSON.stringify(a[k]) !== JSON.stringify(b[k]));
    if (diff.length) h += '<div style="margin-top:6px" class="chg">与上一条快照相比的变化：<br>' +
      diff.slice(0, 40).map(k => `${esc(k)}: <span class="o">${esc(JSON.stringify(a[k]))}</span> → <span class="n">${esc(JSON.stringify(b[k]))}</span>`).join('<br>') +
      (diff.length > 40 ? `<br>…另有 ${diff.length - 40} 项` : '') + '</div>';
  }
  return h + `<details><summary>完整 JSON</summary><pre>${esc(JSON.stringify(st, null, 1))}</pre></details>`;
}

function render(i) {
  i = Math.max(0, Math.min(N - 1, i));
  const f = frames[i];
  const prevIdx = cur; cur = i;
  slider.value = i;
  $('#jump').value = f.fid;
  $('#pos').textContent = `第 ${i + 1} / ${N} 帧`;
  LANES.forEach(l => {
    const el = $('#lane-' + l.key);
    if (prevIdx >= 0) el.children[prevIdx].classList.remove('cur');
    el.children[i].classList.add('cur');
  });

  const img = $('#shot');
  $('#shotmiss').style.display = 'none'; img.style.display = 'block';
  img.onerror = () => { img.style.display = 'none'; $('#shotmiss').style.display = 'block'; };
  img.src = 'frames/' + f.file;
  [i - 1, i + 1].forEach(j => { if (j >= 0 && j < N) new Image().src = 'frames/' + frames[j].file; });
  $('#framemeta').innerHTML = `${esc(f.file)}　${esc(f.thread)}　取帧位置 ${esc(f.caller)}　${rel(f.t)}`;

  $('#fhead').innerHTML = `<span class="big">fid ${f.fid}</span>` +
    `<span class="badge">${esc(f.thread)}</span>` +
    `<span>phase <code>${esc(f.phase ?? '未知')}</code></span>` +
    (f.race ? '<span class="badge race" title="watcher 这一轮 step 期间，main 改过 gamestate">step 期间 gamestate 被改动</span>' : '') +
    (f.newSnap ? '<span class="badge newsnap">本帧有新状态快照</span>' : '');

  $('#c-step').innerHTML = stepHTML(f);
  $('#stepnote').textContent = f.step ? `seq ${f.step.seq}` : '';
  const puts = f.rec.filter(e => e.kind !== 'step');
  $('#c-put').innerHTML = puts.length ? puts.map(evCard).join('') : '<div class="empty">这一帧没有 put。</div>';
  $('#c-after').innerHTML = f.after.length ? f.after.map(evCard).join('')
    : '<div class="empty">这一帧之后没有其他事件。</div>';
  $('#c-state').innerHTML = stateHTML(f);
  try { history.replaceState(null, '', '#fid=' + f.fid); } catch (e) {}
}

function findKind(dir) {
  const k = KINDS.find(x => x.key === $('#kind').value);
  for (let j = cur + dir; j >= 0 && j < N; j += dir) if (k.test(frames[j])) { render(j); return; }
}

// ───────── 交互 ─────────
document.addEventListener('click', e => {
  const t = e.target.closest('[data-jump]');
  if (t) { e.preventDefault(); render(+t.dataset.jump); }
});
$('#prev').onclick = () => render(cur - 1);
$('#next').onclick = () => render(cur + 1);
$('#first').onclick = () => render(0);
$('#last').onclick = () => render(N - 1);
$('#kprev').onclick = () => findKind(-1);
$('#knext').onclick = () => findKind(1);
slider.oninput = () => render(+slider.value);
function goFid() {
  const v = parseInt($('#jump').value, 10);
  if (Number.isNaN(v)) return;
  if (idxByFid.has(v)) { render(idxByFid.get(v)); return; }
  let best = 0;                                 // fid 不在窗口里：跳到最近的帧
  frames.forEach((f, j) => { if (Math.abs(f.fid - v) < Math.abs(frames[best].fid - v)) best = j; });
  render(best);
}
$('#go').onclick = goFid;
$('#jump').addEventListener('keydown', e => { if (e.key === 'Enter') goFid(); });
$('#shotwrap').onclick = () => $('#shotwrap').classList.toggle('full');
document.addEventListener('keydown', e => {
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowRight') { e.shiftKey ? findKind(1) : render(cur + 1); e.preventDefault(); }
  else if (e.key === 'ArrowLeft') { e.shiftKey ? findKind(-1) : render(cur - 1); e.preventDefault(); }
  else if (e.key === 'Home') { render(0); e.preventDefault(); }
  else if (e.key === 'End') { render(N - 1); e.preventDefault(); }
});

// ───────── 全部事件面板 ─────────
const uniq = k => [...new Set(events.map(e => e[k]))].sort();
$('#fsrc').innerHTML = '<option value="">全部</option>' + uniq('src').map(s => `<option>${esc(s)}</option>`).join('');
$('#fkind').innerHTML = '<option value="">全部</option>' + uniq('kind').map(s => `<option>${esc(s)}</option>`).join('');
function summary(ev) {
  const r = {}; Object.keys(ev).forEach(k => { if (!HIDE.has(k)) r[k] = ev[k]; });
  const s = JSON.stringify(r); return s.length > 220 ? s.slice(0, 220) + '…' : s;
}
function renderEvents() {
  const src = $('#fsrc').value, kind = $('#fkind').value, q = $('#fq').value.toLowerCase();
  const list = events.filter(e => (!src || e.src === src) && (!kind || e.kind === kind) &&
    (!q || (e.kind + ' ' + summary(e)).toLowerCase().includes(q)));
  $('#evcount').textContent = list.length === events.length ? `${events.length} 条` : `${list.length} / ${events.length} 条`;
  $('#evtable tbody').innerHTML = list.slice(0, 1500).map(e =>
    `<tr data-jump="${e.home}"><td class="mono">${e.seq}</td><td class="mono">${e.fid}</td>` +
    `<td>${esc(e.src)}</td><td>${esc(e.kind)}</td><td class="s">${esc(summary(e))}</td></tr>`).join('') +
    (list.length > 1500 ? `<tr><td colspan="5" class="dim">只显示前 1500 条，请用筛选缩小范围</td></tr>` : '');
}
['#fsrc', '#fkind'].forEach(s => $(s).onchange = renderEvents);
$('#fq').oninput = renderEvents;
renderEvents();

// ───────── 异常横幅 ─────────
const excs = events.filter(isExc);
$('#excbar').innerHTML = excs.slice(0, 3).map(e =>
  `<div class="exc"><b>${e.kind === 'crash' ? 'watcher 线程崩溃' : '异常'}</b> <code>${esc(e.type || '')}: ${esc(e.msg ?? e.err ?? '')}</code> ` +
  `${linkTo(e.home, '跳到出异常的位置')}</div>`).join('');

// ───────── 头部信息 / 初始位置 ─────────
const m = D.meta || {};
$('#meta').textContent = `${m.reason ?? ''}　${m.time ?? ''}　${N} 帧　${events.length} 条事件`;
const setHH = () => document.documentElement.style.setProperty('--hh', $('#top').offsetHeight + 'px');
setHH(); window.addEventListener('resize', setHH);
let start = N - 1;                       // 默认停在最后一帧：异常往往发生在窗口末尾
const hm = /fid=(\d+)/.exec(location.hash);
if (hm && idxByFid.has(+hm[1])) start = idxByFid.get(+hm[1]);
render(start);
})();
</script>
</body>
</html>
"""


if __name__ == '__main__':
    path = build_viewer(DUMP_FOLDER)
    print(f'已生成: {os.path.abspath(path)}')
