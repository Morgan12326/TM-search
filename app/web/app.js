const $ = (id) => document.getElementById(id);
const input = $("q"), sugBox = $("suggest"), results = $("results");
const { escapeHtml, highlight, render } = window.TMRender;
let suggestTimer = null, activeIdx = -1, suggestItems = [];
let TAX = [], MODE = "global", TOP = "", SUB = "";

if (new URLSearchParams(location.search).get("q")) document.body.classList.add("has-results");

const HINTS = ["圣杯战争", "固有结界", "直死之魔眼", "魔术回路", "空想具现化", "令咒", "根源", "十二试炼", "阿瓦隆"];

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("请求失败 " + r.status);
  return r.json();
}

// ---------------- 联想 ----------------
function renderSuggest(items) {
  suggestItems = items;
  activeIdx = -1;
  if (!items.length) { sugBox.classList.add("hidden"); return; }
  sugBox.innerHTML = items.map((it) =>
    `<div class="suggest-item"><span>${highlight(it.t, input.value.trim())}</span>` +
    `<span class="n">${it.alias ? "别名「" + escapeHtml(it.alias) + "」· " : ""}` +
    `出现 ${it.n.toLocaleString()} 次</span></div>`).join("");
  sugBox.classList.remove("hidden");
  sugBox.querySelectorAll(".suggest-item").forEach((el, i) => {
    el.onclick = () => { input.value = items[i].t; doSearch(); };
  });
}

input.addEventListener("input", () => {
  const q = input.value.trim();
  activeIdx = -1;                 // 输入变了，作废旧的联想选中项
  suggestItems = [];
  clearTimeout(suggestTimer);
  if (!q) { sugBox.classList.add("hidden"); return; }
  suggestTimer = setTimeout(async () => {
    try {
      const data = await fetchJSON("/api/suggest?q=" + encodeURIComponent(q));
      renderSuggest(data.items || []);
    } catch (e) { sugBox.classList.add("hidden"); }
  }, 90);
});

// 中文输入法：合成期间的回车只用于上屏，不触发搜索；上屏后再补一次搜索
let imeEnter = false;
input.addEventListener("compositionstart", () => { imeEnter = false; });
input.addEventListener("compositionend", () => {
  if (imeEnter) { imeEnter = false; sugBox.classList.add("hidden"); doSearch(); }
});
input.addEventListener("keydown", (e) => {
  if (e.isComposing || e.keyCode === 229) {
    if (e.key === "Enter") imeEnter = true;   // 记住这次回车，等上屏后再搜
    return;
  }
  const items = sugBox.querySelectorAll(".suggest-item");
  if (e.key === "ArrowDown" && items.length) {
    activeIdx = Math.min(activeIdx + 1, items.length - 1); paint(items); e.preventDefault();
  } else if (e.key === "ArrowUp" && items.length) {
    activeIdx = Math.max(activeIdx - 1, -1); paint(items); e.preventDefault();
  } else if (e.key === "Enter") {
    if (activeIdx >= 0 && suggestItems[activeIdx]) input.value = suggestItems[activeIdx].t;
    sugBox.classList.add("hidden");
    doSearch();
  } else if (e.key === "Escape") { sugBox.classList.add("hidden"); }
});

function paint(items) { items.forEach((el, i) => el.classList.toggle("active", i === activeIdx)); }

document.addEventListener("click", (e) => {
  if (!e.target.closest(".searchrow")) sugBox.classList.add("hidden");
});

$("go").onclick = doSearch;

// ---------------- 搜索模式 / 范围 ----------------
function currentScope() {
  if (MODE !== "local") return "";
  return SUB || TOP;
}

function buildTops() {
  const sel = $("top");
  sel.innerHTML = TAX.map((t) => `<option value="${t.key}">${t.name}（${t.docs} 篇）</option>`).join("");
  if (!TAX.some((t) => t.key === TOP)) TOP = TAX.length ? TAX[0].key : "";
  sel.value = TOP;
  buildSubs();
}

function buildSubs() {
  const t = TAX.find((x) => x.key === TOP);
  const sel = $("sub");
  if (!t) { sel.innerHTML = ""; return; }
  const opts = [`<option value="">整个 ${t.name}</option>`];
  t.options.forEach((o) => {
    opts.push(`<option value="${o.key}">${o.label}（${o.docs}）</option>`);
    (o.subs || []).forEach((s) => opts.push(`<option value="${s.key}">　└ ${s.label}（${s.docs}）</option>`));
  });
  sel.innerHTML = opts.join("");
  if (![...sel.options].some((o) => o.value === SUB)) SUB = "";
  sel.value = SUB;
}

function onModeChange(rerun) {
  MODE = $("mode").value;
  const local = MODE === "local";
  $("top").classList.toggle("hidden", !local);
  $("sub").classList.toggle("hidden", !local);
  if (local && !TOP && TAX.length) buildTops();
  if (rerun && input.value.trim()) doSearch();
}

// ---------------- 检索 ----------------
async function doSearch() {
  const q = input.value.trim();
  if (!q) return;
  document.body.classList.add("has-results");
  sugBox.classList.add("hidden");
  $("hint").classList.add("hidden");
  results.innerHTML = `<div class="section-title">检索中…</div>`;
  const scope = currentScope();
  try {
    const url = "/api/search?q=" + encodeURIComponent(q) +
                (scope ? "&scope=" + encodeURIComponent(scope) : "");
    const data = await fetchJSON(url);
    render(results, data, {
      showScopeBadge: true,
      onTerm: (t) => { input.value = t; doSearch(); },
      onClearScope: () => { $("mode").value = "global"; onModeChange(); doSearch(); },
    });
    history.replaceState(null, "", `?q=${encodeURIComponent(q)}` +
      (MODE === "local" ? `&mode=local&scope=${encodeURIComponent(scope)}` : ""));
  } catch (e) {
    results.innerHTML = `<div class="notice">出错了：${escapeHtml(String(e.message))}</div>`;
  }
}

// ---------------- 初始化 ----------------
(async () => {
  $("hint-chips").innerHTML = HINTS.map((h) =>
    `<span class="chip" data-term="${h}">${h}</span>`).join("");
  $("hint").querySelectorAll(".chip").forEach((el) => {
    el.onclick = () => { input.value = el.dataset.term; doSearch(); };
  });
  $("mode").onchange = () => onModeChange(true);
  $("top").onchange = () => { TOP = $("top").value; SUB = ""; buildSubs(); if (input.value.trim()) doSearch(); };
  $("sub").onchange = () => { SUB = $("sub").value; if (input.value.trim()) doSearch(); };
  try {
    const s = await fetchJSON("/api/status");
    TAX = s.taxonomy || [];
    $("status").textContent =
      `本地语料 ${s.corpus.toLocaleString()} 字 · ${s.docs} 篇文档 · ${s.entries} 条词条 · ${s.qa} 条问答 · 词表 ${s.vocab} 词 · 作者：自寻初梦`;
    const sp = new URLSearchParams(location.search);
    const sc = sp.get("scope") || "";
    if (sc.startsWith("sub:") || sc.startsWith("work:")) {
      const w = sc.startsWith("sub:") ? sc.slice(4).split("|")[0] : sc.slice(5);
      const t = TAX.find((x) => x.options.some((o) => o.key === "work:" + w));
      if (t) { TOP = t.key; SUB = sc; }
    } else if (sc) {
      TOP = sc;
    }
    buildTops();
    if (sp.get("mode") === "local") { $("mode").value = "local"; onModeChange(false); }
  } catch (e) { /* 忽略 */ }
  const init = new URLSearchParams(location.search).get("q");
  if (init) { input.value = init; doSearch(); }
})();



