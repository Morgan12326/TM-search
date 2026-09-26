import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import test from "node:test";
import assert from "node:assert/strict";

const root = path.resolve(import.meta.dirname, "..", "app");
const source = fs.readFileSync(path.join(root, "web", "render.js"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "style.css"), "utf8");
globalThis.window = {};
vm.runInThisContext(source, { filename: "render.js" });

function fakeElement() {
  return {
    innerHTML: "",
    querySelectorAll() { return []; },
    querySelector() { return null; },
  };
}

test("source line wraps a dictionary title exactly once", () => {
  const html = window.TMRender.sourceLine({
    title: "Fate/EXTELLA用语辞典", work: "FEX", kind: "用语辞典", meta: {},
  });
  assert.match(html, /《Fate\/EXTELLA用语辞典》/);
  assert.doesNotMatch(html, /《《|》》/);
});

test("definition title is not highlighted when only the body matches", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "直死之魔眼",
    highlight_terms: ["直死之魔眼"],
    match_mode: "exact",
    definitions: [{
      term: "两仪式（杀阶）", exact: false, match: "body", cat: "从者",
      body: "拥有“直死之魔眼”的少女。",
      source: { title: "FGO 从者资料", work: "FGO", kind: "设定集", meta: {} },
    }],
    interviews: [], qa: [], occurrences: [], related: [], by_work: [], total: 0, docs: 0,
  }, {});
  assert.match(el.innerHTML, /<div class="term">两仪式（杀阶）<span class="cat">从者<\/span><\/div>/);
  assert.match(el.innerHTML, /<mark>直死之魔眼<\/mark>/);
});

test("non-exact definition title highlights only an actual title match", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "直死之魔眼",
    highlight_terms: ["直死之魔眼"],
    match_mode: "exact",
    definitions: [{
      term: "直死之魔眼入门", exact: false, match: "body",
      body: "正文提到了这个能力。",
      source: { title: "测试资料", work: "月姬", kind: "设定集", meta: {} },
    }],
    interviews: [], qa: [], occurrences: [], related: [], by_work: [], total: 0, docs: 0,
  }, {});
  assert.match(el.innerHTML, /<div class="term"><mark>直死之魔眼<\/mark>入门<\/div>/);
});

test("exact definition title remains fully highlighted", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "直死的魔眼",
    highlight_terms: ["直死的魔眼"],
    match_mode: "exact",
    definitions: [{
      term: "直死的魔眼", exact: true, match: "exact",
      body: "精确定义。",
      source: { title: "测试资料", work: "月姬", kind: "设定集", meta: {} },
    }],
    interviews: [], qa: [], occurrences: [], related: [], by_work: [], total: 0, docs: 0,
  }, {});
  assert.match(el.innerHTML, /<div class="term"><mark>直死的魔眼<\/mark><\/div>/);
});

test("official section renders QA and pointer preview with all link", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "Saber",
    highlight_terms: ["Saber"],
    match_mode: "exact",
    definitions: [],
    interviews: [],
    qa: [{ q: "旧区块不应显示", a: "旧问答", source: { title: "旧", work: "FSN", kind: "问答", meta: {} } }],
    official_items: [
      {
        kind: "qa", q: "Saber是谁？", a: "士郎的从者。", a_excerpt: "士郎的从者。", a_truncated: false, doc: 1, block: 2,
        matched_terms: ["Saber"], path: ["访谈", "FSN", "问答"],
        source: { id: 1, title: "问答", work: "FSN", kind: "访谈", meta: {} },
        jump: { kind: "viewer", doc: 1, start: null, end: null, work: "FSN" },
      },
      {
        kind: "pointer", snippet: "Saber出现在这段访谈中。", doc: 2, block: 8,
        matched_terms: ["Saber"], path: ["访谈", "FSN", "访谈"],
        source: { id: 2, title: "访谈", work: "FSN", kind: "访谈", meta: {} },
        jump: { kind: "viewer", doc: 2, start: 8, end: 9, work: "FSN" },
      },
    ],
    official_total: 12,
    official_counts: { qa: 7, pointer: 4, supplement: 1 },
    official_has_more: true,
    occurrences: [], related: [], by_work: [], total: 0, docs: 0,
  }, {});
  assert.match(el.innerHTML, /官方回答 \/ 访谈原文/);
  assert.match(el.innerHTML, /Saber<\/mark>是谁？/);
  assert.match(el.innerHTML, /class="card qa"/);
  assert.match(el.innerHTML, /class="qa-content"/);
  assert.match(el.innerHTML, /class="card official-pointer"/);
  assert.match(el.innerHTML, /查看全部 12 条/);
  assert.match(el.innerHTML, /official\.html\?q=Saber/);
  const qaHref = el.innerHTML.match(/viewer\.html\?doc=1[^" ]+/);
  assert.ok(qaHref);
  assert.match(qaHref[0], /block=2/);
  assert.doesNotMatch(qaHref[0], /start=|end=/);
  assert.doesNotMatch(el.innerHTML, /旧区块不应显示/);
});

test("compact QA card exposes a full-answer expansion control", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "直死之魔眼",
    highlight_terms: ["直死之魔眼"],
    match_mode: "exact",
    definitions: [],
    official_items: [{
      kind: "qa",
      q: "就算失明也能看见吗？",
      a: "奈：能感受到死。\n武：不只是眼睛。\n奈：后续无关内容。",
      a_excerpt: "奈：能感受到死。\n武：不只是眼睛。",
      a_truncated: true,
      doc: 745, block: 91, matched_terms: ["直死之魔眼"],
      source: { id: 745, title: "剧场版问答", work: "空之境界", kind: "问答", meta: {} },
      path: ["访谈", "空之境界", "剧场版问答"],
      jump: { kind: "viewer", doc: 745, start: 91, end: 92, work: "空之境界" },
    }],
    official_total: 1,
    official_counts: { qa: 1, pointer: 0, supplement: 0 },
    occurrences: [], related: [], by_work: [], total: 0, docs: 0,
  }, {});
  assert.match(el.innerHTML, /class="qa-content clamped"/);
  assert.match(el.innerHTML, /data-short="official-qa-short-0"/);
  assert.match(el.innerHTML, /data-full="official-qa-full-0"/);
  assert.match(el.innerHTML, /展开全文/);
  assert.match(el.innerHTML, /后续无关内容/);
});

test("source jump links use the theme accent instead of browser blue", () => {
  assert.match(css, /\.source a\s*\{[^}]*color:\s*var\(--accent\)/s);
});

test("QA expansion swaps the compact excerpt for the full answer", () => {
  function classList(...initial) {
    const values = new Set(initial);
    return {
      contains: (name) => values.has(name),
      toggle(name, force) {
        const on = force === undefined ? !values.has(name) : !!force;
        if (on) values.add(name); else values.delete(name);
        return on;
      },
    };
  }
  const content = { classList: classList("clamped") };
  const full = { classList: classList("hidden"), closest: (selector) => selector === ".qa-content" ? content : null };
  const short = { classList: classList() };
  const more = {
    dataset: { short: "short", full: "full" }, textContent: "展开全文 ▾", onclick: null,
  };
  const el = {
    querySelectorAll: (selector) => selector === ".more" ? [more] : [],
    querySelector: (selector) => selector === "#short" ? short : selector === "#full" ? full : null,
  };
  window.TMRender.wireCards(el);
  more.onclick();
  assert.equal(full.classList.contains("hidden"), false);
  assert.equal(short.classList.contains("hidden"), true);
  assert.equal(content.classList.contains("clamped"), false);
  assert.equal(more.textContent, "收起 ▴");
});

test("multi-term relaxation notice uses the existing result page", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "ciel，白姬",
    highlight_terms: ["ciel", "希耶尔", "白姬", "爱尔奎特·布伦史塔德"],
    match_mode: "multi_term",
    search_mode: "multi_term",
    multi_term: {
      requested_terms: ["ciel", "白姬"],
      effective_level: 1,
      relaxed: true,
      notice: "未找到同时包含全部 2 个词条的语料，已放宽为任意 1 个词条组共同出现。",
    },
    definitions: [],
    interviews: [],
    qa: [],
    occurrences: [],
    related: [],
    by_work: [],
    total: 0,
    docs: 0,
  }, {});
  assert.match(el.innerHTML, /multi-term-notice/);
  assert.match(el.innerHTML, /已放宽为任意 1 个词条组/);
});

test("multi-term section cards render matched labels and highlights", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "Saber，士郎",
    highlight_terms: ["Saber", "士郎"],
    match_mode: "multi_term",
    search_mode: "multi_term",
    multi_term: {
      requested_terms: ["Saber", "士郎"],
      effective_level: 2,
      relaxed: false,
      notice: "",
    },
    definitions: [{
      term: "卫宫士郎", body: "Saber 与士郎共同出现。", cat: "人物",
      matched_terms: ["Saber", "士郎"], source: {
        title: "测试资料", work: "FSN", kind: "设定集", meta: {},
      },
    }],
    interviews: [],
    qa: [{ q: "Saber 是谁？", a: "士郎的从者。", matched_terms: ["Saber", "士郎"], source: {
      title: "测试问答", work: "FSN", kind: "问答", meta: {},
    }}],
    occurrences: [{
      snippet: "Saber 与士郎。", block: 1, doc: 2, work: "FSN", path: ["FSN"],
      matched_terms: ["Saber", "士郎"], source: {
        title: "测试原文", work: "FSN", kind: "原作", meta: {},
      },
    }],
    related: [],
    by_work: [["FSN", 1]],
    total: 1,
    docs: 1,
  }, {});
  assert.match(el.innerHTML, /multi-badges/);
  assert.match(el.innerHTML, /<mark>Saber<\/mark>/);
  assert.match(el.innerHTML, /1 个片段/);
});

test("multi-term renders repeated snippets under one work group", () => {
  const el = fakeElement();
  window.TMRender.render(el, {
    q: "月,姬", highlight_terms: ["月", "姬"], match_mode: "multi_term", search_mode: "multi_term",
    multi_term: { requested_terms: ["月", "姬"], effective_level: 2, relaxed: false, notice: "" },
    definitions: [], interviews: [], qa: [], related: [], by_work: [["月姬", 2]], total: 2, docs: 1,
    occurrences: [
      { snippet: "月姬一", block: 1, doc: 1, work: "月姬", path: ["月姬"], matched_terms: ["月", "姬"], source: { title: "A", work: "月姬", kind: "原作", meta: {} } },
      { snippet: "月姬二", block: 2, doc: 1, work: "月姬", path: ["月姬"], matched_terms: ["月", "姬"], source: { title: "A", work: "月姬", kind: "原作", meta: {} } },
    ],
  }, {});
  assert.equal((el.innerHTML.match(/class="occ"/g) || []).length, 2);
  assert.equal((el.innerHTML.match(/class="group-head"/g) || []).length, 1);
});

test("occurrence href follows explicit official jump", () => {
  const href = window.TMRender.occurrenceHref({
    doc: 900, block: 2, jump: { kind: "official", work: "FGO", id: 100, section: 1 },
  }, "玛修", ["玛修"]);
  assert.match(href, /official_reader\.html\?work=FGO&id=100&sec=1/);
  assert.match(href, /q=%E7%8E%9B%E4%BF%AE/);
});


