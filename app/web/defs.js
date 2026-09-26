/* 全部词解卡：分页列出该查询的所有词解卡，顺序与搜索页预览完全一致。 */
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const Q = (params.get("q") || "").trim();
const SCOPE = params.get("scope") || "";
const MULTI = params.get("multi") === "1";
const PAGE = 20;
let offset = 0, total = 0, loading = false;
const { escapeHtml, defCard, wireCards, aliasExact, aliasBanner } = window.TMRender;

async function load() {
  if (loading) return;
  loading = true;
  $("more").textContent = "读取中…";
  try {
    if (!MULTI) {
      const al = await aliasExact(Q);
      const ab = $("alias-tip");
      if (al) { ab.innerHTML = aliasBanner(al); ab.classList.remove("hidden"); }
      else { ab.innerHTML = ""; ab.classList.add("hidden"); }
    }

    const url = `/api/defs?q=${encodeURIComponent(Q)}&offset=${offset}&limit=${PAGE}` +
                (SCOPE ? "&scope=" + encodeURIComponent(SCOPE) : "") +
                (MULTI ? "&multi=1" : "");
    const data = await (await fetch(url)).json();
    const HL = (data.highlight_terms && data.highlight_terms.length) ? data.highlight_terms : [Q];
    if (MULTI) {
      const ab = $("alias-tip");
      ab.innerHTML = data.multi_term && data.multi_term.notice
        ? `<div class="notice multi-term-notice">${escapeHtml(data.multi_term.notice)}</div>` : "";
      ab.classList.toggle("hidden", !ab.innerHTML);
    }
    total = data.total;
    const start = offset;
    $("items").insertAdjacentHTML("beforeend",
      data.items.map((d, i) => defCard(d, start + i, Q, HL)).join(""));
    wireCards($("items"));
    offset += data.items.length;
    $("defs-stat").textContent = `已显示 ${offset} / ${total}`;
    $("defs-sum").innerHTML =
      (SCOPE ? `范围：<b>${escapeHtml(data.scope_name)}</b>　|　` : "") +
      `共 <b>${total.toLocaleString()}</b> 张词解卡　|　已显示 <b>${offset.toLocaleString()}</b> 张`;
    $("load-more").classList.toggle("hidden", !data.has_more);
    $("more").textContent = `加载更多（已显示 ${offset} / ${total}）`;
    $("foot").textContent = MULTI
      ? "顺序：同一放宽层级内，按全部命中词条的最短文本跨度排序；同一术语只显示一张。"
      : "顺序：该词条本身的词解 → 正文提到该词的词解 → 词条名含该词的词解；同一术语只显示一张。";
    history.replaceState(null, "", `?q=${encodeURIComponent(Q)}` +
      (SCOPE ? "&scope=" + encodeURIComponent(SCOPE) : "") +
      (MULTI ? "&multi=1" : ""));
  } catch (e) {
    $("foot").textContent = "读取失败：" + e.message;
  }
  loading = false;
}

$("more").onclick = load;
$("q-text").textContent = Q;
document.title = `「${Q}」的全部词解卡 · 型月搜索`;
load();
