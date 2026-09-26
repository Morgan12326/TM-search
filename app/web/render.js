/* 结果渲染：搜索页与词条详情页共用，保证两边看到的内容完全一致。 */
window.TMRender = (function () {
  const CAT_ORDER = { 人名: 0, 人物: 0, 从者: 1, 英灵: 2, 宝具: 3, 技能: 4, 技名: 4,
                      固有技能: 5, 魔术: 6, 用语: 7, 概念: 7, 组织: 8, 组织名: 8,
                      地名: 9, 地形: 9, 事项: 10 };

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // ---- 黑称／同义词表（角色黑称、旧译名；数据来自 /api/aliases）-----
  let ALIAS_MAP = null, ALIAS_NOTES = null, ALIAS_CI = null;
  async function loadAliases() {
    if (ALIAS_MAP) return ALIAS_MAP;
    try {
      const r = await fetch("/api/alias-data");
      if (!r.ok) throw new Error("no alias data");
      const d = (await r.json()) || {};
      ALIAS_MAP = d.targets || {};
      ALIAS_NOTES = d.notes || {};
    } catch (e) {
      try { ALIAS_MAP = (await (await fetch("/api/aliases")).json()) || {}; }
      catch (e2) { ALIAS_MAP = {}; }
      ALIAS_NOTES = {};
    }
    ALIAS_CI = {};
    Object.keys(ALIAS_MAP).forEach((k) => {
      const low = k.toLowerCase();
      if (!(low in ALIAS_CI)) ALIAS_CI[low] = [k, ALIAS_MAP[k]];
    });
    return ALIAS_MAP;
  }

  function targetList(v) {
    return (Array.isArray(v) ? v : [v]).filter(Boolean);
  }

  async function aliasExact(q) {
    const map = await loadAliases();
    if (!q || !map) return null;
    const note = ALIAS_NOTES && (ALIAS_NOTES[q] ||
      ALIAS_NOTES[Object.keys(ALIAS_NOTES).find((k) => k.toLowerCase() === q.toLowerCase()) || ""]);
    if (note) return { nick: q, terms: [], note };
    let nick = null, raw = null;
    if (q in map) { nick = q; raw = map[q]; }
    else {
      const hit = ALIAS_CI ? ALIAS_CI[q.toLowerCase()] : null;
      if (hit) { nick = hit[0]; raw = hit[1]; }
    }
    if (!nick) return null;
    const terms = targetList(raw);
    return { nick, terms, term: terms[0] || "" };
  }

  async function aliasPrefix(q, limit = 4) {
    const map = await loadAliases();
    const low = (q || "").toLowerCase();
    const out = [];
    if (!low || !map) return out;
    Object.keys(map).forEach((k) => {
      if (out.length < limit && k.toLowerCase().startsWith(low))
        out.push({ nick: k, terms: targetList(map[k]) });
    });
    return out;
  }

  function sourceLinks(sources) {
    return (sources || []).slice(0, 3).filter((s) => s && s.url).map((s) =>
      `<a href="${encodeURI(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.site || s.title || "来源")}</a>`
    ).join("　");
  }

  function aliasBanner(hit, extra) {
    if (!hit) return "";
    if (hit.note) {
      const text = typeof hit.note === "string" ? hit.note : (hit.note.text || "");
      const src = sourceLinks(typeof hit.note === "object" ? hit.note.sources : []);
      return `<div class="alias-tip">黑话「${escapeHtml(hit.nick)}」：${escapeHtml(text)}` +
        (src ? `<div class="alias-more">来源：${src}</div>` : "") + `</div>`;
    }
    const terms = targetList(hit.terms || hit.term);
    const links = terms.map((t) =>
      `<a href="entry.html?term=${encodeURIComponent(t)}"><b>${escapeHtml(t)}</b></a>`
    ).join("　");
    const more = (extra || []).filter((x) => !terms.includes((x.terms || [])[0]))
      .slice(0, 4).map((x) => `<a class="chip" href="entry.html?term=${encodeURIComponent((x.terms || [])[0])}">` +
        `${escapeHtml(x.nick)} → ${escapeHtml((x.terms || []).join(" / "))}</a>`).join(" ");
    if (terms.length > 1)
      return `<div class="alias-tip">黑话「${escapeHtml(hit.nick)}」可能指：${links}` +
        (more ? `<span class="alias-more">相关：${more}</span>` : "") + `</div>`;
    return `<div class="alias-tip">黑称「${escapeHtml(hit.nick)}」→ 正式词条 ${links}` +
      (more ? `<span class="alias-more">相关：${more}</span>` : "") + `</div>`;
  }

  function highlight(text, q) {
    const safe = escapeHtml(text);
    if (!q) return safe;
    const esc = escRe(q);
    return safe.replace(new RegExp(esc, "gi"), (m) => `<mark>${m}</mark>`);
  }

  // 正文高亮：与检索规则一致——英文用整词（不会把 transport 里的 ort 标黄），中文用子串
  const CJK_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]/;
  const PUNCT_RE = /[·・‧．.\s]/;
  function termHighlightPattern(term) {
    let out = "";
    for (const ch of term) out += PUNCT_RE.test(ch) ? "[·・‧．.\\s]*" : escRe(ch);
    if (/[A-Za-z]/.test(term) && !CJK_RE.test(term))
      out = "(?<![A-Za-z0-9])" + out + "(?![A-Za-z0-9])";
    return out;
  }
  function highlightText(text, terms) {
    const safe = escapeHtml(text);
    const list = (Array.isArray(terms) ? terms : [terms])
      .map((x) => String(x || "").trim()).filter(Boolean)
      .sort((a, b) => b.length - a.length);
    if (!list.length) return safe;
    const re = new RegExp(list.map(termHighlightPattern).join("|"), "gi");
    return safe.replace(re, (m) => `<mark>${m}</mark>`);
  }

  function escRe(q) {
    return q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function multiBadges(item) {
    const values = item && Array.isArray(item.matched_terms) ? item.matched_terms : [];
    if (!values.length) return "";
    return `<div class="multi-badges">` + values.map((value) =>
      `<span>${escapeHtml(value)}</span>`).join("") + `</div>`;
  }

  function sourceLine(src) {
    const parts = [`<b>《${escapeHtml(src.title)}》</b>`,
                   escapeHtml(src.work) + " · " + escapeHtml(src.kind)];
    const meta = src.meta || {};
    const who = meta["译者"] || meta["翻译"] || meta["录入"];
    if (who) parts.push("译者／录入：" + escapeHtml(who));
    const lic = meta["许可"];
    const extra = lic ? `<div class="path">${escapeHtml(lic)}</div>` : "";
    return `${parts.join("　·　")}${extra}`;
  }

  function occurrenceHref(o, q, terms) {
    const jump = o && o.jump ? o.jump : {};
    const termsQS = encodeURIComponent(JSON.stringify(terms || []));
    const qQS = encodeURIComponent(q || "");
    if (jump.kind === "official") {
      return `official_reader.html?work=${encodeURIComponent(jump.work || "")}` +
        `&id=${encodeURIComponent(jump.id || "")}` +
        `&sec=${encodeURIComponent(jump.section == null ? "" : jump.section)}` +
        `&q=${qQS}&terms=${termsQS}`;
    }
    const doc = jump.doc == null ? o.doc : jump.doc;
    let url = `viewer.html?doc=${encodeURIComponent(doc)}&block=${encodeURIComponent(o.block)}` +
      `&q=${qQS}&terms=${termsQS}`;
    if (jump.start != null) url += `&start=${encodeURIComponent(jump.start)}`;
    if (jump.end != null) url += `&end=${encodeURIComponent(jump.end)}`;
    if (jump.chapter) url += `&chapter=${encodeURIComponent(jump.chapter)}`;
    if (jump.work) url += `&work=${encodeURIComponent(jump.work)}`;
    return url;
  }

  function variantLabel(v) {
    const k = v.translation_kind || "direct";
    const a = v.source_authority || "official_source";
    if (k === "original") return "原文";
    if (a === "official_source" && k === "direct") return "官方资料译文";
    if (k === "machine") return "机器译文";
    if (k === "relay") return "转译";
    return "社区资料";
  }

  function definitionHtml(text, q) {
    const src = text || "";
    if (!src) return "";
    return src.split(/\n\s*\n/).map((part) => {
      const lines = part.split("\n");
      const head = (lines[0] || "").trim();
      const section = /^(?:第一人称|第二人称|第三人称|人称[：:]|性格|动机·对Master的态度|对Master的态度|台词例|史上的实像·人物像|人物像|游戏内的角色|因缘人物|因缘角色|通常武器|其他版本|注释)/.test(head);
      const body = lines.map((line) => highlightText(line, q)).join("<br>");
      return `<p${section ? ' class="def-section"' : ""}>${body}</p>`;
    }).join("");
  }

  // ---- 单张词解卡（搜索页与「查看全部」页共用）----
  function defCard(d, i, q, terms) {
    const hl = (terms && terms.length) ? terms : [q].filter(Boolean);
    const long = d.body.length > 420;
    const variants = Array.isArray(d.variants) ? d.variants : [];
    const hasVariants = variants.length > 1;
    const sameConcept = Array.isArray(d.same_concept) ? d.same_concept : [];
    const hasSameConcept = sameConcept.length > 0;
    const pending = d.entry_type === "pending_definition" || !d.body;
    const conflict = Array.isArray(d.conflict_flags) && d.conflict_flags.length > 0;
    const varRows = hasVariants ? variants.slice(1).map((v, n) => {
      const vlong = (v.body || "").length > 420;
      return `<div class="variant">
        <div class="variant-head">${variantLabel(v)} ${n + 2}</div>
        <div class="definition ${vlong ? "clamped" : ""}" id="variant-def-${i}-${n}">${definitionHtml(v.body || "", hl)}</div>
        ${vlong ? `<span class="more" data-target="variant-def-${i}-${n}">展开全文 ▾</span>` : ""}
        ${v.jp_body ? `<div class="jp" id="variant-jp-${i}-${n}">${highlightText(v.jp_body, hl)}</div>
          <span class="mini" data-toggle="variant-jp-${i}-${n}" data-show-label="显示日文原文" data-hide-label="隐藏日文原文">显示日文原文</span>` : ""}
        <div class="source">出处：${sourceLine(v.source)}</div>
      </div>`;
    }).join("") : "";
    const sameRows = sameConcept.map((v, n) => {
      const vlong = (v.body || "").length > 420;
      const sVariants = Array.isArray(v.variants) ? v.variants : [];
      const sRows = sVariants.slice(1).map((sv, sn) => {
        const svlong = (sv.body || "").length > 420;
        const sid = `same-variant-def-${i}-${n}-${sn}`;
        return `<div class="variant">
          <div class="variant-head">${variantLabel(sv)} ${sn + 2}</div>
          <div class="definition ${svlong ? "clamped" : ""}" id="${sid}">${definitionHtml(sv.body || "", hl)}</div>
          ${svlong ? `<span class="more" data-target="${sid}">展开全文 ▾</span>` : ""}
          ${sv.jp_body ? `<div class="jp" id="same-variant-jp-${i}-${n}-${sn}">${highlightText(sv.jp_body, hl)}</div>
            <span class="mini" data-toggle="same-variant-jp-${i}-${n}-${sn}" data-show-label="显示日文原文" data-hide-label="隐藏日文原文">显示日文原文</span>` : ""}
          <div class="source">出处：${sourceLine(sv.source)}</div>
        </div>`;
      }).join("");
      const sid = `same-def-${i}-${n}`;
      return `<div class="variant same-concept">
        <div class="variant-head">同类词解 ${n + 1}</div>
        <div class="definition ${vlong ? "clamped" : ""}" id="${sid}">${definitionHtml(v.body || "", hl)}</div>
        ${vlong ? `<span class="more" data-target="${sid}">展开全文 ▾</span>` : ""}
        ${v.jp_body ? `<div class="jp" id="same-jp-${i}-${n}">${highlightText(v.jp_body, hl)}</div>
          <span class="mini" data-toggle="same-jp-${i}-${n}" data-show-label="显示日文原文" data-hide-label="隐藏日文原文">显示日文原文</span>` : ""}
        <div class="source">出处：${sourceLine(v.source)}</div>
        ${sRows ? `<span class="mini" data-toggle="same-variants-${i}-${n}" data-show-label="查看其他译本（${sVariants.length - 1}）" data-hide-label="收起其他译本">查看其他译本（${sVariants.length - 1}）</span>
          <div class="variant-list" id="same-variants-${i}-${n}" style="display:none">${sRows}</div>` : ""}
      </div>`;
    }).join("");
    const titleHtml = d.exact
      ? `<mark>${escapeHtml(d.term)}</mark>`
      : highlightText(d.term, hl);
    return `<div class="card">
      ${multiBadges(d)}
      <div class="term">${titleHtml}${d.cat ? `<span class="cat">${escapeHtml(d.cat)}</span>` : ""}</div>
      ${pending ? `<div class="pending-definition">词解待补</div>` :
        `<div class="definition ${long ? "clamped" : ""}" id="def-${i}">${definitionHtml(d.body, hl)}</div>
      ${long ? `<span class="more" data-target="def-${i}">展开全文 ▾</span>` : ""}`}
      ${!pending && d.jp_body ? `<div class="jp" id="jp-${i}">${highlightText(d.jp_body, hl)}</div>
        <span class="mini" data-toggle="jp-${i}" data-show-label="显示日文原文" data-hide-label="隐藏日文原文">显示日文原文</span>` : ""}
      ${!pending ? `<div class="source">出处：${sourceLine(d.source)}</div>` : ""}
      ${conflict ? `<div class="variant-warning">存在译文含义差异，请对照原文与其他译本。</div>` : ""}
      ${hasVariants ? `<span class="mini" data-toggle="variants-${i}" data-show-label="查看其他译本（${variants.length - 1}）" data-hide-label="收起其他译本">查看其他译本（${variants.length - 1}）</span>
        <div class="variant-list" id="variants-${i}" style="display:none">${varRows}</div>` : ""}
      ${hasSameConcept ? `<span class="mini" data-toggle="same-concepts-${i}" data-show-label="查看同类词解（${sameConcept.length}）" data-hide-label="收起同类词解">查看同类词解（${sameConcept.length}）</span>
        <div class="variant-list same-concept-list" id="same-concepts-${i}" style="display:none">${sameRows}</div>` : ""}
    </div>`;
  }

  // 「展开全文 / 显示日文原文」的点击绑定（两处共用）
  function wireCards(el) {
    el.querySelectorAll(".more").forEach((n) => {
      n.onclick = () => {
        if (n.dataset.full && n.dataset.short) {
          const full = el.querySelector("#" + n.dataset.full);
          const short = el.querySelector("#" + n.dataset.short);
          const content = full.closest(".qa-content");
          const expanded = !full.classList.contains("hidden");
          full.classList.toggle("hidden", expanded);
          short.classList.toggle("hidden", !expanded);
          if (content) content.classList.toggle("clamped", expanded);
          n.textContent = expanded ? "展开全文 ▾" : "收起 ▴";
          return;
        }
        const box = el.querySelector("#" + n.dataset.target);
        box.classList.toggle("clamped");
        n.textContent = box.classList.contains("clamped") ? "展开全文 ▾" : "收起 ▴";
      };
    });
    el.querySelectorAll(".mini").forEach((n) => {
      n.onclick = () => {
        const box = el.querySelector("#" + n.dataset.toggle);
        const shown = box.style.display === "block";
        box.style.display = shown ? "none" : "block";
        n.textContent = shown ? (n.dataset.showLabel || "展开") : (n.dataset.hideLabel || "收起");
      };
    });
  }

  function officialCard(x, i, q, terms) {
    const hl = (terms && terms.length) ? terms : [q].filter(Boolean);
    const jump = occurrenceHref({ ...x, block: x.block }, q, hl);
    if (x.kind === "qa") {
      const fullAnswer = x.a || "";
      const shortAnswer = x.a_excerpt || fullAnswer;
      const expandable = !!x.a_truncated || fullAnswer.length > 320 || (x.q || "").length > 260;
      const shortId = `official-qa-short-${i}`;
      const fullId = `official-qa-full-${i}`;
      return `<div class="card qa">
        ${multiBadges(x)}
        <div class="qa-content${expandable ? " clamped" : ""}">
          <div class="q">Ｑ：${highlightText(x.q || "", hl)}</div>
          <div class="a qa-short" id="${shortId}">${highlightText(shortAnswer, hl)}</div>
          ${expandable ? `<div class="a qa-full hidden" id="${fullId}">${highlightText(fullAnswer, hl)}</div>` : ""}
        </div>
        ${expandable ? `<span class="more" data-short="${shortId}" data-full="${fullId}">展开全文 ▾</span>` : ""}
        <div class="source">出处：${sourceLine(x.source)}　<a href="${jump}" target="_blank" rel="noopener">查看原文 ↗</a></div>
      </div>`;
    }
    const path = Array.isArray(x.path) ? x.path : [];
    const kindLabel = x.kind === "supplement" ? "补充来源" : "访谈原文";
    return `<div class="card official-pointer">
      <a class="occ-head" href="${jump}" target="_blank" rel="noopener" title="打开原文并跳到这一处">
        ${path.length
          ? path.map((part, index) => `<span class="${index === 0 ? "work" : "chapter"}">${escapeHtml(part)}</span>`).join('<span class="sep">›</span>')
          : `<span class="work">${escapeHtml(x.source.work || "")}</span><span class="doc">《${escapeHtml(x.source.title || "")}》</span>`}
        <span class="kind">${kindLabel}</span><span class="jump">查看原文 ↗</span>
      </a>
      ${multiBadges(x)}
      <div class="occ-text">${highlightText(x.snippet || "", hl)}</div>
    </div>`;
  }

  function render(el, data, opts) {
    opts = opts || {};
    const q = data.q;
    const highlightTerms = (data.highlight_terms && data.highlight_terms.length)
      ? data.highlight_terms : [q];
    const html = [];
    const hasDef = data.definitions.length > 0;

    if (data.search_mode === "multi_term" && data.multi_term && data.multi_term.notice) {
      html.push(`<div class="notice multi-term-notice">${escapeHtml(data.multi_term.notice)}</div>`);
    }

    if (data.scoped && opts.showScopeBadge !== false) {
      html.push(`<div class="scope-badge">局部搜索：<b>${escapeHtml(data.scope_name)}</b>
        <span class="x" id="scope-clear">改为全局搜索 ↺</span></div>`);
    }

    if (data.alias) {
      html.push(aliasBanner({ nick: data.alias.from, terms: targetList(data.alias.to) }));
    }
    if (data.alias_note) {
      html.push(aliasBanner({ nick: data.q, note: data.alias_note }));
    }

    if ((data.classifications || []).length && opts.showClassifications) {
      html.push(`<div class="classification-bar">` +
        `<span class="classification-label">百科收录</span>` +
        `<div class="classification-links">` +
        data.classifications.map((c) =>
          `<a class="classification-link" href="encyclopedia.html?key=${encodeURIComponent(c.key)}">${escapeHtml(c.name)}</a>`
        ).join(``) + `</div></div>`);
    }

    const scopeQS = data.scoped ? "&scope=" + encodeURIComponent(data.scope) : "";
    const multiQS = data.search_mode === "multi_term" ? "&multi=1" : "";

    if (hasDef) {
      const defsTotal = data.defs_total || data.definitions.length;
      const all = defsTotal > data.definitions.length
        ? `<a class="more-link" href="defs.html?q=${encodeURIComponent(data.q)}${scopeQS}${multiQS}">查看全部 ${defsTotal} 张 →</a>`
        : "";
      html.push(`<div class="section-title">词条定义${all}</div>`);
      data.definitions.forEach((d, i) => html.push(defCard(d, i, q, highlightTerms)));
    }

    const officialItems = data.official_items || [];
    const officialTotal = Number(data.official_total || officialItems.length || 0);
    if (officialItems.length) {
      const officialMore = officialTotal > officialItems.length
        ? `<a class="more-link" href="official.html?q=${encodeURIComponent(data.q)}${scopeQS}${multiQS}">查看全部 ${officialTotal} 条 →</a>`
        : "";
      html.push(`<div class="section-title">官方回答 / 访谈原文${officialMore}</div>`);
      officialItems.forEach((x, oi) => html.push(officialCard(x, oi, q, highlightTerms)));
    }

    if (!hasDef) {
      const noDef = data.search_mode === "multi_term"
        ? `没有词解卡同时包含本次检索的词条。以下列出共同出现的原文位置。`
        : `检索不到 <b>${escapeHtml(q)}</b> 的成条定义（本地语料中的官方用语辞典/设定集尚未收录该条目）。
        以下列出它在全部语料中的<b>出现位置</b>。`;
      html.push(`<div class="notice">${noDef}${officialItems.length ? "另附官方回答与访谈原文。" : ""}</div>`);
    }

    if (data.scoped && data.total === 0 && !officialItems.length) {
      html.push(`<div class="notice">「<b>${escapeHtml(q)}</b>」在 <b>${escapeHtml(data.scope_name)}</b> 里没有任何命中。
        换个二级分类，或者 <span class="mini" id="scope-clear2">改为全局搜索 ↺</span>。</div>`);
    }

    html.push(`<div class="section-title">出现位置</div>`);
    const works = (data.by_work || []).map(([w, c]) => `${escapeHtml(w)} ${c}`).join(" · ");
    const statsLead = data.search_mode === "multi_term"
      ? `共同命中 <b>${data.total.toLocaleString()}</b> 个片段`
      : `共在语料中出现 <b>${data.total.toLocaleString()}</b> 次`;
    html.push(`<div class="stats">${statsLead}，
      覆盖 <b>${data.docs}</b> 篇文档${works ? "　|　" + works : ""}
      ${data.truncated ? `　|　以下显示前 ${data.occurrences.length} ${data.search_mode === "multi_term" ? "个片段" : "处"}` : ""}</div>`);

    if (!data.occurrences.length) {
      html.push(`<div class="notice">全部语料中没有找到「${escapeHtml(q)}」。</div>`);
    } else {
      const groups = new Map();
      data.occurrences.forEach((o) => {
        if (!groups.has(o.source.work)) groups.set(o.source.work, []);
        groups.get(o.source.work).push(o);
      });
      const workTotal = new Map(data.by_work);
      const scopeQS = data.scoped ? "&scope=" + encodeURIComponent(data.scope) : "";
      const termsQS = encodeURIComponent(JSON.stringify(highlightTerms));
      groups.forEach((items, work) => {
        const total = workTotal.get(work) || items.length;
        const unitLabel = data.search_mode === "multi_term" ? "个片段" : "处";
        html.push(`<div class="group-head">${escapeHtml(work)}
          <span>共 ${total} ${unitLabel} · 下列 ${items.length} ${unitLabel}
            <a class="more-link" href="list.html?q=${encodeURIComponent(q)}&work=${encodeURIComponent(work)}${scopeQS}&terms=${termsQS}${data.search_mode === "multi_term" ? "&multi=1" : ""}">查看全部 →</a>
          </span></div>`);
        html.push(`<div class="card">`);
        items.forEach((o) => {
          const jump = occurrenceHref(o, q, highlightTerms);
          html.push(`<div class="occ">
            <a class="occ-head" href="${jump}" target="_blank" rel="noopener" title="点击查看原文并跳转到这一处">
              ${(o.path && o.path.length)
                ? o.path.map((p, i) => `<span class="${i === 0 ? "work" : "chapter"}">${escapeHtml(p)}</span>`).join('<span class="sep">›</span>')
                : `<span class="work">${escapeHtml(o.source.work)}</span>
                   <span class="doc">《${escapeHtml(o.source.title)}》</span>
                   <span class="kind">${escapeHtml(o.source.kind)}</span>`}
              <span class="jump">查看原文 ↗</span></a>
            ${multiBadges(o)}
            <div class="occ-text">${highlightText(o.snippet, highlightTerms)}</div>
          </div>`);
        });
        html.push(`</div>`);
      });
    }

    if (data.related.length) {
      html.push(`<div class="section-title">相关词（同段落共现）</div>`);
      html.push(`<div class="chips">` + data.related.map(([t]) =>
        `<span class="chip" data-term="${escapeHtml(t)}">${escapeHtml(t)}</span>`).join("") + `</div>`);
    }

    el.innerHTML = html.join("");
    wire(el, opts);
  }

  function wire(el, opts) {
    wireCards(el);
    el.querySelectorAll(".chip").forEach((n) => {
      n.onclick = () => opts.onTerm && opts.onTerm(n.dataset.term);
    });
    ["scope-clear", "scope-clear2"].forEach((id) => {
      const n = el.querySelector("#" + id);
      if (n) n.onclick = () => opts.onClearScope && opts.onClearScope();
    });
  }

  return { render, escapeHtml, highlight, highlightText, sourceLine, defCard, officialCard, wireCards,
           loadAliases, aliasExact, aliasPrefix, aliasBanner, occurrenceHref };
})();
