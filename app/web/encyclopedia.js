const $ = (id) => document.getElementById(id);
const { escapeHtml } = window.TMRender;
const params = new URLSearchParams(location.search);
let LEAF_KEY = params.get("key") || "";   // 当前实际加载的词条分类（work 或 sub）
let TOP_KEY = "", WORK_KEY = "";
let office = 0, filter = "", currentCat = "", loading = false, tree = [];
let catFilter = params.get("cat") || "";   // 脚注筛选（点 chips 切换，再点一次取消）
const PAGE = 100;

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("请求失败 " + r.status);
  return r.json();
}

const isMobile = () => window.matchMedia("(max-width: 760px)").matches;

// 「只有子项、没有自身词条」的分组标题怎么显示（桌面树使用）：
const HEAD_DROP = new Set(["work:FE"]);
const HEAD_PLAIN = new Set(["work:月姬"]);

function treeRow(c, asSub) {
  const cls = `tree-leaf${asSub ? " sub" : ""}${LEAF_KEY === c.key ? " on" : ""}`;
  const name = (asSub ? "└ " : "") + escapeHtml(c.name);
  return `<div class="${cls}" data-key="${escapeHtml(c.key)}">
      <span class="name">${name}</span><span class="n">${c.terms}</span></div>`;
}

function renderTree() {
  const html = tree.map((top) => {
    const kids = top.children.map((c) => {
      const drop = !c.own && (c.children || []).length && HEAD_DROP.has(c.key);
      const subs = (c.children || []).map((s) => treeRow(s, !drop)).join("");
      if (!c.own && subs) {
        if (drop) return subs;
        const cls = HEAD_PLAIN.has(c.key) ? "tree-leaf head plain" : "tree-leaf head";
        return `<div class="${cls}"><span class="name">${escapeHtml(c.name)}</span>
          <span class="n">${c.terms}（分 ${c.children.length} 类）</span></div>${subs}`;
      }
      return treeRow(c, false) + subs;
    }).join("");
    return `<div class="tree-top">
        <div class="tree-topname">${escapeHtml(top.name)}<span class="n">${top.terms}</span></div>
        ${kids}
      </div>`;
  }).join("");
  $("tree").innerHTML = html || "（暂无词条）";
  $("tree").querySelectorAll(".tree-leaf").forEach((el) => {
    el.onclick = () => selectLeaf(el.dataset.key);
  });
}

// ---- 手机端：分级横向标签栏 ----
function syncLevelsFromLeaf(key) {
  WORK_KEY = key.startsWith("sub:") ? "work:" + key.slice(4).split("|", 1)[0] : key;
  for (const t of tree) {
    if ((t.children || []).some((c) => c.key === WORK_KEY)) {
      TOP_KEY = t.key;
      return;
    }
  }
  TOP_KEY = (tree[0] && tree[0].key) || "";
}

function tab(key, label, n, on) {
  return `<button class="m-tab${on ? " on" : ""}" data-key="${escapeHtml(key)}">${escapeHtml(label)}` +
    (n != null ? `<span class="n">${n}</span>` : "") + `</button>`;
}

function renderMobileTabs() {
  const prevScroll = {};
  $("tree").querySelectorAll(".m-tabrow").forEach((r) => {
    prevScroll[r.dataset.level] = r.scrollLeft;
  });
  const top = tree.find((t) => t.key === TOP_KEY) || tree[0];
  const works = top ? (top.children || []) : [];
  const work = works.find((c) => c.key === WORK_KEY) || works[0];
  const subs = work ? (work.children || []) : [];
  const rowTop = `<div class="m-tabrow" data-level="top">` +
    tree.map((t) => tab(t.key, t.name, t.terms, t.key === TOP_KEY)).join("") + `</div>`;
  const rowWork = `<div class="m-tabrow" data-level="work">` +
    works.map((c) => tab(c.key, c.name, c.terms, c.key === WORK_KEY)).join("") + `</div>`;
  const rowSub = `<div class="m-tabrow" data-level="sub"${subs.length ? "" : " hidden"}>` +
    tab(WORK_KEY, "全部", work ? work.terms : 0, LEAF_KEY === WORK_KEY) +
    subs.map((s) => tab(s.key, s.name, s.terms, LEAF_KEY === s.key)).join("") + `</div>`;
  $("tree").innerHTML = `<div class="m-tabs">${rowTop}${rowWork}${rowSub}</div>`;
  // 还原各标签行的横向位置：点选分类后不回到最左端
  $("tree").querySelectorAll(".m-tabrow").forEach((r) => {
    const s = prevScroll[r.dataset.level];
    if (s) r.scrollLeft = s;
  });
  $("tree").querySelectorAll(".m-tab").forEach((el) => {
    el.onclick = () => {
      const key = el.dataset.key;
      const level = el.closest(".m-tabrow").dataset.level;
      if (level === "top") {
        const t = tree.find((x) => x.key === key);
        TOP_KEY = key;
        WORK_KEY = (t && t.children && t.children.length) ? t.children[0].key : "";
        LEAF_KEY = WORK_KEY;
      } else if (level === "work") {
        WORK_KEY = key;
        LEAF_KEY = key;
      } else {
        LEAF_KEY = key;
      }
      renderMobileTabs();
      load(false);
    };
  });
}

function renderToc() {
  if (isMobile()) renderMobileTabs();
  else renderTree();
}

function catHeader(cat, n) {
  return `<div class="cat-head">${escapeHtml(cat)}<span>${n} 条</span></div>`;
}

function termHtml(it) {
  const other = it.leaves.filter((l) => l !== it.leafName);
  return `<div class="wiki-term" data-term="${escapeHtml(it.term)}">
    <div class="wt-name">${escapeHtml(it.term)}
      ${it.defs > 1 ? `<span class="wt-tag">${it.defs} 条定义</span>` : ""}
      ${it.cat ? `<span class="wt-cat">${escapeHtml(it.cat)}</span>` : ""}</div>
    <div class="wt-def${it.long ? " clamped" : ""}">${escapeHtml(it.def)}</div>
    ${it.long ? `<div class="wt-more">展开定义 ▾</div>` : ""}
    <div class="wt-meta">出处：《${escapeHtml(it.source.title)}》 · ${escapeHtml(it.source.work)} · ${escapeHtml(it.source.kind)}
      ${other.length ? `　|　也收录于：${other.map(escapeHtml).join("、")}` : ""}</div>
  </div>`;
}

async function load(more) {
  if (!LEAF_KEY || loading) return;
  loading = true;
  $("more").textContent = "读取中…";
  try {
    const url = `/api/wiki/leaf?key=${encodeURIComponent(LEAF_KEY)}&offset=${more ? office : 0}` +
                `&limit=${PAGE}${filter ? "&filter=" + encodeURIComponent(filter) : ""}` +
                `${catFilter ? "&cat=" + encodeURIComponent(catFilter) : ""}`;
    const data = await fetchJSON(url);
    if (!more) {
      $("terms").innerHTML = "";
      office = 0;
      currentCat = "";
      $("leaf-name").textContent = data.name;
      if (catFilter && !data.categories.some(([c]) => c === catFilter)) {
        catFilter = "";
        loading = false;
        return load(false);
      }
      $("leaf-cats").innerHTML = data.categories.map(([c, n]) =>
        `<span class="chip cat-chip${c === catFilter ? " on" : ""}" data-cat="${escapeHtml(c)}">${escapeHtml(c)} ${n}</span>`).join("");
      $("leaf-cats").querySelectorAll(".cat-chip").forEach((el) => {
        el.onclick = () => {
          catFilter = (catFilter === el.dataset.cat) ? "" : el.dataset.cat;
          load(false);
        };
      });
    }
    const bits = [];
    if (filter) bits.push(`筛选「${escapeHtml(filter)}」`);
    if (catFilter) bits.push(`脚注：${escapeHtml(catFilter)}`);
    $("leaf-stat").innerHTML = bits.length
      ? `${bits.join("　|　")}　<b>${data.total}</b> 条`
      : `共 <b>${data.total}</b> 条语义`;
    const buf = [];
    data.items.forEach((it) => {
      const cat = it.cat || "未分类";
      if (!catFilter && cat !== currentCat) {
        currentCat = cat;
        const n = (data.categories.find(([c]) => c === cat) || [, 0])[1];
        buf.push(catHeader(cat, filter ? "" : n));
      }
      it.leafName = data.name;
      buf.push(termHtml(it));
    });
    if (!data.items.length && !more) {
      buf.push(`<div class="notice">该分类下没有匹配的词条。换一个脚注，或清空搜索框。</div>`);
    }
    $("terms").insertAdjacentHTML("beforeend", buf.join(""));
    $("terms").querySelectorAll(".wiki-term").forEach((el) => {
      if (el.dataset.bound) return;
      el.dataset.bound = "1";
      el.onclick = () => { location.href = "entry.html?term=" + encodeURIComponent(el.dataset.term); };
      const more = el.querySelector(".wt-more");
      if (more) {
        more.onclick = (ev) => {
          ev.stopPropagation();
          const box = el.querySelector(".wt-def");
          box.classList.toggle("clamped");
          more.textContent = box.classList.contains("clamped") ? "展开定义 ▾" : "收起定义 ▴";
        };
      }
    });
    office = (more ? office : 0) + data.items.length;
    $("load-more").classList.toggle("hidden", !data.has_more);
    $("more").textContent = `加载更多（已显示 ${office} / ${data.total}）`;
    $("wiki-foot").textContent = "点上方脚注可只看该类词条（再点一次取消）；点任意词条进入详情页。";
    history.replaceState(null, "", `?key=${encodeURIComponent(LEAF_KEY)}` +
      (catFilter ? "&cat=" + encodeURIComponent(catFilter) : ""));
  } catch (e) {
    $("wiki-foot").textContent = "读取失败：" + e.message;
  }
  loading = false;
}

function selectLeaf(key) {
  LEAF_KEY = key;
  syncLevelsFromLeaf(key);
  history.replaceState(null, "", "?key=" + encodeURIComponent(key));
  renderToc();
  window.scrollTo({ top: 0 });
  load(false);
}

let filterTimer = null;
async function applyFilter() {
  const raw = $("filter").value.trim();
  const box = $("alias-tip");
  const hit = await window.TMRender.aliasExact(raw);
  if (hit) {
    const extra = await window.TMRender.aliasPrefix(raw);
    box.innerHTML = window.TMRender.aliasBanner(hit, extra);
    box.classList.remove("hidden");
    filter = hit.note ? raw : (hit.term || raw);
  } else {
    box.innerHTML = "";
    box.classList.add("hidden");
    filter = raw;
  }
  load(false);
}
$("filter").oninput = () => {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(applyFilter, 200);
};
$("more").onclick = () => load(true);

(async () => {
  try {
    const data = await fetchJSON("/api/wiki/tree");
    tree = data.tree || [];
    const flat = [];
    tree.forEach((t) => t.children.forEach((c) => {
      if (c.own || (c.children || []).length) flat.push(c.key);
      (c.children || []).forEach((s) => flat.push(s.key));
    }));
    const defaultWork = (tree[0] && tree[0].children && tree[0].children[0]) ? tree[0].children[0].key : "";
    if (!LEAF_KEY || !flat.includes(LEAF_KEY)) LEAF_KEY = flat[0] || defaultWork || "";
    syncLevelsFromLeaf(LEAF_KEY);
    renderToc();
    if (LEAF_KEY) load(false);
  } catch (e) {
    $("tree").textContent = "读取失败：" + e.message;
  }
})();

const mq = window.matchMedia("(max-width: 760px)");
if (mq.addEventListener) mq.addEventListener("change", () => renderToc());
else if (mq.addListener) mq.addListener(() => renderToc());