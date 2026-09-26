const $ = (id) => document.getElementById(id);
const { escapeHtml, render } = window.TMRender;
const TERM = (new URLSearchParams(location.search).get("term") || "").trim();

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("请求失败 " + r.status);
  return r.json();
}

function go(term) {
  location.href = "entry.html?term=" + encodeURIComponent(term);
}

(async () => {
  document.title = TERM ? `「${TERM}」 · 型月搜索` : "词条 · 型月搜索";
  $("to-search").href = "/?q=" + encodeURIComponent(TERM);
  if (!TERM) {
    $("results").innerHTML = `<div class="notice">没有指定词条。</div>`;
    return;
  }
  try {
    const data = await fetchJSON("/api/search?q=" + encodeURIComponent(TERM));
    $("entry-from").textContent = (data.classifications || []).length
      ? "本词条来源明确" : "本词条暂无定义的收录分类";
    render($("results"), data, {
      showScopeBadge: false,
      showClassifications: true,
      onTerm: go,
      onClearScope: () => go(TERM),
    });
  } catch (e) {
    $("results").innerHTML = `<div class="notice">读取失败：${escapeHtml(e.message)}</div>`;
  }
})();
