const $ = (id) => document.getElementById(id);
const { escapeHtml } = window.TMRender;
let KEY = new URLSearchParams(location.search).get("key") || "";
let TOP_KEY = "", WORK_KEY = "";
let ROUTE_CHILDREN = [];      // 当前作品下的路线/分组（手机端第三行标签）
let tree = [], jpOnly = 0;

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("请求失败 " + r.status);
  return r.json();
}

const isMobile = () => window.matchMedia("(max-width: 760px)").matches;

function renderTree() {
  $("tree").innerHTML = tree.map((top) => {
    const kids = top.children.map((c) => `
      <div class="tree-leaf ${KEY.startsWith(c.key) ? "on" : ""}" data-key="${escapeHtml(c.key)}">
        <span class="name">${escapeHtml(c.name)}</span>
        <span class="n">${c.chapters} 章</span></div>`).join("");
    return `<div class="tree-top">
        <div class="tree-topname">${escapeHtml(top.name)}<span class="n">${top.chapters}</span></div>
        ${kids}</div>`;
  }).join("") || "（暂无剧情文本）";
  $("tree").querySelectorAll(".tree-leaf[data-key]").forEach((el) => {
    el.onclick = () => open(el.dataset.key);
  });
}

// ---- 手机端：分级横向标签栏 ----
function workOf(key) {
  return key.split("||")[0];
}

function syncLevelsFromKey(key) {
  if (key.startsWith("top:")) {
    const t = tree.find((x) => x.key === key);
    TOP_KEY = key;
    WORK_KEY = (t && t.children && t.children.length) ? t.children[0].key : "";
    return;
  }
  WORK_KEY = workOf(key);
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
  const rowTop = `<div class="m-tabrow" data-level="top">` +
    tree.map((t) => tab(t.key, t.name, t.chapters, t.key === TOP_KEY)).join("") + `</div>`;
  const rowWork = `<div class="m-tabrow" data-level="work">` +
    works.map((c) => tab(c.key, c.name, c.chapters, c.key === WORK_KEY)).join("") + `</div>`;
  const rowRoute = `<div class="m-tabrow" data-level="route"${ROUTE_CHILDREN.length ? "" : " hidden"}>` +
    tab(WORK_KEY, "全部", null, KEY === WORK_KEY) +
    ROUTE_CHILDREN.map((c) => tab(c.key, c.name, c.section_count != null ? c.section_count : c.count, KEY === c.key)).join("") + `</div>`;
  $("tree").innerHTML = `<div class="m-tabs">${rowTop}${rowWork}${rowRoute}</div>`;
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
        // 大类没有独立节点：选中该大类下的第一个作品再打开
        const t = tree.find((x) => x.key === key);
        TOP_KEY = key;
        WORK_KEY = (t && t.children && t.children.length) ? t.children[0].key : "";
        ROUTE_CHILDREN = [];
        if (WORK_KEY) open(WORK_KEY);
        return;
      }
      if (level === "work") {
        WORK_KEY = key;
        ROUTE_CHILDREN = [];
      }
      open(key);
    };
  });
}

function renderToc() {
  if (isMobile()) renderMobileTabs();
  else renderTree();
}

function chapterHref(c, workKey) {
  if (c.official) {
    return `official_reader.html?work=${encodeURIComponent(c.official)}&id=${c.id}` +
           (c.section != null ? `&sec=${encodeURIComponent(c.section)}` : "");
  }
  return `reader.html?doc=${c.doc}&start=${c.start}` +
         (c.end != null ? `&end=${c.end}` : "") +
         (c.key ? `&chapter=${encodeURIComponent(c.key)}` : "") +
         `&work=${encodeURIComponent(workKey)}`;
}

async function open(key) {
  KEY = key;
  syncLevelsFromKey(key);
  if (key === WORK_KEY) ROUTE_CHILDREN = [];
  history.replaceState(null, "", "?key=" + encodeURIComponent(key));
  renderToc();
  $("crumbs").innerHTML = "";
  $("panel").innerHTML = `<div class="notice">读取中…</div>`;
  try {
    const data = await fetchJSON("/api/story/node?key=" + encodeURIComponent(key));
    $("crumbs").innerHTML = (data.breadcrumb || [])
      .map((b, i) => `<span class="crumb${i === data.breadcrumb.length - 1 ? " cur" : ""}"
          data-key="${escapeHtml(b.key)}">${escapeHtml(b.name)}</span>`).join("<i>›</i>");
    $("crumbs").querySelectorAll(".crumb").forEach((el) => {
      el.onclick = () => open(el.dataset.key);
    });

    let panelHtml = "";
    if (data.chapters.length) {
      panelHtml += `<div class="chapter-grid">` + data.chapters.map((c, i) => `
        <a class="chapter-card" href="${chapterHref(c, workOf(key))}">
          <span class="ch-no">${i + 1}</span>
          <span class="ch-body"><span class="ch-title">${escapeHtml(c.title)}</span>
          ${c.fgo && c.sections ? `<span class="ch-meta">含 ${c.sections} 个小节</span>` : ""}</span>
          <span class="ch-go">阅读 →</span>
        </a>`).join("") + `</div>`;
    }
    if (data.children.length) {
      if (!isMobile()) ROUTE_CHILDREN = data.children;
      if (isMobile()) renderMobileTabs();
      panelHtml += `<div class="cat-grid">` + data.children.map((c) => {
        const meta = c.kind === "official_section"
          ? ""
          : (c.section_count != null ? `含 ${c.section_count} 小节` : `${c.count} 章`);
        const body = `<span class="cat-name">${escapeHtml(c.name)}</span>
          ${meta ? `<span class="cat-count">${meta}</span>` : ""}
          <span class="cat-go">${c.href ? "阅读 →" : "进入 ›"}</span>`;
        return c.href
          ? `<a class="cat-card" href="${escapeHtml(c.href)}">${body}</a>`
          : `<div class="cat-card" data-key="${escapeHtml(c.key)}">${body}</div>`;
      }).join("") + `</div>`;
    }
    $("panel").innerHTML = panelHtml || `<div class="notice">这一类暂时没有可读的剧情文本。</div>`;
    $("panel").querySelectorAll(".cat-card[data-key]").forEach((el) => {
      el.onclick = () => open(el.dataset.key);
    });
    $("node-name").textContent = data.name;
    $("story-foot").textContent = jpOnly
      ? `另有 ${jpOnly} 篇剧情只存有日文原文，尚未翻译，暂未收录。` : "";
  } catch (e) {
    $("panel").innerHTML = `<div class="notice">读取失败：${escapeHtml(e.message)}</div>`;
  }
}

$("back").onclick = () => {
  const parts = KEY.split("||");
  if (parts.length > 1) open(parts.slice(0, -1).join("||"));
};

(async () => {
  try {
    const data = await fetchJSON("/api/story/tree");
    tree = data.tree || [];
    jpOnly = data.jp_only || 0;
    const flat = [];
    tree.forEach((t) => t.children.forEach((c) => flat.push(c.key)));
    const defaultKey = (tree[0] && tree[0].children && tree[0].children[0]) ? tree[0].children[0].key : "";
    const target = KEY && flat.some((k) => KEY.startsWith(k)) ? KEY : defaultKey;
    syncLevelsFromKey(target || "");
    renderToc();
    if (target) open(target);
  } catch (e) {
    $("tree").textContent = "读取失败：" + e.message;
  }
})();

const mq = window.matchMedia("(max-width: 760px)");
if (mq.addEventListener) mq.addEventListener("change", () => renderToc());
else if (mq.addListener) mq.addListener(() => renderToc());
