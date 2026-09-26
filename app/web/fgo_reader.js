const $ = (id) => document.getElementById(id);
const { escapeHtml } = window.TMRender;
const WAR = new URLSearchParams(location.search).get("war") || "";

function render(data) {
  document.title = data.title + " · FGO 剧情";
  $("doc-title").textContent = data.title;
  $("doc-meta").innerHTML =
    `<span class="work">${escapeHtml(data.part)}</span>　` +
    `${data.chapters.length} 个小节 · ${data.lines.toLocaleString()} 条台词` +
    `<span class="path">来源：${escapeHtml(data.source)}</span>`;
  $("source-tag").textContent = "来源：Atlas Academy（官方中文）";

  const nav = data.nav || {};
  $("counter").textContent = nav.total ? `${nav.index} / ${nav.total} 章` : "";
  const mk = (el, item, label) => {
    if (!item) { el.classList.add("disabled"); el.removeAttribute("href"); el.textContent = label; return; }
    el.href = `fgo_reader.html?war=${item.id}`;
    el.textContent = label + "：" + item.title.slice(0, 14);
  };
  mk($("prev"), nav.prev, "← 上一章");
  mk($("next"), nav.next, "下一章 →");

  $("toc").innerHTML = `<div class="toc-title">本章小节</div>` +
    data.chapters.map((c, i) =>
      `<div class="toc-item" data-sec="${i}"><span class="toc-no">${i + 1}</span>${escapeHtml(c.title)}</div>`).join("");
  $("toc").querySelectorAll(".toc-item").forEach((el) => {
    el.onclick = () => {
      const t = document.getElementById("sec-" + el.dataset.sec);
      if (t) t.scrollIntoView({ block: "start", behavior: "smooth" });
    };
  });

  $("doc-body").innerHTML = data.chapters.map((c, i) => `
    <section class="fgo-section" id="sec-${i}">
      <h2 class="fgo-section-title">${escapeHtml(c.title)}</h2>
      ${c.lines.map((l) => `
        <div class="fgo-line${l.s === "选项" ? " choice" : ""}">
          ${l.s ? `<span class="fgo-speaker">${escapeHtml(l.s)}</span>` : ""}
          <span class="fgo-text">${escapeHtml(l.t).replace(/\n/g, "<br>")}</span>
        </div>`).join("")}
    </section>`).join("");

  $("back").href = "story.html?key=work%3AFGO";
  $("doc-foot").textContent =
    `共 ${data.chapters.length} 个小节、${data.lines.toLocaleString()} 条台词。文本取自 Atlas Academy 的官方中文数据（ODC-BY 1.0），未经改写。`;
}

document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft" && $("prev").href) location.href = $("prev").href;
  if (e.key === "ArrowRight" && $("next").href) location.href = $("next").href;
});

(async () => {
  if (!WAR) { $("doc-title").textContent = "缺少章节参数"; return; }
  try {
    render(await (await fetch("/api/fgo/chapter?id=" + encodeURIComponent(WAR))).json());
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