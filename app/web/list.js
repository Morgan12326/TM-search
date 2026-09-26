const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const Q = (params.get("q") || "").trim();
let WORK = params.get("work") || "";
let SCOPE = params.get("scope") || "";
const MULTI = params.get("multi") === "1";
function parseTerms(raw) {
  try {
    const values = JSON.parse(raw || "[]");
    if (!Array.isArray(values)) return [];
    const out = [], seen = new Set();
    values.forEach((value) => {
      const term = String(value || "").trim();
      const key = term.toLowerCase();
      if (term && !seen.has(key)) { seen.add(key); out.push(term); }
    });
    return out.slice(0, 32);
  } catch (e) { return []; }
}
const TERMS = parseTerms(params.get("terms"));
let HL = TERMS.length ? TERMS : [Q].filter(Boolean);
const PAGE = 50;
let offset = 0, works = [], loading = false;

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// 片段高亮：与检索规则一致——英文整词、中文子串；同义词共用高亮。
const CJK_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]/;
const PUNCT_RE = /[·・‧．.\s]/;
function termPattern(term) {
  let out = "";
  for (const ch of term) out += PUNCT_RE.test(ch) ? "[·・‧．.\\s]*" : ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (/[A-Za-z]/.test(term) && !CJK_RE.test(term))
    out = "(?<![A-Za-z0-9])" + out + "(?![A-Za-z0-9])";
  return out;
}
function highlight(text, terms) {
  const safe = escapeHtml(text);
  const list = (Array.isArray(terms) ? terms : [terms]).map((x) => String(x || "").trim())
    .filter(Boolean).sort((a, b) => b.length - a.length);
  if (!list.length) return safe;
  return safe.replace(new RegExp(list.map(termPattern).join("|"), "gi"), (m) => `<mark>${m}</mark>`);
}

function multiBadges(o) {
  const values = o && Array.isArray(o.matched_terms) ? o.matched_terms : [];
  if (!values.length) return "";
  return `<div class="multi-badges">` + values.map((value) =>
    `<span>${escapeHtml(value)}</span>`).join("") + `</div>`;
}

function itemHtml(o) {
  const jump = window.TMRender.occurrenceHref(o, Q, HL);
  return `<div class="occ">
    <a class="occ-head" href="${jump}" target="_blank" rel="noopener" title="打开原文并跳到这一处">
      ${(o.path && o.path.length)
        ? o.path.map((p, i) => `<span class="${i === 0 ? "work" : "chapter"}">${escapeHtml(p)}</span>`).join('<span class="sep">›</span>')
        : `<span class="work">${escapeHtml(o.source.work)}</span>
           <span class="doc">《${escapeHtml(o.source.title)}》</span>
           <span class="kind">${escapeHtml(o.source.kind)}</span>`}
      <span class="jump">查看原文 ↗</span></a>
    ${multiBadges(o)}
    <div class="occ-text">${highlight(o.snippet, HL)}</div>
  </div>`;
}

function renderTabs() {
  const all = works.reduce((a, w) => a + w[1], 0);
  const chips = [`<span class="work-tab ${WORK ? "" : "on"}" data-w="">全部作品 <b>${all}</b></span>`]
    .concat(works.map(([w, hits, segs]) =>
      `<span class="work-tab ${WORK === w ? "on" : ""}" data-w="${escapeHtml(w)}">${escapeHtml(w)} <b>${hits}</b><i>／${segs}${MULTI ? "片段" : "段"}</i></span>`));
  $("tabs").innerHTML = chips.join("");
  $("tabs").querySelectorAll(".work-tab").forEach((el) => {
    el.onclick = () => { WORK = el.dataset.w; offset = 0; $("items").innerHTML = ""; load(); };
  });
  const idx = works.findIndex((w) => w[0] === WORK);
  $("prevw").disabled = idx < 0;
  $("nextw").disabled = idx < 0;
  $("prevw").onclick = () => { if (idx >= 0) { WORK = works[(idx - 1 + works.length) % works.length][0]; offset = 0; $("items").innerHTML = ""; load(); } };
  $("nextw").onclick = () => { if (idx >= 0) { WORK = works[(idx + 1) % works.length][0]; offset = 0; $("items").innerHTML = ""; load(); } };
}

async function load() {
  if (loading) return;
  loading = true;
  $("more").textContent = "读取中…";
  try {
    if (!MULTI) {
      const _al = await window.TMRender.aliasExact(Q);
      const _ab = $("alias-tip");
      if (_al) { _ab.innerHTML = window.TMRender.aliasBanner(_al); _ab.classList.remove("hidden"); }
      else { _ab.innerHTML = ""; _ab.classList.add("hidden"); }
    }
    const url = `/api/list?q=${encodeURIComponent(Q)}&work=${encodeURIComponent(WORK)}` +
                `&offset=${offset}&limit=${PAGE}` +
                (SCOPE ? "&scope=" + encodeURIComponent(SCOPE) : "") +
                (MULTI ? "&multi=1" : "") +
                (!MULTI && TERMS.length ? "&terms=" + encodeURIComponent(JSON.stringify(TERMS)) : "");
    const data = await (await fetch(url)).json();
    HL = (data.highlight_terms && data.highlight_terms.length) ? data.highlight_terms : [Q];
    if (MULTI) {
      const _ab = $("alias-tip");
      const _mt = data.multi_term || {};
      const _notice = _mt.notice || (_mt.relaxed
        ? `未能同时包含全部 ${_mt.requested_terms.length} 个词条，已放宽为任意 ${_mt.effective_level} 个词条组共同出现。`
        : `以下段落同时包含全部 ${(_mt.requested_terms || []).length} 个词条。`);
      _ab.innerHTML = `<div class="notice multi-term-notice">${escapeHtml(_notice)}</div>`;
      _ab.classList.remove("hidden");
    }
    if (!works.length) works = data.works;
    renderTabs();
    const hits = data.total, segs = data.passages;
    $("list-sum").innerHTML =
      (SCOPE ? `范围：<b>${escapeHtml(data.scope_name)}</b>　|　` : "") +
      (WORK ? (MULTI ? `本作品共同命中 <b>${hits.toLocaleString()}</b> 个片段`
                        : `本作品命中 <b>${hits.toLocaleString()}</b> 次、<b>${segs}</b> 段`)
            : (MULTI ? `合计命中 <b>${hits.toLocaleString()}</b> 个片段`
                     : `合计命中 <b>${hits.toLocaleString()}</b> 次、同段落合并后 <b>${segs}</b> 条`)) +
      `　|　覆盖 <b>${data.docs}</b> 篇文档` +
      (data.truncated ? `　|　（命中过多，仅统计前 ${segs.toLocaleString()} 段）` : "");
    $("items").insertAdjacentHTML("beforeend", data.items.map(itemHtml).join(""));
    offset += data.items.length;
    $("load-more").classList.toggle("hidden", !data.has_more);
    $("more").textContent = `加载更多（已显示 ${offset} / ${segs}）`;
    $("foot").textContent = `点任意一条的「查看原文 ↗」会打开该文档并跳到那一段。`;
    history.replaceState(null, "", `?q=${encodeURIComponent(Q)}${WORK ? "&work=" + encodeURIComponent(WORK) : ""}` +
      (SCOPE ? "&scope=" + encodeURIComponent(SCOPE) : "") +
      (MULTI ? "&multi=1" : "") +
      (!MULTI && TERMS.length ? "&terms=" + encodeURIComponent(JSON.stringify(TERMS)) : ""));
  } catch (e) {
    $("foot").textContent = "读取失败：" + e.message;
  }
  loading = false;
}

$("more").onclick = load;
$("q-text").textContent = Q;
document.title = `「${Q}」的全部出现位置 · 型月搜索`;
load();
