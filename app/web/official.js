const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const Q = (params.get("q") || "").trim();
const SCOPE = params.get("scope") || "";
const MULTI = params.get("multi") === "1";
const PAGE = 20;
let offset = 0, total = 0, loading = false;
const { escapeHtml, officialCard, wireCards, aliasExact, aliasBanner } = window.TMRender;

function parseTerms(raw) {
  try {
    const values = JSON.parse(raw || "[]");
    return Array.isArray(values) ? values.map((value) => String(value || "").trim()).filter(Boolean).slice(0, 32) : [];
  } catch (_e) { return []; }
}
const TERMS = parseTerms(params.get("terms"));

function resultUrl() {
  return `/api/official?q=${encodeURIComponent(Q)}&offset=${offset}&limit=${PAGE}` +
    (SCOPE ? "&scope=" + encodeURIComponent(SCOPE) : "") +
    (MULTI ? "&multi=1" : "");
}

async function load() {
  if (loading) return;
  loading = true;
  $("more").textContent = "读取中…";
  try {
    if (!MULTI) {
      const alias = await aliasExact(Q);
      const box = $("alias-tip");
      if (alias) { box.innerHTML = aliasBanner(alias); box.classList.remove("hidden"); }
      else { box.innerHTML = ""; box.classList.add("hidden"); }
    } else {
      const box = $("alias-tip");
      box.innerHTML = `<div class="notice multi-term-notice">以下结果满足本次多词检索的有效匹配层级。</div>`;
      box.classList.remove("hidden");
    }

    const data = await (await fetch(resultUrl())).json();
    const highlight = (data.highlight_terms && data.highlight_terms.length) ? data.highlight_terms : TERMS.length ? TERMS : [Q];
    total = data.total;
    if (!offset && !data.items.length) {
      $("items").innerHTML = `<div class="notice">没有找到「<b>${escapeHtml(Q)}</b>」的官方回答或访谈原文。</div>`;
    } else {
      const start = offset;
      $("items").insertAdjacentHTML("beforeend",
        data.items.map((item, index) => officialCard(item, start + index, Q, highlight)).join(""));
      wireCards($("items"));
    }
    offset += data.items.length;
    const counts = data.counts || {};
    $("official-stat").textContent = `已显示 ${offset} / ${total}`;
    $("official-sum").innerHTML =
      (SCOPE ? `范围：<b>${escapeHtml(data.scope_name)}</b>　|　` : "") +
      `共 <b>${total.toLocaleString()}</b> 条　|　问答 <b>${(counts.qa || 0).toLocaleString()}</b>　|　` +
      `访谈出处 <b>${(counts.pointer || 0).toLocaleString()}</b>　|　补充来源 <b>${(counts.supplement || 0).toLocaleString()}</b>`;
    $("load-more").classList.toggle("hidden", !data.has_more);
    $("more").textContent = `加载更多（已显示 ${offset} / ${total}）`;
    $("foot").textContent = "顺序：可拆分问答优先，其次为剧情大全原文出处，最后为补充来源。";
    history.replaceState(null, "", `?q=${encodeURIComponent(Q)}` +
      (SCOPE ? "&scope=" + encodeURIComponent(SCOPE) : "") +
      (MULTI ? "&multi=1" : ""));
  } catch (error) {
    $("foot").textContent = "读取失败：" + error.message;
  }
  loading = false;
}

$("more").onclick = load;
$("q-text").textContent = Q;
document.title = `「${Q}」的全部官方回答与访谈原文 · 型月搜索`;
load();
