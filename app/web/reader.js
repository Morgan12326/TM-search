const $ = (id) => document.getElementById(id);
const { escapeHtml } = window.TMRender;
const params = new URLSearchParams(location.search);
const DOC = parseInt(params.get("doc") || "-1", 10);
const START = params.get("start");
const END = params.get("end");
const CHAPTER = params.get("chapter") || "";
const WORK = params.get("work") || "";
let SECTIONS = [];

function jumpUrl(c) {
  if (!c) return null;
  return `reader.html?doc=${c.doc}&start=${c.start}` +
         (c.end != null ? `&end=${c.end}` : "") +
         (c.key ? `&chapter=${encodeURIComponent(c.key)}` : "") +
         (WORK ? `&work=${encodeURIComponent(WORK)}` : "");
}

function render(data) {
  const d = data.doc, st = data.story || {};
  document.title = (st.title || d.title) + " · 剧情大全";
  $("doc-title").textContent = st.title || d.title;
  const meta = d.meta || {};
  const bits = [`<span class="work">${escapeHtml(st.work_name || d.work)}</span>`];
  if (st.route) bits.push(escapeHtml(st.route));
  if (st.group) bits.push(escapeHtml(st.group));
  bits.push(escapeHtml(d.kind));
  const who = meta["译者"] || meta["翻译"] || meta["录入"];
  if (who) bits.push("译者／录入：" + escapeHtml(who));
  bits.push(`<span class="path">语料文件：${escapeHtml(d.file)}</span>`);
  $("doc-meta").innerHTML = bits.join("　·　");

  $("doc-body").innerHTML = data.blocks.map((b) => {
    if (b.lang === "ja") {
      return `<div class="jp-block" data-ord="${b.o}">
        <div class="jp-hint">▸ 此处为日文原文（尚未翻译），点击展开</div>
        <div class="jp-text hidden">${escapeHtml(b.t)}</div></div>`;
    }
    return `<div class="para" data-ord="${b.o}">${escapeHtml(b.t)}</div>`;
  }).join("");

  // 章内小节目录（FGO 这类长章节）
  if (SECTIONS.length >= 2) {
    const toc = document.createElement("div");
    toc.className = "chapter-toc";
    toc.innerHTML = `<div class="toc-title">本章小节</div>` + SECTIONS.map((s, i) =>
      `<div class="toc-item" data-block="${s.block}"><span class="toc-no">${i + 1}</span>${escapeHtml(s.title)}</div>`).join("");
    $("doc-body").parentNode.insertBefore(toc, $("doc-body"));
    toc.querySelectorAll(".toc-item").forEach((el) => {
      el.onclick = () => {
        const t = document.querySelector(`.para[data-ord="${el.dataset.block}"]`);
        if (t) t.scrollIntoView({ block: "start", behavior: "smooth" });
      };
    });
  }

  $("back").href = "story.html" + (WORK ? "?key=" + encodeURIComponent(WORK) : "");
  $("counter").textContent = st.total ? `${st.route}${st.group ? ` · ${st.group}` : ""}　第 ${st.index} / ${st.total} 章` : "";
  const mk = (el, c, label) => {
    const url = jumpUrl(c);
    if (!url) { el.classList.add("disabled"); el.removeAttribute("href"); el.textContent = label; return; }
    el.href = url;
    el.textContent = label + (c.title ? "：" + c.title.slice(0, 12) : "");
  };
  mk($("prev"), st.prev, "← 上一章");
  mk($("next"), st.next, "下一章 →");

  if (data.untranslated) {
    $("jp-label").classList.remove("hidden");
    $("doc-foot").textContent =
      `本章共 ${data.blocks.length} 段，另有 ${data.untranslated} 段日文原文（勾选上方开关可显示）。`;
  } else {
    $("doc-foot").textContent = `本章共 ${data.blocks.length} 段。`;
  }
}

$("jp-show").onchange = (e) => {
  document.querySelectorAll(".jp-block").forEach((el) => {
    el.querySelector(".jp-text").classList.toggle("hidden", !e.target.checked);
    el.querySelector(".jp-hint").textContent = e.target.checked
      ? "▾ 日文原文（尚未翻译）" : "▸ 此处为日文原文（尚未翻译），点击展开";
  });
};
$("doc-body").addEventListener("click", (e) => {
  const hint = e.target.closest(".jp-hint");
  if (!hint) return;
  const box = hint.parentElement.querySelector(".jp-text");
  const show = box.classList.contains("hidden");
  box.classList.toggle("hidden", !show);
  hint.textContent = show ? "▾ 日文原文（尚未翻译）" : "▸ 此处为日文原文（尚未翻译），点击展开";
});
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.key === "ArrowLeft" && $("prev").href) location.href = $("prev").href;
  if (e.key === "ArrowRight" && $("next").href) location.href = $("next").href;
});

(async () => {
  if (DOC < 0) { $("doc-title").textContent = "缺少章节参数"; return; }
  const url = `/api/doc?id=${DOC}` + (START ? `&start=${START}` : "") +
              (END ? `&end=${END}` : "") +
              (CHAPTER ? `&chapter=${encodeURIComponent(CHAPTER)}` : "");
  try {
    SECTIONS = [];
    if (WORK) {
      try {
        const leaf = await (await fetch("/api/story/leaf?key=" + encodeURIComponent(WORK))).json();
        for (const r of leaf.routes || []) {
          for (const c of r.chapters) {
            if (c.doc === DOC && String(c.start) === String(START)) SECTIONS = c.sections || [];
          }
        }
      } catch (e) { /* 忽略 */ }
    }
    render(await (await fetch(url)).json());
    window.scrollTo({ top: 0 });
  } catch (e) {
    $("doc-title").textContent = "读取失败：" + e.message;
  }
})();


// ---- 手机端全屏阅读：点击正文呼出/隐藏顶底栏 + 阅读进度条 ----
(function () {
  const body = document.body;
  const bodyEl = $("doc-body");
  if (bodyEl) {
    bodyEl.addEventListener("click", (e) => {
      if (e.target.closest(".jp-hint, .toc-item, a, button, .chapter-toc")) return;
      body.classList.toggle("chrome-on");
    });
  }
  const fill = $("progress-fill");
  const onScroll = () => {
    if (!fill) return;
    const doc = document.documentElement;
    const max = doc.scrollHeight - window.innerHeight;
    const p = max > 0 ? Math.min(100, Math.max(0, (window.scrollY / max) * 100)) : 0;
    fill.style.width = p.toFixed(2) + "%";
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
})();
