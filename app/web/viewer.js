const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const Q = (params.get("q") || "").trim();
let TERMS = [Q].filter(Boolean);
try {
  const parsed = JSON.parse(params.get("terms") || "[]");
  if (Array.isArray(parsed) && parsed.length) TERMS = parsed;
} catch (_e) { /* 使用 q 回退 */ }
const DOC = parseInt(params.get("doc") || "-1", 10);
const BLOCK = parseInt(params.get("block") || "-1", 10);
const START = params.get("start");
const END = params.get("end");
const CHAPTER = params.get("chapter") || "";
const WORK = params.get("work") || "";
let marks = [], cur = 0;

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

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

function render(data) {
  const d = data.doc;
  document.title = d.title + " · 型月搜索";
  $("doc-title").textContent = d.title;
  const meta = d.meta || {};
  const bits = [`<span class="work">${escapeHtml(d.work)}</span>`,
                escapeHtml(d.kind),
                `<span class="path">语料文件：${escapeHtml(d.file)}</span>`];
  if (meta["译者"] || meta["翻译"] || meta["录入"]) {
    bits.splice(2, 0, "译者／录入：" + escapeHtml(meta["译者"] || meta["翻译"] || meta["录入"]));
  }
  $("doc-meta").innerHTML = bits.join("　·　");

  const body = $("doc-body");
  body.innerHTML = data.blocks.map((b, i) => {
    if (b.lang === "ja") {
      return `<div class="jp-block" data-ord="${b.o}">
        <div class="jp-hint">▸ 此处为日文原文（尚未翻译），点击展开</div>
        <div class="jp-text hidden">${escapeHtml(b.t)}</div>
      </div>`;
    }
    const isTarget = b.o === data.target;
    return `<div class="para${isTarget ? " target" : ""}" data-ord="${b.o}" data-i="${i}">
      ${highlight(b.t, TERMS)}
    </div>`;
  }).join("");

  marks = Array.from(body.querySelectorAll("mark"));
  const target = body.querySelector(".para.target");
  const total = marks.length;
  $("counter").textContent = total ? `本页 ${total} 处` : "本页无匹配";
  if (target) {
    const idx = marks.findIndex((m) => target.contains(m));
    cur = idx >= 0 ? idx : 0;
  }
  if (total) { focusMark(true); } else if (target) { target.scrollIntoView({ block: "center" }); }

  const jpCount = data.untranslated;
  if (jpCount) {
    $("jp-label").classList.remove("hidden");
    $("doc-foot").textContent =
      `本文档共 ${data.blocks.length} 段，其中 ${jpCount} 段仍是日文原文，未参与中文检索（勾选上方开关可查看）。`;
  } else {
    $("doc-foot").textContent = `本文档共 ${data.blocks.length} 段，全部为中文。`;
  }
}

function focusMark(scroll) {
  marks.forEach((m, i) => m.classList.toggle("cur", i === cur));
  const m = marks[cur];
  if (m && scroll) m.scrollIntoView({ block: "center", behavior: "smooth" });
}

$("prev").onclick = () => { if (marks.length) { cur = (cur - 1 + marks.length) % marks.length; focusMark(true); } };
$("next").onclick = () => { if (marks.length) { cur = (cur + 1) % marks.length; focusMark(true); } };
$("jp-show").onchange = (e) => {
  document.querySelectorAll(".jp-block").forEach((el) => {
    el.querySelector(".jp-text").classList.toggle("hidden", !e.target.checked);
    el.querySelector(".jp-hint").textContent = e.target.checked
      ? "▾ 日文原文（尚未翻译）" : "▸ 此处为日文原文（尚未翻译），点击展开";
  });
};
document.querySelectorAll(".jp-hint").forEach(() => {});
$("doc-body").addEventListener("click", (e) => {
  const hint = e.target.closest(".jp-hint");
  if (!hint) return;
  const box = hint.parentElement.querySelector(".jp-text");
  const show = box.classList.contains("hidden");
  box.classList.toggle("hidden", !show);
  hint.textContent = show ? "▾ 日文原文（尚未翻译）" : "▸ 此处为日文原文（尚未翻译），点击展开";
});

document.addEventListener("keydown", (e) => {
  if (e.key === "n") $("next").click();
  if (e.key === "p") $("prev").click();
});

(async () => {
  if (DOC < 0) { $("doc-title").textContent = "缺少文档参数"; return; }
  try {
    let url = `/api/doc?id=${DOC}&block=${BLOCK}&q=${encodeURIComponent(Q)}`;
    if (START != null) url += `&start=${encodeURIComponent(START)}`;
    if (END != null) url += `&end=${encodeURIComponent(END)}`;
    if (CHAPTER) url += `&chapter=${encodeURIComponent(CHAPTER)}`;
    if (WORK) url += `&work=${encodeURIComponent(WORK)}`;
    const r = await fetch(url);
    render(await r.json());
  } catch (err) {
    $("doc-title").textContent = "读取失败：" + err.message;
  }
})();
