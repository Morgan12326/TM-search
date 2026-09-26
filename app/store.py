# -*- coding: utf-8 -*-
"""Data loading, indexing, and query behavior for Type-Moon Search."""
from __future__ import annotations

try:
    from .core import *
except ImportError:  # Direct execution compatibility.
    from core import *

class Store:
    def __init__(self):
        t0 = time.time()
        self.corpus = read_text(os.path.join(DATA, "corpus.txt"))
        self.offsets = read_json(os.path.join(DATA, "offsets.json"))
        bundle = read_json(os.path.join(DATA, "entries.json"))
        self.docs = bundle["docs"]
        self.entries = bundle["entries"]
        self.qa = bundle["qa"]
        self.interviews = bundle.get("interviews", [])
        self.vocab = read_json(os.path.join(DATA, "vocab.json"))
        self.related = read_json(os.path.join(DATA, "related.json"))
        self._legacy_corpus_length = len(self.corpus)
        self._legacy_starts = [o[0] for o in self.offsets]
        self._recovered_segment_base = len(self.offsets)
        self._recovered_starts = []
        recovery = load_recovered_blocks(DATA)
        if recovery:
            if recovery["base_corpus_length"] != self._legacy_corpus_length:
                raise RuntimeError("zh_recovered_blocks.json baseline does not match corpus.txt")
            recovered_parts = []
            cursor = self._legacy_corpus_length
            for block in recovery["blocks"]:
                block_text = block["text"]
                self.offsets.append([cursor, len(block_text), block["doc"], block["order"]])
                self._recovered_starts.append(cursor)
                recovered_parts.append(block_text)
                recovered_parts.append("\n")
                cursor += len(block_text) + 1
            self.corpus += "".join(recovered_parts)
        self.recovered_block_count = len(self._recovered_starts)
        self.starts = [o[0] for o in self.offsets]
        self.doc_index = defaultdict(list)
        self.doc_span = {}
        for start, length, doc_id, order in self.offsets:
            self.doc_index[doc_id].append((order, start, length))
            lo, hi = self.doc_span.get(doc_id, (start, start + length))
            self.doc_span[doc_id] = (min(lo, start), max(hi, start + length))
        self.jp_index = defaultdict(dict)
        for doc_id, order, block_text in read_json(os.path.join(DATA, "jp_blocks.json")):
            self.jp_index[doc_id][order] = block_text
        self.story_blocks = defaultdict(dict)
        story_blocks_path = os.path.join(DATA, "story_blocks.json")
        if os.path.exists(story_blocks_path):
            for doc_id, order, block_text in read_json(story_blocks_path):
                self.story_blocks[doc_id][order] = block_text
        self.occurrence_locations = []
        occurrence_path = os.path.join(DATA, "occurrence_locations.json")
        if os.path.exists(occurrence_path):
            self.occurrence_locations = read_json(occurrence_path)
        self._occurrence_by_doc = {}
        for row in self.occurrence_locations:
            self._occurrence_by_doc.setdefault(row["doc"], []).append(row)
        for rows in self._occurrence_by_doc.values():
            rows.sort(key=lambda row: row["start"])
        self.vocab_sorted = sorted(self.vocab, key=lambda v: -v["n"])
        self.vocab_freq = {v["t"]: v["n"] for v in self.vocab}
        self.entries_by_term = {}
        for e in self.entries:
            keys = {term_key(e["term"])}
            if e.get("source_term"):
                keys.add(term_key(e["source_term"]))
            for key in keys:
                if key:
                    self.entries_by_term.setdefault(key, []).append(e)
        self.term_list = list(self.entries_by_term)
        self.terms_ci = {}
        for _t in self.term_list:
            self.terms_ci.setdefault(_t.lower(), []).append(_t)
        self._scan_cache = (None, None)
        self._multi_cache = {}
        self.multi_engine = MultiTermEngine(
            self, CARD_TOTAL_MAX, work_rank, occurrence_term_pattern)
        print(f"语料 {len(self.corpus):,} 字 / 段落 {len(self.offsets):,} / 词条 {len(self.entries):,}"
              f" / 问答 {len(self.qa):,} / 词表 {len(self.vocab):,}   载入耗时 {time.time() - t0:.1f}s")
        self._build_scope()
        self._build_wiki()
        self._build_story()
        self._build_official()

    def _is_story_file(self, file):
        f = file
        return (f.lower().endswith(".epub") or f.startswith("原作文本\\") or f.startswith("DRAMA\\")
                or "\\DRAMA\\" in f)

    def _build_story(self):
        """剧情大全：读 07_story.py 生成的结构（作品 → 路线 → 章节）。"""
        path = os.path.join(DATA, "story.json")
        if not os.path.exists(path):
            self.story_works, self.story_jp_only, self.story_chapter_at = [], 0, {}
            self.story_chapter_by_key = {}
            return
        bundle = read_json(path)
        self.story_works = bundle["works"]
        self.story_jp_only = bundle.get("jp_only", 0)
        self.story_chapter_at = {}
        self.story_chapter_by_key = {}
        self.chapters_by_doc = {}
        self.story_doc_owner = {}
        for w in self.story_works:
            root_route = {"name": w["work"], "chapters": w.get("root_chapters", [])}
            for r in ([root_route] if root_route["chapters"] else []) + w["routes"]:
                for i, c in enumerate(r["chapters"]):
                    self.story_doc_owner[c["doc"]] = w["work"]
                    # A document referenced from two places keeps the later node
                    # as its display owner, while both chapter paths remain valid.
                    self.story_chapter_at.setdefault((c["doc"], c["start"]), (w["work"], r, i))
                    if c.get("key"):
                        self.story_chapter_by_key[c["key"]] = (w["work"], r, i)
                    self.chapters_by_doc.setdefault(c["doc"], []).append(
                        {"start": c["start"] or 0, "end": c.get("end"), "work": w["work"],
                         "route": r["name"], "group": c.get("group", ""),
                         "prereq": bool(c.get("prereq", False)), "title": c["title"]})
        for doc_id, rows in self.chapters_by_doc.items():
            rows.sort(key=lambda x: x["start"])
        self._build_chapter_shingles()
        self.story_work_map = {w["work"]: w for w in self.story_works}
        print(f"剧情大全：{len(self.story_works)} 部作品 / "
              f"{sum(len(w['routes']) for w in self.story_works)} 条路线 / "
              f"{sum(len(r['chapters']) for w in self.story_works for r in w['routes']) + sum(len(w.get('root_chapters', [])) for w in self.story_works)} 个章节"
              f"（仅日文 {self.story_jp_only} 篇未收录）")
        self._build_fgo()
        self.build_nav()
        return

    def _build_fgo(self):
        """官方剧情数据：FGO（Atlas Academy）与月姬R（汉化文本）。"""
        self.official = {}
        self.official_story_index = {}
        for fname, work in (("fgo_story.json", "FGO"), ("tsukihime_r.json", "月姬R")):
            path = os.path.join(DATA, fname)
            if not os.path.exists(path):
                continue
            parts, order = [], []
            for p in read_json(path):
                chapters = []
                for ch in p["chapters"]:
                    secs = ch["chapters"]
                    chapters.append({"id": ch["war_id"], "title": ch["title"],
                                     "group": ch.get("group", ""),
                                     "intro": ch.get("intro"),
                                     "sections": [s["title"] for s in secs],
                                     "lines": sum(len(s["lines"]) for s in secs),
                                     "body": secs})
                if chapters:
                    parts.append({"name": p["part"], "chapters": chapters})
                    order += [(p["part"], c["id"]) for c in chapters]
            self.official[work] = parts
            for i, (part, cid) in enumerate(order):
                self.official_story_index[(work, cid)] = (part, i, order)
            print(f"官方剧情[{work}]：{len(parts)} 部 / {len(order)} 章 / "
                  f"{sum(c['lines'] for p in parts for c in p['chapters']):,} 条")
        self.fgo_parts = self.official.get("FGO", [])

    SOURCE_LABEL = {"FGO": "Atlas Academy · 官方中文（ODC-BY 1.0）",
                    "月姬R": "月姬重制版汉化组 · 中文文本"}

    def official_title(self, work, cid):
        for p in self.official.get(work, []):
            for c in p["chapters"]:
                if c["id"] == cid:
                    return c["title"]
        return ""

    def official_chapter(self, work, cid):
        info = self.official_story_index.get((work, cid))
        if not info:
            return None
        part, i, order = info
        for p in self.official[work]:
            for c in p["chapters"]:
                if c["id"] == cid:
                    prev = order[i - 1] if i > 0 else None
                    nxt = order[i + 1] if i + 1 < len(order) else None
                    return {
                        "work": work, "id": c["id"], "part": p["name"], "title": c["title"],
                        "source": self.SOURCE_LABEL.get(work, work),
                        "intro": c.get("intro"),
                        "lines": c["lines"],
                        "chapters": [{"title": s["title"], "lines": s["lines"]}
                                     for s in c["body"]],
                        "nav": {"index": i + 1, "total": len(order),
                                "prev": {"id": prev[1], "title": self.official_title(work, prev[1])}
                                        if prev else None,
                                "next": {"id": nxt[1], "title": self.official_title(work, nxt[1])}
                                        if nxt else None},
                    }
        return None

    def fgo_chapter(self, war_id):
        # war 400 was merged into the Ordeal Call chapter (war 401).
        try:
            war_id = int(war_id)
        except (TypeError, ValueError):
            return None
        if war_id == 400:
            war_id = 401
        return self.official_chapter("FGO", war_id)

    def _build_story_old(self):
        """（旧逻辑，保留备用）"""
        self.story_docs = {}
        self.story_leaves = {}
        self.story_jp_only = []
        for d in self.docs:
            if d["kind"] not in ("原作", "广播剧") or not self._is_story_file(d["file"]):
                continue
            blocks = self.doc_index.get(d["id"], [])
            if not blocks:
                self.story_jp_only.append(d["id"])
                continue
            leaf = self.leaf_of(d["id"])
            self.story_docs[d["id"]] = {"chars": sum(b[2] for b in blocks),
                                        "blocks": len(blocks), "leaf": leaf}
            self.story_leaves.setdefault(leaf, []).append(d["id"])
        for ids in self.story_leaves.values():
            ids.sort(key=lambda i: self.docs[i]["file"])
        self.story_tree = []
        for t in self.taxonomy:
            children = []
            for o in t["options"]:
                kids = []
                for s in o.get("subs") or []:
                    n = len(self.story_leaves.get(s["key"], []))
                    if n:
                        kids.append({"key": s["key"], "name": s["label"], "chapters": n})
                own = len(self.story_leaves.get(o["key"], []))
                total = own + sum(k["chapters"] for k in kids)
                if total:
                    children.append({"key": o["key"], "name": o["label"], "chapters": total,
                                     "own": own, "children": kids})
            if children:
                self.story_tree.append({"key": t["key"], "name": t["name"],
                                        "chapters": sum(c["chapters"] for c in children),
                                        "children": children})
        print(f"剧情大全：{len(self.story_docs):,} 篇可读章节 / {len(self.story_leaves):,} 个分类，"
              f"另有 {len(self.story_jp_only)} 篇仅日文原文")

    BAD_HEAD = re.compile(r"^[0-9０-９]+[：:.．]|^未知$|^[#*\-—・◇◆\s]+$|^[（(]|^https?:|"
                          r"^译者|^录入|^翻译|^插画|^修图|^校对|^扫图")
    HEAD_HINT = re.compile(r"^(序|序幕|开幕|终章|尾声|幕间|间章|后记|あとがき|prologue|epilogue|"
                           r"chapter|act|track|disc|intro|outro|final|"
                           r"第[0-9一二三四五六七八九十百千]+(章|节|幕|话|回|夜|部))", re.I)

    def _is_heading(self, s):
        if not (1 < len(s) <= 24) or self.BAD_HEAD.search(s):
            return False
        if re.search(r"[。，、！？…；：:！?]", s) or any(c in s for c in "【「『"):
            return False
        if any(c in s for c in "[]{}<>|\\^~$#@*_=+%&"):
            return False
        if not re.search(r"[\u4e00-\u9fff]", s) and not self.HEAD_HINT.match(s):
            return False
        if self.HEAD_HINT.match(s) or re.search(r"（\d+/\d+）$", s):
            return True
        return len(s) <= 14

    def toc_of(self, doc_id, limit=300):
        out = []
        for order, start, length in self.doc_index.get(doc_id, []):
            for ln in self.corpus[start:start + length].split("\n"):
                s = ln.strip("　 ")
                if self._is_heading(s):
                    out.append({"title": s, "block": order})
                    if len(out) >= limit:
                        return out
        return out

    def _build_wiki(self):
        """百科索引：词条 → 分类（分类跟着词条来源文档走，保证不串类）。"""
        leaf_terms = {}          # leaf_key -> {term: 最佳词条}
        leaf_priorities = {}     # leaf_key -> {term: 来源优先级}
        term_leaves = {}         # term -> {leaf_key}
        term_entries = {}        # term -> [entry]
        leaf_kind = {}
        wiki_allow = {"work:魔法使之夜": {"第二魔法", "自动人偶"}}
        for e in self.entries:
            doc = self.docs[e["doc"]]
            work, sub = self.doc_scope[e["doc"]]
            source_leaf = "sub:" + work + "|" + sub if sub else "work:" + work
            leaf = WIKI_LEAF_ALIASES.get(source_leaf, source_leaf)
            allowed = wiki_allow.get(source_leaf)
            if allowed is not None and e["term"] not in allowed:
                continue
            bucket = leaf_terms.setdefault(leaf, {})
            priorities = leaf_priorities.setdefault(leaf, {})
            old = bucket.get(e["term"])
            old_rank = (priorities.get(e["term"], 10 ** 9),
                        KIND_ORDER.get(self.docs[old["doc"]]["kind"], 4) if old else 10 ** 9)
            new_rank = (WIKI_LEAF_PRIORITY.get(source_leaf, 1),
                        KIND_ORDER.get(doc["kind"], 4))
            if old is None or new_rank < old_rank:
                bucket[e["term"]] = e
                priorities[e["term"]] = new_rank[0]
            term_leaves.setdefault(e["term"], set()).add(leaf)
            term_entries.setdefault(e["term"], []).append(e)
            leaf_kind[leaf] = WIKI_LEAF_KIND_OVERRIDES.get(leaf, (work, sub))
        self.wiki_leaf_terms = {}
        for leaf, bucket in leaf_terms.items():
            self.wiki_leaf_terms[leaf] = sorted(
                bucket.items(),
                key=lambda kv: (cat_rank(kv[1].get("cat", "")), self._term_order(kv[0])))
        self.wiki_term_leaves = term_leaves
        self.wiki_term_entries = term_entries
        self.wiki_leaf_kind = leaf_kind
        self.wiki_tree = []
        for t in self.taxonomy:
            children = []
            for o in t["options"]:
                kids = []
                for s in o.get("subs") or []:
                    terms = self.wiki_leaf_terms.get(s["key"], [])
                    if terms:
                        kids.append({"key": s["key"], "name": s["label"], "terms": len(terms),
                                     "own": len(terms), "children": []})
                own = len(self.wiki_leaf_terms.get(o["key"], []))
                total = own + sum(k["terms"] for k in kids)
                if total == 0:
                    continue
                children.append({"key": o["key"], "name": o["label"],
                                 "terms": total, "own": own, "children": kids})
            if children:
                self.wiki_tree.append({"key": t["key"], "name": t["name"],
                                       "terms": sum(c["terms"] for c in children),
                                       "children": children})
        print(f"百科：{sum(len(v) for v in self.wiki_leaf_terms.values()):,} 条词条归属 / "
              f"{len(self.wiki_leaf_terms):,} 个最小分类 / {len(self.wiki_term_leaves):,} 个词条")

    def _term_order(self, term):
        score = self.vocab_freq.get(term, 0)
        return (-score, len(term), term)

    def leaf_of(self, doc_id):
        work, sub = self.doc_scope[doc_id]
        return "sub:" + work + "|" + sub if sub else "work:" + work

    def leaf_name(self, key):
        key = WIKI_LEAF_ALIASES.get(key, key)
        if key in WIKI_LEAF_LABELS:
            return WIKI_LEAF_LABELS[key]
        if key in self.wiki_leaf_kind:
            work, sub = self.wiki_leaf_kind[key]
            label = WORK_LABEL.get(work, work)
            return label + " · " + sub if sub else label
        if key.startswith("work:"):
            return WORK_LABEL.get(key[5:], key[5:])
        return key

    def _leaf_pairs(self, key):
        """分类词条：最小分类直接取；作品层（自身无词条、只有子分类）按子分类聚合并去重。"""
        key = WIKI_LEAF_ALIASES.get(key, key)
        pairs = self.wiki_leaf_terms.get(key)
        if pairs is not None:
            return pairs
        if key.startswith("work:"):
            prefix = "sub:" + key[5:] + "|"
            merged = {}
            for leaf, bucket in self.wiki_leaf_terms.items():
                if not leaf.startswith(prefix):
                    continue
                for term, e in bucket:
                    old = merged.get(term)
                    if old is None or KIND_ORDER.get(self.docs[e["doc"]]["kind"], 4) < \
                            KIND_ORDER.get(self.docs[old["doc"]]["kind"], 4):
                        merged[term] = e
            return sorted(merged.items(),
                          key=lambda kv: (cat_rank(kv[1].get("cat", "")), self._term_order(kv[0])))
        return []

    def wiki_leaf(self, key, offset=0, limit=100, filt="", cat=""):
        pairs = self._leaf_pairs(key)
        if filt:
            fl = filt.lower()
            pairs = [kv for kv in pairs if fl in kv[0].lower()]
        # chips 数量随「词条名筛选」变化，但不受「脚注筛选」影响（这样才能随时切换脚注）
        cats = {}
        for _term, _e in pairs:
            _c = _e.get("cat") or "未分类"
            cats[_c] = cats.get(_c, 0) + 1
        if cat:
            pairs = [kv for kv in pairs if (kv[1].get("cat") or "未分类") == cat]
        page = pairs[offset:offset + limit]
        items = []
        for term, e in page:
            es = self.wiki_term_entries.get(term, [])
            body = self._definition_display_body(term, e["doc"], e["body"])
            items.append({
                "term": term, "cat": e.get("cat", ""),
                "def": body, "long": len(body) > 90, "defs": len(es),
                "source": self.source(e["doc"]),
                "leaves": [self.leaf_name(k) for k in sorted(self.wiki_term_leaves.get(term, []))],
            })
        return {"key": key, "name": self.leaf_name(key), "total": len(pairs),
                "offset": offset, "items": items, "has_more": offset + limit < len(pairs),
                "cat": cat,
                "categories": sorted(cats.items(), key=lambda kv: (cat_rank(kv[0]), -kv[1]))}

    def term_classifications(self, term):
        leaves = sorted(self.wiki_term_leaves.get(term, []))
        return [{"key": k, "name": self.leaf_name(k)} for k in leaves]

    def _sub_of(self, doc):
        rules = SUBRULES.get(doc["work"])
        if not rules:
            return None
        path = doc["file"]
        for key, label in rules:
            if key in path:
                return label
        return DEFAULT_SUB.get(doc["work"], "其他")

    def _build_scope(self):
        """预先算出每个分类包含哪些文档，检索时直接按集合过滤。"""
        self.doc_scope = {}          # doc_id -> (work, sub)
        for d in self.docs:
            self.doc_scope[d["id"]] = (d["work"], self._sub_of(d))
        self.scope_docs = {}
        for d in self.docs:
            self.scope_docs.setdefault("work:" + d["work"], set()).add(d["id"])
            sub = self.doc_scope[d["id"]][1]
            if sub:
                self.scope_docs.setdefault("sub:" + d["work"] + "|" + sub, set()).add(d["id"])
        for tid, _tname, works in TAXONOMY:
            ids = set()
            for w in works:
                ids |= self.scope_docs.get("work:" + w, set())
            self.scope_docs["top:" + tid] = ids
        self.taxonomy = []
        for tid, tname, works in TAXONOMY:
            options = []
            for w in works:
                ids = self.scope_docs.get("work:" + w, set())
                if not ids:
                    continue
                label = WORK_LABEL.get(w, w)
                subs = [(k.split("|", 1)[1], len(v))
                        for k, v in sorted(self.scope_docs.items())
                        if k.startswith("sub:" + w + "|")]
                options.append({"key": "work:" + w, "label": label, "docs": len(ids),
                                "subs": [{"key": "sub:" + w + "|" + s, "label": s, "docs": n}
                                         for s, n in subs]})
            self.taxonomy.append({"id": tid, "key": "top:" + tid, "name": tname,
                                  "docs": len(self.scope_docs.get("top:" + tid, set())),
                                  "options": options})

    def scope_name(self, scope):
        """把 scope 键转成给人看的名字。"""
        if not scope or scope == "all":
            return "全部作品"
        if scope.startswith("top:"):
            for t in self.taxonomy:
                if t["key"] == scope:
                    return t["name"] + "（全部）"
        if scope.startswith("work:"):
            return WORK_LABEL.get(scope[5:], scope[5:])
        if scope.startswith("sub:"):
            w, sub = scope[4:].split("|", 1)
            return WORK_LABEL.get(w, w) + " · " + sub
        return "全部作品"

    def story_tree(self):
        out = []
        for tid, tname, works in STORY_TAXONOMY:
            children = []
            for w in works:
                sw = self.story_work_map.get(w)
                official = self.official.get(w)
                if not sw and not official:
                    continue
                key = "work:" + w
                if self.nav.get(key):
                    chapters = self.count_chapters(key)
                else:
                    chapters = sum(len(r["chapters"]) for r in sw["routes"]) + len(sw.get("root_chapters", []))
                children.append({"key": "work:" + w, "name": WORK_LABEL.get(w, w),
                                 "chapters": chapters,
                                 "routes": len(official) if official else len(sw["routes"])})
            if children:
                out.append({"key": "top:" + tid, "name": tname,
                            "chapters": sum(c["chapters"] for c in children),
                            "children": children})
        return out

    def story_leaf(self, key):
        w = key[5:] if key.startswith("work:") else key
        sw = self.story_work_map.get(w)
        official = self.official.get(w)
        if not sw and not official:
            return {"key": key, "name": "（无此分类）", "routes": [], "chapters": [], "total": 0}
        routes = []
        root_chapters = [{"title": c["title"], "doc": c["doc"], "start": c["start"], "end": c["end"],
                          "sections": c.get("sections", [])}
                         for c in (sw.get("root_chapters", []) if sw else [])]
        if official:
            # 正篇用官方文本，篇外用本地整理的旧文本
            for p in official:
                routes.append({"name": p["name"], "chars": 0, "extra": False,
                               "chapters": [{"title": c["title"], "official": w,
                                             "id": c["id"],
                                             "group": c.get("group", ""),
                                             "lines": c["lines"],
                                             "sections": len(c["sections"])}
                                            for c in p["chapters"]]})
        for r in (sw["routes"] if sw else []):
            extra = r.get("extra", False)
            if official and not extra:
                continue          # 正篇已被官方文本取代
            routes.append({"name": r["name"], "chars": r.get("chars", 0),
                           "extra": extra,
                           "chapters": [{"title": c["title"], "doc": c["doc"],
                                         "start": c["start"], "end": c["end"],
                                         "group": c.get("group", ""),
                                         "prereq": bool(c.get("prereq", False)),
                                         "main_index": c.get("main_index"),
                                         "sections": c.get("sections", [])}
                                        for c in r["chapters"]]})
        return {"key": key, "name": WORK_LABEL.get(w, w), "routes": routes,
                "chapters": root_chapters,
                "total": len(root_chapters) + sum(len(r["chapters"]) for r in routes)}
    def build_nav(self):
        """把作品 → 分类（路线/年份/职阶）→ 章节/小节组装成可逐级下钻的树。"""
        nav = {}

        def add(key, name, children=None, chapters=None, **extra):
            node = {"key": key, "name": name, "children": children or [],
                    "chapters": chapters or []}
            node.update(extra)
            nav[key] = node
            return key

        self.nav_roots = []
        for tid, tname, works in STORY_TAXONOMY:
            kids = []
            for w in works:
                official = self.official.get(w)
                sw = self.story_work_map.get(w)
                wkey = "work:" + w
                rkeys = []
                if official:
                    for p in official:
                        rkey = wkey + "||route:" + p["name"]
                        chapter_keys = []
                        groups = {}
                        group_order = []
                        for c in p["chapters"]:
                            ckey = rkey + "||chapter:" + str(c["id"])
                            section_titles = c.get("sections") or []
                            if not section_titles:
                                section_titles = [c["title"]]
                            section_keys = []
                            for index, title in enumerate(section_titles):
                                skey = ckey + "||section:" + str(index)
                                href = ("official_reader.html?work=%s&id=%s&sec=%s" %
                                        (urllib.parse.quote(w), c["id"], index))
                                add(skey, title, kind="official_section", href=href,
                                    official=w, id=c["id"], section=index, count=0,
                                    group=c.get("group", ""))
                                section_keys.append(skey)
                            add(ckey, c["title"], children=section_keys,
                                kind="official_chapter", count=1, official=w, id=c["id"],
                                section_count=len(section_keys))
                            chapter_keys.append(ckey)
                            g = c.get("group") or ""
                            if g == p["name"]:
                                g = ""
                            if g and g not in groups:
                                groups[g] = []
                                group_order.append(g)
                            groups.setdefault(g, []).append(ckey)
                        route_children = []
                        nonempty = [g for g in group_order if g]
                        if not nonempty:
                            route_children = chapter_keys
                        elif len(groups) == 1:
                            route_children = chapter_keys
                        else:
                            for ckey in groups.get("", []):
                                route_children.append(ckey)
                            for g in nonempty:
                                gkey = rkey + "||group:" + g
                                add(gkey, g, children=groups[g])
                                route_children.append(gkey)
                        add(rkey, p["name"], children=route_children)
                        rkeys.append(rkey)
                else:
                    sw = self.story_work_map.get(w)
                    if not sw:
                        continue
                    for r in sw["routes"]:
                        rkey = wkey + "||route:" + r["name"]
                        groups, order, ungrouped = {}, [], []
                        for c in r["chapters"]:
                            g = c.get("group") or ""
                            if g == r["name"]:
                                g = ""
                            if not g:
                                ungrouped.append(c)
                                continue
                            if g not in groups:
                                groups[g] = []
                                order.append(g)
                            groups[g].append(c)
                        if len(groups) == 1 and order and order[0] in r["name"] and not ungrouped:
                            add(rkey, r["name"], chapters=groups[order[0]])
                        elif groups:
                            gkeys = []
                            for g in order:
                                gkey = rkey + "||group:" + g
                                add(gkey, g, chapters=groups[g])
                                gkeys.append(gkey)
                            add(rkey, r["name"], children=gkeys, chapters=ungrouped)
                        else:
                            add(rkey, r["name"], chapters=r["chapters"])
                        rkeys.append(rkey)
                add(wkey, WORK_LABEL.get(w, w), children=rkeys, chapters=(sw.get("root_chapters", []) if sw else []))
                kids.append(wkey)
            if kids:
                self.nav_roots.append({"key": "top:" + tid, "name": tname, "children": kids})
        self.nav = nav
        print(f"目录树：{len(nav):,} 个节点")

    def story_node(self, key):
        node = self.nav.get(key)
        if not node:
            return {"key": key, "name": "（无此分类）", "children": [], "chapters": []}
        crumb = []
        parts = key.split("||")
        acc = parts[0]
        for i, seg in enumerate(parts):
            if i:
                acc += "||" + seg
            n = self.nav.get(acc)
            if n:
                crumb.append({"key": acc, "name": n["name"]})
        children = []
        for k in node["children"]:
            source = self.nav[k]
            child = {"key": k, "name": source["name"],
                     "count": self.count_chapters(k)}
            for field in ("kind", "section_count", "href", "section", "official", "id"):
                if source.get(field) is not None:
                    child[field] = source.get(field)
            children.append(child)
        out = {"key": key, "name": node["name"], "breadcrumb": crumb,
               "children": children, "chapters": []}
        for c in node["chapters"]:
            item = {"title": c["title"]}
            if c.get("official"):
                item["official"] = c["official"]
                item["id"] = c.get("id")
                if c.get("section") is not None:
                    item["section"] = c.get("section")
                if c.get("sections") is not None:
                    sec = c.get("sections")
                    item["sections"] = sec if isinstance(sec, int) else len(sec or [])
            else:
                item.update({"doc": c.get("doc"), "start": c.get("start"), "end": c.get("end")})
                if c.get("key"):
                    item["key"] = c["key"]
            out["chapters"].append(item)
        return out

    def count_chapters(self, key):
        node = self.nav.get(key)
        if not node:
            return 0
        if node.get("count") is not None:
            return node["count"]
        total = len(node["chapters"])
        if node["children"]:
            total += sum(self.count_chapters(k) for k in node["children"])
        return total

    def _leaf_chapters(self, key):
        node = self.nav.get(key)
        if not node:
            return []
        return node["chapters"]

    def scope_set(self, scope):
        if not scope or scope == "all":
            return None
        return self.scope_docs.get(scope, set())

    def source(self, doc_id):
        d = self.docs[doc_id]
        return {"title": d["title"], "work": d["work"], "kind": d["kind"],
                "file": d["file"], "meta": d.get("meta", {}), "id": doc_id}

    def seg_of(self, pos):
        if self._recovered_starts and pos >= self._legacy_corpus_length:
            index = bisect.bisect_right(self._recovered_starts, pos) - 1
            if index >= 0:
                return self._recovered_segment_base + index
        return bisect.bisect_right(self._legacy_starts, pos) - 1

    def occurrence_terms(self, requested, canonical, targets=None):
        terms, seen = [], set()

        def add(value, safe_only=False):
            value = (value or "").strip()
            if not value or len(value) < 2:
                return
            if safe_only:
                flat = re.sub(r"\s+", "", value)
                if (len(flat) < 3 and flat not in OCCURRENCE_SHORT_ALIASES
                        and not re.search(r"[A-Za-z0-9·・‧．.]", flat)):
                    return
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                terms.append(value)

        add(requested, safe_only=False)
        add(canonical, safe_only=False)
        for target in targets or []:
            add(target)
        # 繁简等查询改写不只用于长句兜底；短词也应同时命中原文变体。
        for rewritten in query_rewrite_parts(requested):
            add(rewritten, safe_only=False)
        target_keys = {term_key(x).casefold() for x in ([canonical] + list(targets or [])) if x}

        # 概念卡中的异体、原题名与规范名。
        concept_ids = set()
        for key in target_keys:
            rows = self.entries_by_term.get(key)
            if not rows:
                rows = next((r for t, r in self.entries_by_term.items()
                             if t.casefold() == key), [])
            for entry in rows:
                if entry.get("concept_id"):
                    concept_ids.add(entry["concept_id"])
        if concept_ids:
            for entry in self.entries:
                if entry.get("concept_id") not in concept_ids:
                    continue
                add(entry.get("source_term"), safe_only=True)
                add(entry.get("display_term"), safe_only=True)
                add(entry.get("term"), safe_only=True)

        # 反向别名：只纳入较具体或拉丁化的同义词，避免“公主”这类泛称污染统计。
        def alias_targets_match(raw):
            values = raw if isinstance(raw, list) else [raw]
            return any(term_key(value).casefold() in target_keys for value in values if value)

        for nick, raw in ALIAS_TARGETS.items():
            if alias_targets_match(raw):
                add(nick, safe_only=True)
        for nick, raw in ALIAS.items():
            if alias_targets_match(raw):
                add(nick, safe_only=True)
        return terms

    def resolve_query(self, q):
        requested = (q or "").strip()
        normalized, normalization = normalize_query(requested)
        hit = alias_lookup(normalized) or alias_lookup(requested)
        targets = []
        if hit:
            targets = hit[1] if isinstance(hit[1], list) else [hit[1]]
            canonical = targets[0] if len(targets) == 1 else normalized
        else:
            canonical = normalized
        terms = self.occurrence_terms(requested, canonical, targets)
        return requested, canonical, hit, normalization, terms

    def multi_term_groups(self, q):
        """Build ordered synonym groups for an explicit separated multi-term query."""
        groups, seen = [], set()
        for fragment in split_multi_terms(q):
            requested, canonical, _hit, _normalization, terms = self.resolve_query(fragment)
            key = term_key(canonical).casefold()
            if key in seen:
                continue
            seen.add(key)
            variants, variant_seen = [], set()
            for value in list(terms or []) + [requested, canonical]:
                value = (value or "").strip()
                variant_key = value.casefold()
                if not value or variant_key in variant_seen:
                    continue
                variant_seen.add(variant_key)
                variants.append(value)
            if variants:
                groups.append({"input": fragment, "canonical": canonical, "variants": variants})
        return groups if len(groups) >= 2 else []

    def search_multi(self, q, limit=60, scope=""):
        return self.multi_engine.search(q, limit=limit, scope=scope)

    def definitions_multi(self, q, scope="", offset=0, limit=20):
        return self.multi_engine.definitions_view(q, scope, offset, limit)

    def list_view_multi(self, q, work="", offset=0, limit=50, scope=""):
        return self.multi_engine.list_view(q, work, offset, limit, scope)

    def scan(self, q, terms=None, max_passages=20000, max_hits=200000):
        """把整个语料扫一遍：按作品统计命中次数与段落数，并收集全部段落（供完整列举）。"""
        cache_key = (q, tuple(terms or []))
        cached_q, cached = self._scan_cache
        if cached_q == cache_key:
            return cached
        pat = occurrence_pattern(terms) if terms else query_pattern(q, kind="text")
        work_hits, work_segs = {}, {}
        doc_set, work_docs = set(), {}
        items, seen = [], {}
        hits, truncated, stopped = 0, False, False
        matches = pat.finditer(self.corpus)
        for m in matches:
            pos = m.start()
            hits += 1
            seg = self.seg_of(pos)
            if seg >= 0:
                doc_id = self.offsets[seg][2]
                work = self.docs[doc_id]["work"]
                work_hits[work] = work_hits.get(work, 0) + 1
                doc_set.add(doc_id)
                work_docs.setdefault(work, set()).add(doc_id)
                if seg in seen:
                    seen[seg]["n"] += 1
                else:
                    work_segs[work] = work_segs.get(work, 0) + 1
                    if len(items) < max_passages:
                        item = {"pos": pos, "seg": seg, "doc": doc_id,
                                "block": self.offsets[seg][3], "work": work, "n": 1}
                        seen[seg] = item
                        items.append(item)
                    else:
                        truncated = True
            if hits >= max_hits:
                truncated = True
                stopped = True
                break
        total = hits + (sum(1 for _ in matches) if stopped else 0)   # 命中上限截断时补算总数
        data = {"hits": hits, "work_hits": work_hits, "work_segs": work_segs,
                "work_docs": {w: len(s) for w, s in work_docs.items()},
                "items": items, "truncated": truncated, "docs": len(doc_set),
                "total": total}
        self._scan_cache = (cache_key, data)
        return data

    def snippet_window(self, pos, q, terms=None, before=2, after=2,
                       min_len=60, max_len=SNIPPET_PARAGRAPH_TARGET,
                       hard_max=SNIPPET_PARAGRAPH_HARD):
        """Return the whole matching paragraph, with bounded adjacent context."""
        seg = self.seg_of(pos)
        if seg < 0:
            doc_id = None
            doc_start, doc_end = 0, len(self.corpus)
        else:
            doc_id = self.offsets[seg][2]
            doc_start, doc_end = self.doc_span.get(doc_id, (0, len(self.corpus)))
        text = self.corpus[doc_start:doc_end]
        local_pos = min(max(pos - doc_start, 0), len(text))
        match_len = max([len(x) for x in (terms or []) if x] or [len(q or ""), 1])
        local_match_end = min(len(text), local_pos + match_len)
        blocks = []
        for _order, block_start, block_length in self.doc_index.get(doc_id, []):
            if block_length <= 0:
                continue
            start = max(0, block_start - doc_start)
            end = min(len(text), block_start + block_length - doc_start)
            if end > start:
                blocks.append((start, end))
        hard_limit = min(hard_max, SNIPPET_PARAGRAPH_HARD - 2)
        local_start, local_end = select_block_snippet_span(
            text, blocks, local_pos, local_match_end,
            target_len=min(max_len, hard_limit), hard_max=hard_limit,
        )
        return doc_start + local_start, doc_start + local_end

    def snippet_text(self, s, e, doc_id=None):
        if doc_id is None:
            start, end = 0, len(self.corpus)
        else:
            start, end = self.doc_span.get(doc_id, (0, len(self.corpus)))
        text = self.corpus[s:e].replace("\n", "　")
        text = text.replace("＠", "　").replace("[lr]", "　")
        text = re.sub(r"<IMG[^>]{0,80}>", "", text, flags=re.I)
        text = re.sub(r"[ \t　]{2,}", "　", text).strip()
        return ("…" if s > start else "") + text + ("…" if e < end else "")

    def snippet(self, pos, q, terms=None, before=2, after=2,
                min_len=60, max_len=SNIPPET_PARAGRAPH_TARGET):
        """按完整段落截取；短段补相邻段，超长段保留多句上下文。"""
        s, e = self.snippet_window(pos, q, terms=terms, before=before, after=after,
                                   min_len=min_len, max_len=max_len)
        seg = self.seg_of(pos)
        doc_id = self.offsets[seg][2] if seg >= 0 else None
        return self.snippet_text(s, e, doc_id)

    def suggest(self, q, limit=10):
        if not q:
            return []
        query = q.strip()
        ql = query.lower()
        out, seen = [], set()

        def formal_term(value):
            key = term_key(value)
            items = self.entries_by_term.get(key)
            if items:
                return items[0].get("term") or key
            low = key.lower()
            matches = []
            for term, rows in self.entries_by_term.items():
                if term.lower() == low:
                    term_name = rows[0].get("term") or term
                    matches.append(term_name)
            if matches:
                return max(matches, key=lambda term: (self.vocab_freq.get(term, 0),
                                                       -len(term), term))
            return ""

        def add(value, alias=None, force=False):
            value = (value or "").strip()
            if not value:
                return
            formal = formal_term(value)
            if formal:
                value = formal
            else:
                aliased = term_key(value)
                if alias is not None or aliased != unicodedata.normalize("NFKC", value).replace(" ", "").replace("　", ""):
                    return
            key = value.casefold()
            if key in seen:
                if alias:
                    old = next((x for x in out if x["t"].casefold() == key), None)
                    if old and not old.get("alias"):
                        old["alias"] = alias
                return
            seen.add(key)
            out.append({"t": value, "n": self.vocab_freq.get(value, 0),
                        "alias": alias})

        # 1) 完整别名 / 完整正式词条。
        hit = alias_lookup(query)
        if hit:
            for target in hit[1] if isinstance(hit[1], list) else [hit[1]]:
                add(target, alias=hit[0])
        else:
            add(query)

        # 2) 可配置的固定优先顺序（例如 arc）。
        for value in SUGGEST_OVERRIDES.get(query) or []:
            add(value, force=True)

        # 3) 别名前缀展开：只回填到正式词条。
        for nick, target in alias_prefix(query, limit=20):
            targets = target if isinstance(target, list) else [target]
            for value in targets:
                add(value, alias=nick)

        # 4) 正式词条前缀，再是边界/包含命中。
        formal_terms = set()
        for rows in self.entries_by_term.values():
            for entry in rows:
                formal_terms.add(entry.get("term") or "")
        prefix, contains_other = [], []
        for value in sorted(formal_terms):
            if not value:
                continue
            low = value.lower()
            if low.startswith(ql):
                prefix.append(value)
            elif ql in low:
                contains_other.append(value)
        for value in sorted(prefix, key=lambda x: (-self.vocab_freq.get(x, 0), len(x), x)):
            add(value)
        for value in sorted(contains_other, key=lambda x: (-self.vocab_freq.get(x, 0), len(x), x)):
            add(value)

        # 5) 非别名的普通语料词仍允许出现；无正式目标的别名会被 add 过滤。
        for item in self.suggest_raw(query, limit=max(limit * 4, 24)):
            add(item.get("t"), force=True)

        if ql in SUGGEST_OVERRIDES:
            order = [str(x).casefold() for x in SUGGEST_OVERRIDES[ql]]
            rank = {key: i for i, key in enumerate(order)}
            out.sort(key=lambda x: (rank.get(x["t"].casefold(), len(rank)),))
        return out[:limit]

    def _fate_heavy(self, exact):
        """精确卡里 Fate 系作品占多数（>50%）时，跨组预排序按 FSN → FE → FEX/FEXL → 其他分组。"""
        if not exact:
            return False
        n = sum(1 for e in exact if self.docs[e["doc"]]["work"] in FATE_WORKS)
        return n * 2 > len(exact)

    def _entry_rank(self, e):
        body = e.get("body") or ""
        flat = re.sub(r"\s+", "", body)
        placeholder = len(flat) < 40 or any(h in body[:60] for h in JUNK_HINT)
        return (1 if placeholder else 0,
                0 if int(e.get("definition_quality") or 0) > 0 else 1,
                -len(flat),
                0 if (e.get("authority") or "official_source") == "official_source" else 1,
                0 if e.get("translation_kind") in ("original", "direct") else 1,
                -len(body))

    def _variant_view(self, e):
        source = self.source(e["doc"])
        refs = e.get("source_refs") or []
        translator = e.get("translator") or ((refs[0].get("translator") if refs else "") or "")
        if translator:
            source = dict(source)
            source["meta"] = dict(source.get("meta") or {})
            source["meta"]["译者"] = translator
        return {
            "variant_id": e.get("variant_id") or "",
            "entry_type": e.get("entry_type") or "definition",
            "cat": e.get("cat") or "",
            "display_term": e.get("display_term") or e.get("term") or "",
            "concept_id": e.get("concept_id") or "",
            "entity_id": e.get("entity_id") or "",
            "source_unit_id": e.get("source_unit_id") or "",
            "translation_group_id": e.get("translation_group_id") or "",
            "source_locator": e.get("source_locator") or {},
            "body": e.get("body") or "",
            "jp_body": e.get("jp_body"),
            "definition_quality": int(e.get("definition_quality") or 0),
            "truncated": e.get("truncated", False),
            "source": source,
            "source_authority": e.get("authority") or "official_source",
            "translation_kind": e.get("translation_kind") or "direct",
            "source_refs": refs,
            "is_primary": bool(e.get("is_primary")),
            "conflict_flags": e.get("conflict_flags") or [],
        }

    def _meaning_card(self, items, seen_bodies=None):
        items = sorted(items, key=lambda e: (0 if e.get("is_meaning_primary") else 1,
                                             self._entry_rank(e)))
        items = items[:3]  # 首卡 + 最多两个其他译本
        variants, seen_variants, bodies = [], set(), set()
        for e in items:
            vid = e.get("variant_id") or ("v:" + str(e["doc"]))
            body_key = e.get("variant_id") or e.get("body") or ""
            if vid in seen_variants or body_key in bodies:
                continue
            if seen_bodies is not None and body_key in seen_bodies:
                continue
            seen_variants.add(vid)
            bodies.add(body_key)
            if seen_bodies is not None:
                seen_bodies.add(body_key)
            variants.append(self._variant_view(e))
        if not variants:
            return None
        card = dict(variants[0])
        card["variants"] = variants
        card["variant_count"] = len(variants)
        card["source_authority"] = card.get("source_authority") or "official_source"
        card["translation_kind"] = card.get("translation_kind") or "direct"
        return card

    @staticmethod
    def _definition_text(e):
        """正文归一化：去掉标签、链接、空白、标点和分类标记，只保留有效字符。"""
        value = e.get("body") or ""
        value = HTML_BODY_LINK_RE.sub(r"\1", value)
        value = MD_BODY_LINK_RE.sub(r"\1", value)
        value = HTML_TAG_RE.sub("", value)
        value = unicodedata.normalize("NFKC", value)
        value = DEFINITION_CATEGORY_RE.sub("", value)
        return re.sub(r"[\W_]+", "", value)

    @classmethod
    def _definition_duplicate(cls, first, second):
        """归一化后高度相似、长度也接近的定义视为同一张卡。"""
        left, right = cls._definition_text(first), cls._definition_text(second)
        if not left or not right:
            return False
        short, long = sorted((left, right), key=len)
        if len(short) / len(long) < DEFINITION_DUPLICATE_LENGTH_RATIO:
            return False
        matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
        return matcher.ratio() >= DEFINITION_DUPLICATE_MIN_RATIO

    @staticmethod
    def _definition_coverage(short, long):
        """短定义有至少 70% 内容被长定义覆盖时，视为涵盖关系。"""
        if (len(short) < DEFINITION_COVERAGE_MIN_CHARS
                or len(long) < len(short) * DEFINITION_COVERAGE_LENGTH_RATIO):
            return 0.0
        matcher = difflib.SequenceMatcher(None, short, long, autojunk=False)
        matched = sum(block.size for block in matcher.get_matching_blocks())
        ratio = matched / len(short)
        return ratio if ratio >= DEFINITION_COVERAGE_MIN_RATIO else 0.0

    @classmethod
    def _definition_coverage_key(cls, card, peers, texts):
        body = texts[id(card)]
        covered_count, covered_chars = 0, 0
        for peer in peers:
            if peer is card:
                continue
            peer_body = texts[id(peer)]
            if not body or not peer_body or len(body) <= len(peer_body):
                continue
            if cls._definition_coverage(peer_body, body):
                covered_count += 1
                covered_chars += len(peer_body)
        return (-covered_count, -covered_chars)

    @staticmethod
    def _definition_work(card):
        return ((card.get("source") or {}).get("work") or "")

    @classmethod
    def _primary_version_key(cls, card):
        work = cls._definition_work(card)
        if work in NORMAL_GRAIL_ORDER:
            return (0, NORMAL_GRAIL_ORDER[work])
        if work in SPECIAL_GRAIL_ORDER:
            return (1, SPECIAL_GRAIL_ORDER[work])
        return (2, 0)

    @classmethod
    def _is_forced_primary(cls, card):
        doc_id = (card.get("source") or {}).get("id")
        return DEFINITION_FORCED_PRIMARY.get(card.get("group_id")) == doc_id

    @staticmethod
    def _definition_display_body(term, doc_id, body):
        text = body or ""
        prefix = DEFINITION_BODY_PREFIXES.get((term, doc_id), "")
        if prefix and not text.startswith(prefix):
            text = prefix + text
        for old, new in DEFINITION_BODY_REPLACEMENTS.get((term, doc_id), ()):
            text = text.replace(old, new)
        return text

    def _apply_definition_display_overrides(self, card):
        term = card.get("display_term") or card.get("term") or ""
        for variant in card.get("variants") or []:
            doc_id = (variant.get("source") or {}).get("id")
            variant["body"] = self._definition_display_body(
                term, doc_id, variant.get("body"))
        doc_id = (card.get("source") or {}).get("id")
        card["body"] = self._definition_display_body(term, doc_id, card.get("body"))

    @classmethod
    def _definition_version_bucket(cls, card):
        work = cls._definition_work(card)
        if work in NORMAL_GRAIL_ORDER:
            return "normal"
        if work in SPECIAL_GRAIL_ORDER:
            return "special"
        return "other"

    @classmethod
    def _same_version_key(cls, card):
        work = cls._definition_work(card)
        if work in SPECIAL_GRAIL_ORDER:
            return (0, SPECIAL_GRAIL_ORDER[work])
        if work in NORMAL_GRAIL_ORDER:
            return (1, NORMAL_GRAIL_ORDER[work])
        return (2, 0)

    def _definition_primary_key(self, card, peers, texts, coverage_keys=None):
        coverage = ((coverage_keys or {}).get(id(card))
                    or self._definition_coverage_key(card, peers, texts))
        return (0 if self._is_forced_primary(card) else 1,
                coverage,
                self._primary_version_key(card),
                0 if card.get("is_primary") else 1,
                self._entry_rank(card))

    def _definition_same_key(self, card, peers, texts, coverage_keys=None):
        coverage = ((coverage_keys or {}).get(id(card))
                    or self._definition_coverage_key(card, peers, texts))
        return (coverage,
                self._same_version_key(card),
                0 if card.get("is_primary") else 1,
                self._entry_rank(card))

    def _prune_covered_meaning_cards(self, cards):
        """同一版本层级内，只保留未被其他定义涵盖的卡片。"""
        if len(cards) < 2:
            return cards
        texts = {id(card): self._definition_text(card) for card in cards}
        buckets = defaultdict(list)
        for card in cards:
            buckets[self._definition_version_bucket(card)].append(card)

        removed = set()
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            covered = set()
            for candidate in bucket:
                if self._is_forced_primary(candidate):
                    continue
                candidate_text = texts[id(candidate)]
                for other in bucket:
                    if candidate is other:
                        continue
                    other_text = texts[id(other)]
                    if (len(other_text) > len(candidate_text)
                            and self._definition_coverage(candidate_text, other_text)):
                        covered.add(id(candidate))
                        break
            keep = [card for card in bucket if id(card) not in covered]
            if not keep:  # 极端传递关系下也必须保留一张代表卡
                keep = [max(bucket, key=lambda card: len(texts[id(card)]))]
            keep_ids = {id(card) for card in keep}
            for card in bucket:
                if id(card) not in keep_ids:
                    removed.add(id(card))
        return [card for card in cards if id(card) not in removed]

    def _dedupe_meaning_cards(self, cards):
        """同一 group 内传递合并近重复卡，并保留排序最高的代表卡。"""
        if len(cards) < 2:
            return cards
        parent = list(range(len(cards)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left, right):
            left, right = find(left), find(right)
            if left != right:
                parent[right] = left

        for i, first in enumerate(cards):
            for j in range(i + 1, len(cards)):
                if self._definition_duplicate(first, cards[j]):
                    union(i, j)

        clusters = defaultdict(list)
        for index, card in enumerate(cards):
            clusters[find(index)].append(card)
        texts = {id(card): self._definition_text(card) for card in cards}
        return [min(cluster, key=lambda card: self._definition_primary_key(card, cards, texts))
                for cluster in clusters.values()]

    def _group_entry_cards(self, entries, match):
        groups = defaultdict(list)
        for e in entries:
            gid = (e.get("group_id") or e.get("concept_id")
                   or ("term:" + (e.get("term") or "")))
            groups[gid].append(e)
        cards = []
        for _gid, items in groups.items():
            meanings = defaultdict(list)
            for e in items:
                mgid = e.get("translation_group_id") or e.get("source_unit_id") or e.get("variant_id")
                meanings[mgid].append(e)
            meaning_cards = []
            seen_bodies = set()
            for mgid, group in meanings.items():
                card = self._meaning_card(group, seen_bodies=seen_bodies)
                if card is None:
                    continue
                card["translation_group_id"] = mgid
                card["group_id"] = _gid
                card["meaning_primary"] = bool(group and group[0].get("is_meaning_primary"))
                meaning_cards.append(card)
            ranked_cards = self._dedupe_meaning_cards(meaning_cards)
            if not ranked_cards:
                continue
            ranked_texts = {id(c): self._definition_text(c) for c in ranked_cards}
            coverage_keys = {
                id(c): self._definition_coverage_key(c, ranked_cards, ranked_texts)
                for c in ranked_cards
            }
            meaning_cards = self._prune_covered_meaning_cards(ranked_cards)
            if not meaning_cards:
                continue
            buckets = {
                bucket: [c for c in meaning_cards if self._definition_version_bucket(c) == bucket]
                for bucket in ("normal", "special", "other")
            }
            primary_pool = buckets["normal"] if buckets["normal"] and buckets["special"] else meaning_cards
            primary_obj = min(
                primary_pool,
                key=lambda c: self._definition_primary_key(
                    c, ranked_cards, ranked_texts, coverage_keys),
            )
            same = [c for c in meaning_cards if c is not primary_obj]
            same.sort(key=lambda c: self._definition_same_key(
                c, ranked_cards, ranked_texts, coverage_keys))
            primary = dict(primary_obj)
            self._apply_definition_display_overrides(primary)
            for card in same:
                self._apply_definition_display_overrides(card)
            primary["same_concept"] = same
            primary["same_concept_count"] = len(same)
            primary["group_id"] = _gid
            display_term = DEFINITION_GROUP_TERM_OVERRIDES.get(_gid)
            if display_term:
                primary["display_term"] = display_term
                primary["term"] = display_term
            else:
                primary["term"] = primary.get("display_term") or primary.get("term") or ""
            primary["match"] = match
            primary["exact"] = match == "exact"
            primary["concept_id"] = primary.get("concept_id") or _gid
            primary["translation_group_id"] = primary.get("translation_group_id") or ""
            primary["source_authority"] = primary.get("source_authority") or "official_source"
            primary["translation_kind"] = primary.get("translation_kind") or "direct"
            primary["entry_type"] = primary.get("entry_type") or "definition"
            primary["entity_id"] = primary.get("entity_id") or ""
            flags = []
            for e in items:
                for flag in e.get("conflict_flags") or []:
                    if flag not in flags:
                        flags.append(flag)
            primary["conflict_flags"] = flags
            cards.append(primary)
        return cards

    def ordered_definitions(self, q, allow=None):
        """按既定规则排出该查询的全部词解卡（精确 → 词条名包含 → 正文提及），预览页与「查看全部」页共用。"""
        latin = is_latin_query(q)
        pat_name = query_pattern(q, latin, "name")
        pat_text = query_pattern(q, latin, "text")

        exact, _seen_t = [], set()
        for t in [q] + self.terms_ci.get(q.lower(), []):
            if t in _seen_t:
                continue
            _seen_t.add(t)
            exact.extend(self.entries_by_term.get(t, []))
        exact = [e for e in exact if allow is None or e["doc"] in allow]
        canonical = exact[0]["term"] if exact else q
        exact_names = {e["term"] for e in exact}

        # 英文按下搜索不产生「词条名包含关联」；中文才出含词卡
        contains_names = []
        if not latin:
            contains_names = [t for t in self.term_list
                              if t not in exact_names and pat_name.search(t)]
        contains = []
        for t in contains_names:
            for e in self.entries_by_term.get(t, []):
                if allow is None or e["doc"] in allow:
                    contains.append(e)

        # 中文：含该词的词条一多就不再展开「词解正文含该词」
        body_hits = []
        if latin or len(contains_names) <= CN_EXPAND_MAX:
            for e in self.entries:
                if e["term"] in exact_names:
                    continue
                if allow is not None and e["doc"] not in allow:
                    continue
                if pat_text.search(e.get("body") or ""):
                    body_hits.append(e)

        def def_rank(e):
            """同一术语多条定义时：先按章节档次，再把占位/过短的沉到最后，长定义优先。"""
            body = e.get("body") or ""
            flat = re.sub(r"\s+", "", body)
            placeholder = len(flat) < 40 or any(h in body[:60] for h in JUNK_HINT)
            return (1 if placeholder else 0, KIND_ORDER.get(self.docs[e["doc"]]["kind"], 4),
                    -len(body))

        fate = self._fate_heavy(exact)

        def grp(e):
            """资料组：启用时 FSN=0 → FE=1 → 其他=2；否则一律 0（不影响原顺序）。"""
            return MAT_GROUP.get(self.docs[e["doc"]]["work"], 3) if fate else 0

        pinned_terms = set(QUERY_PINS.get(q, ()))

        def body_rank(e):
            """正文命中卡：用户固定项 → 资料组 → 出现次数 → 密度 → 原排序。"""
            body = e.get("body") or ""
            n = len(pat_text.findall(body))
            pinned = 0 if e.get("term") in pinned_terms else 1
            return (pinned, grp(e), -n, -n / max(len(body), 1) * 1000) + def_rank(e)

        def one_per_term(group, key):
            """同一术语只留排序最高的一张卡（非精确桶用）。"""
            out, seen = [], set()
            for e in sorted(group, key=key):
                if e["term"] in seen:
                    continue
                seen.add(e["term"])
                out.append(e)
            return out

        preferred_group = QUERY_PRIMARY_GROUPS.get(term_key(q))

        def entry_group_id(entry):
            return (entry.get("group_id") or entry.get("concept_id")
                    or ("term:" + (entry.get("term") or "")))

        groups = (
            ("exact", sorted(exact, key=lambda e: (grp(e),) + def_rank(e))),
            ("contains", sorted(contains, key=lambda e: (
                0 if preferred_group and entry_group_id(e) == preferred_group else 1,
                grp(e),
                -self.vocab_freq.get(e["term"], 0),
                0 if pat_name.match(e["term"]) else 1,
                len(e["term"]), def_rank(e)))),
            ("body", sorted(body_hits, key=body_rank)),
        )
        cards = self._group_entry_cards(groups[0][1], "exact")
        seen_groups = {c.get("group_id") for c in cards if c.get("group_id")}
        for kind, group in groups[1:]:
            for card in self._group_entry_cards(group, kind):
                gid = card.get("group_id")
                if gid in seen_groups:
                    continue
                seen_groups.add(gid)
                cards.append(card)
        forced_group = DEFINITION_FORCED_FIRST_GROUP.get(term_key(q))
        if forced_group:
            cards.sort(key=lambda card: 0 if card.get("group_id") == forced_group else 1)
        return cards, canonical

    def suggest_raw(self, q, limit=10):
        """联想补全（一律忽略大小写）：
        英文——① 词条以该词开头 ② 该词是完整词（后面不是字母/数字）③ 该词只是更长英文词的词首；
        中文——① 前缀 ② 包含。层内按词频降序 → 名称长度 → 名称。
        """
        ql = q.lower()
        latin = is_latin_query(q)
        pat = query_pattern(q, True, "name") if latin else None
        tiers = ([], [], [])
        for v in self.vocab_sorted:
            t, low = v["t"], v["t"].lower()
            if latin:
                m = pat.search(t)
                if not m:
                    continue                      # 必须落在词边界上（Forte 里的 ort 不算）
                if m.start() == 0:
                    tiers[0].append(v)
                elif re.match(r"[A-Za-z0-9]", low[m.start() + len(q):m.start() + len(q) + 1] or ""):
                    tiers[2].append(v)
                else:
                    tiers[1].append(v)
            elif low.startswith(ql):
                tiers[0].append(v)
            elif ql in low:
                tiers[1].append(v)
        out, seen = [], set()
        for bucket in tiers:
            for v in sorted(bucket, key=lambda x: (-x["n"], len(x["t"]), x["t"])):
                if v["t"] in seen:
                    continue
                seen.add(v["t"])
                out.append(v)
                if len(out) >= limit:
                    return out
        return out

    def _fallback_parts(self, q):
        """长句无精确命中时，优先提取真实命中的长片段，再使用改写、术语和分句。"""
        specific = []
        for n in (24, 20, 16, 12, 10, 8):
            local = []
            step = max(2, n // 3)
            for i in range(0, max(0, len(q) - n + 1), step):
                sub = q[i:i + n]
                if len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", sub)) < 6:
                    continue
                if self.corpus.find(sub) >= 0:
                    local.append(sub)
                    if len(local) >= 4:
                        break
            specific.extend(local)
            if len(specific) >= 6:
                break
        specific = sorted(set(specific), key=lambda x: (-len(x), self.corpus.count(x)))[:8]

        low = q.lower()
        generic = {"人类", "神灵", "自然", "世界", "存在", "力量", "时代", "现象", "规则"}
        terms = []
        for t in self.term_list:
            if len(t) < 3 or t in generic:
                continue
            if t.lower() in low and self.vocab_freq.get(t, 0) <= 5000:
                terms.append(t)
        terms = sorted(set(terms), key=lambda x: (-len(x), self.vocab_freq.get(x, 0)))[:8]
        parts = [x.strip() for x in re.split(
            r"[，。！？；：、\s\n\r“”‘’「」『』（）()\[\]【】]+", q)
            if len(x.strip()) >= 4]
        out = []
        for x in specific + query_rewrite_parts(q) + terms + parts:
            x = x.strip("“”‘’「」『』 ")
            if x and x not in out:
                out.append(x)
        return out[:16]

    def _build_official(self):
        """Load the generated official-answer and interview index."""
        path = os.path.join(DATA, "official_interviews.json")
        empty = {"version": 1, "primary_docs": [], "qa": [], "supplements": [], "stats": {}}
        self.official_index = read_json(path) if os.path.exists(path) else empty
        self.official_primary = self.official_index.get("primary_docs") or []
        self.official_qa = self.official_index.get("qa") or []
        self.official_supplements = self.official_index.get("supplements") or []
        self.official_doc_order = {item["doc"]: index for index, item in enumerate(self.official_primary)}
        print("官方回答/访谈索引：%d 篇访谈 / %d 条问答 / %d 条补充来源" %
              (len(self.official_primary), len(self.official_qa), len(self.official_supplements)))

    def _official_matcher(self, q, scope="", multi=False):
        if multi:
            analysis = self.multi_engine.analysis(q, scope)
            groups = analysis.get("groups") or []
            level = int(analysis.get("level") or 0)
            if not groups or not level:
                return (lambda _text: []), []
            pattern, owners = self.multi_engine._compile_pattern(groups)
            highlight = []
            for group in groups:
                for value in group.get("variants") or []:
                    if value and value not in highlight:
                        highlight.append(value)

            def match(text):
                _positions, mask = self.multi_engine._match(text, pattern, owners)
                if mask.bit_count() < level:
                    return []
                return [groups[index]["input"] for index in range(len(groups))
                        if mask & (1 << index)]
            return match, highlight

        _requested, canonical, _hit, _normalization, terms = self.resolve_query(q)
        patterns = []
        for term in terms:
            pattern = query_pattern(term, is_latin_query(term), "text")
            patterns.append((term, pattern))

        def match(text):
            return [term for term, pattern in patterns if pattern.search(text or "")]
        return match, terms

    def _official_path(self, doc_id, block):
        _chapter, path = self.chapter_path(doc_id, block)
        if path:
            return path
        return [self.docs[doc_id].get("work") or "", self.docs[doc_id].get("title") or ""]

    def _official_snippet(self, text, match):
        text = str(text or "")
        if not text or match is None:
            return text
        start, end = select_block_snippet_span(
            text, [(0, len(text))], match.start(), match.end(),
            target_len=SNIPPET_PARAGRAPH_TARGET - 2,
            hard_max=SNIPPET_PARAGRAPH_HARD - 2,
        )
        snippet = text[start:end].strip()
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(text) else ""
        return prefix + snippet + suffix

    def _attach_official_preview(self, result, q, scope="", multi=False):
        view = self.official_view(q, offset=0, limit=5, scope=scope, multi=multi)
        result["official_items"] = view["items"]
        result["official_total"] = view["total"]
        result["official_counts"] = view["counts"]
        result["official_has_more"] = view["has_more"]
        return result

    def official_view(self, q, offset=0, limit=20, scope="", multi=False):
        """Return typed QA/pointer/supplement results for the dedicated section."""
        requested = (q or "").strip()
        matcher, highlight = self._official_matcher(requested, scope, multi=multi)
        allow = self.scope_set(scope)
        items = []
        covered = set()

        for raw in self.official_qa:
            doc_id = int(raw["doc"])
            if allow is not None and doc_id not in allow:
                continue
            text = "%s\n%s" % (raw.get("q") or "", raw.get("a") or "")
            labels = matcher(text)
            if not labels:
                continue
            start = int(raw.get("start") or 0)
            end = max(start, int(raw.get("end") or start))
            covered.update((doc_id, order) for order in range(start, end + 1))
            source = self.source(doc_id)
            answer = raw.get("a") or ""
            labels_pattern = occurrence_pattern(labels)
            a_excerpt, a_truncated = build_answer_excerpt(answer, labels_pattern)
            items.append({
                "kind": "qa", "doc": doc_id, "block": start,
                "q": raw.get("q") or "", "a": answer,
                "a_excerpt": a_excerpt, "a_truncated": a_truncated,
                "matched_terms": labels, "source": source,
                "path": self._official_path(doc_id, start),
                "jump": {"kind": "viewer", "doc": doc_id, "start": None,
                         "end": None, "chapter": None,
                         "work": source.get("work") or ""},
                "_order": self.official_doc_order.get(doc_id, 10 ** 9),
                "_start": start,
            })

        for primary in self.official_primary:
            doc_id = int(primary["doc"])
            if allow is not None and doc_id not in allow:
                continue
            source = self.source(doc_id)
            rows = sorted(self.story_blocks.get(doc_id, {}).items())
            for order, text in rows:
                if (doc_id, order) in covered:
                    continue
                labels = matcher(text)
                if not labels:
                    continue
                term_pattern = occurrence_pattern(labels)
                found = term_pattern.search(text)
                if not found:
                    continue
                snippet = self._official_snippet(text, found)
                if not official_snippet_is_long_enough(snippet):
                    continue
                items.append({
                    "kind": "pointer", "doc": doc_id, "block": order,
                    "snippet": snippet,
                    "matched_terms": labels, "source": source,
                    "path": self._official_path(doc_id, order),
                    "jump": {"kind": "viewer", "doc": doc_id, "start": None,
                             "end": None, "chapter": None,
                             "work": source.get("work") or ""},
                    "_order": int(primary.get("order") or 0),
                    "_start": int(order),
                })

        for raw in self.official_supplements:
            doc_id = int(raw["doc"])
            if allow is not None and doc_id not in allow:
                continue
            text = "%s\n%s" % (raw.get("q") or "", raw.get("a") or "")
            labels = matcher(text)
            if not labels:
                continue
            term_pattern = occurrence_pattern(labels)
            found = term_pattern.search(text)
            if not found:
                continue
            snippet = self._official_snippet(text, found)
            if not official_snippet_is_long_enough(snippet):
                continue
            source = self.source(doc_id)
            items.append({
                "kind": "supplement", "doc": doc_id, "block": 0,
                "snippet": snippet,
                "matched_terms": labels, "source": source,
                "path": [source.get("work") or "", "访谈补充", source.get("title") or ""],
                "jump": {"kind": "viewer", "doc": doc_id, "start": None,
                         "end": None, "chapter": None,
                         "work": source.get("work") or ""},
                "_order": 10 ** 9,
                "_start": 0,
            })

        qa_items = [item for item in items if item["kind"] == "qa"]
        pointer_items = [item for item in items if item["kind"] == "pointer"]
        supplement_items = [item for item in items if item["kind"] == "supplement"]
        qa_items.sort(key=lambda item: (item["_order"], item["_start"], item["doc"]))
        pointer_items.sort(key=lambda item: (item["_order"], item["_start"], item["doc"]))
        ordered = qa_items + pointer_items + supplement_items
        for item in ordered:
            item.pop("_order", None)
            item.pop("_start", None)

        total = len(ordered)
        page = ordered[max(offset, 0):max(offset, 0) + max(limit, 1)]
        counts = {"qa": len(qa_items), "pointer": len(pointer_items), "supplement": len(supplement_items)}
        return {
            "q": requested, "scope": scope, "scope_name": self.scope_name(scope),
            "highlight_terms": highlight, "total": total, "counts": counts,
            "offset": max(offset, 0), "limit": max(limit, 1),
            "has_more": max(offset, 0) + len(page) < total,
            "items": page,
        }

    def search(self, q, limit=60, scope=""):
        requested = q.strip()
        if self.multi_term_groups(requested):
            return self.search_multi(requested, limit, scope)
        _requested, q, hit, normalization, occ_terms = self.resolve_query(requested)
        alias = None
        alias_note = alias_note_lookup(requested)
        if hit:
            targets = hit[1] if isinstance(hit[1], list) else [hit[1]]
            alias = {"from": hit[0], "to": targets, "ambiguous": len(targets) > 1}
        allow = self.scope_set(scope)
        result = {"q": q, "requested_q": requested, "scope": scope,
                  "scope_name": self.scope_name(scope), "alias": alias,
                  "alias_note": alias_note, "normalization": normalization,
                  "highlight_terms": occ_terms,
                  "match_mode": "exact", "scoped": allow is not None,
                  "definitions": [], "interviews": [], "qa": [], "related": [],
                  "official_items": [], "official_total": 0,
                  "official_counts": {"qa": 0, "pointer": 0, "supplement": 0},
                  "official_has_more": False,
                  "occurrences": [], "total": 0, "by_work": [], "docs": 0,
                  "truncated": False}
        if not q:
            return result
        self._attach_official_preview(result, q, scope, multi=False)
        latin = is_latin_query(q)
        pat_text = query_pattern(q, latin, "text")

        if alias and alias.get("ambiguous"):
            cards, canonical = [], alias["to"][0] if alias["to"] else q
            for target in alias["to"]:
                target_cards, _ = self.ordered_definitions(target, allow)
                cards.extend(c for c in target_cards if c["match"] == "exact")
        else:
            cards, canonical = self.ordered_definitions(q, allow)

        data = self.scan(q, terms=occ_terms)
        items = data["items"] if allow is None else [i for i in data["items"] if i["doc"] in allow]
        fallback_parts = self._fallback_parts(q)
        if not cards:
            card_groups = {c.get("group_id") for c in cards}
            fallback_cards = []
            for part in fallback_parts:
                part_cards, _ = self.ordered_definitions(part, allow)
                for c in part_cards:
                    if c.get("match") == "exact" and c.get("group_id") not in card_groups:
                        fallback_cards.append(c)
                        card_groups.add(c.get("group_id"))
                if fallback_cards:
                    break
            cards.extend(fallback_cards)
        if not items:
            fallback_items, item_keys = [], set()
            for part in fallback_parts:
                part_data = self.scan(part)
                part_items = part_data["items"] if allow is None else [
                    i for i in part_data["items"] if i["doc"] in allow]
                for i in part_items:
                    key = (i["doc"], i.get("block"), i.get("pos"))
                    if key not in item_keys:
                        item_keys.add(key)
                        fallback_items.append(i)
                if fallback_items:
                    break
            if fallback_items:
                data = {"items": fallback_items, "total": sum(i.get("n", 1) for i in fallback_items),
                        "truncated": False}
                items = fallback_items

        result["defs_total"] = len(cards)
        shown, per_kind = [], {}
        for c in cards:
            k = c["match"]
            if k != "exact":
                cap = CARD_BODY_MAX if k == "body" else CARD_CONTAINS_MAX
                if per_kind.get(k, 0) >= cap:
                    continue
            per_kind[k] = per_kind.get(k, 0) + 1
            shown.append(c)
            if len(shown) >= CARD_TOTAL_MAX:
                break
        result["definitions"] = shown

        for item in self.interviews:
            if pat_text.search(item.get("body") or "") or pat_text.search(item.get("term") or ""):
                result["interviews"].append({
                    "term": item.get("term") or "",
                    "entry_type": item.get("entry_type") or "interview",
                    "body": item.get("body") or "",
                    "jp_body": item.get("jp_body"),
                    "source": self.source(item["doc"]),
                    "source_locator": item.get("source_locator") or {},
                    "source_refs": item.get("source_refs") or [],
                })
            if len(result["interviews"]) >= 8:
                break

        pat_text = query_pattern(q, is_latin_query(q), "text")
        for item in self.qa:
            if pat_text.search(item["q"]) and (allow is None or item["doc"] in allow):
                result["qa"].append({"q": item["q"], "a": item["a"],
                                     "truncated": item.get("truncated", False),
                                     "source": self.source(item["doc"])})
            if len(result["qa"]) >= 8:
                break
        result["related"] = [[t, c] for t, c in self.related.get(canonical, [])][:12]
        result["classifications"] = self.term_classifications(canonical)

        work_hits, work_segs, work_docs = {}, {}, {}
        for it in items:
            w = it["work"]
            work_hits[w] = work_hits.get(w, 0) + it["n"]
            work_segs[w] = work_segs.get(w, 0) + 1
            work_docs.setdefault(w, set()).add(it["doc"])
        result["total"] = sum(work_hits.values())
        result["raw_total"] = data["total"]
        result["docs"] = len({i["doc"] for i in items})
        result["by_work"] = sorted(work_hits.items(), key=lambda x: work_rank(x[0]))
        result["by_work_segs"] = work_segs
        result["by_work_docs"] = {w: len(v) for w, v in work_docs.items()}
        result["truncated"] = data["truncated"]
        if normalization:
            result["match_mode"] = "normalized"
        if not data["items"] and result["definitions"]:
            result["match_mode"] = "subphrase"

        by_work = {}
        for it in items:
            by_work.setdefault(it["work"], []).append(it)
        works = sorted(by_work, key=work_rank)
        queue = {}
        for w in works:
            by_kind = {}
            for it in by_work[w]:
                k = KIND_STORY_RANK.get(self.docs[it["doc"]]["kind"], 4)
                by_kind.setdefault(k, []).append(it)
            cand = []
            for k in sorted(by_kind):
                firsts, rest, seen_doc = [], [], set()
                for it in by_kind[k]:
                    if it["doc"] in seen_doc:
                        rest.append(it)
                    else:
                        seen_doc.add(it["doc"])
                        firsts.append(it)
                cand.extend(firsts + rest)
            queue[w] = cand
        picked = []
        for rnd in range(1, 9):
            if len(picked) >= limit:
                break
            for w in works:
                cand = queue[w]
                if len(cand) < rnd:
                    continue
                picked.append(cand[rnd - 1])
                if len(picked) >= limit:
                    break
        result["occurrences"] = [self._occ(it, q, terms=occ_terms) for it in picked]
        return result

    def _build_chapter_shingles(self):
        """索引直接挂载章节的 40 字 shingle，并严格按作品隔离。"""
        self.chapter_shingle_by_work = {}
        for doc_id, rows in self.chapters_by_doc.items():
            work = self.docs[doc_id].get("work")
            for order, s0, length in self.doc_index.get(doc_id, []):
                flat = re.sub(r"\s+", "", self.corpus[s0:s0 + length])
                if len(flat) < 40:
                    continue
                _chapter, path = self.chapter_path(doc_id, order, direct_only=True)
                if not path:
                    continue
                bucket = self.chapter_shingle_by_work.setdefault(work, {})
                for k in range(0, len(flat) - 40, 160):
                    bucket.setdefault(flat[k:k + 40], list(path))

    def chapter_path(self, doc_id, block, direct_only=False):
        """返回 (展示章节串, 路径数组)。作品 key 是硬边界，绝不跨作品回退。"""
        doc = self.docs[doc_id]
        work = doc.get("work")
        rows = self.chapters_by_doc.get(doc_id)
        if rows:
            hit = None
            for i, r in enumerate(rows):
                nxt = rows[i + 1]["start"] if i + 1 < len(rows) else None
                end = r["end"] if r["end"] is not None else nxt
                if block >= r["start"] and (end is None or block < end):
                    hit = r
                    break
            if hit is None:
                hit = rows[0] if block < rows[0]["start"] else rows[-1]
            if hit.get("work") == work or self.story_doc_owner.get(doc_id) == hit.get("work"):
                parts = []
                path_work = hit.get("work")
                if path_work in STORY_SYNTHETIC_WORKS and work not in STORY_SYNTHETIC_WORKS:
                    path_work = work
                for value in (WORK_LABEL.get(path_work, path_work), hit.get("route"), hit.get("group"), hit.get("title")):
                    if value and value not in parts:
                        parts.append(value)
                return " › ".join(parts), parts
        if direct_only:
            return None, []
        bucket = getattr(self, "chapter_shingle_by_work", {}).get(work, {})
        if not bucket:
            return None, []
        for order, s0, length in self.doc_index.get(doc_id, []):
            if order != block:
                continue
            flat = re.sub(r"\s+", "", self.corpus[s0:s0 + length])
            for k in range(0, max(1, len(flat) - 40), 20):
                path = bucket.get(flat[k:k + 40])
                if path:
                    return " › ".join(path), list(path)
        return None, []

    def chapter_of(self, doc_id, block, direct_only=False):
        """兼容旧调用：只返回章节展示串。"""
        label, _path = self.chapter_path(doc_id, block, direct_only=direct_only)
        return label

    def occurrence_location(self, doc_id, block):
        rows = self._occurrence_by_doc.get(doc_id, [])
        starts = [row["start"] for row in rows]
        index = bisect.bisect_right(starts, block) - 1
        if index < 0:
            return None
        row = rows[index]
        if row["start"] <= block < row["end"]:
            return row
        return None

    def _occ(self, it, q, terms=None):
        location = self.occurrence_location(it["doc"], it["block"])
        if location:
            path = list(location.get("path") or [])
            chapter = " › ".join(path)
            jump = dict(location.get("jump") or {})
        else:
            chapter, path = self.chapter_path(it["doc"], it["block"])
            jump = {"kind": "viewer", "doc": it["doc"], "start": None, "end": None,
                    "chapter": None}
        return {"snippet": self.snippet(it["pos"], q, terms=terms), "source": self.source(it["doc"]),
                "doc": it["doc"], "block": it["block"], "work": it["work"],
                "chapter": chapter, "path": path, "jump": jump}

    def list_view(self, q, work, offset=0, limit=50, scope="", terms=None):
        requested, canonical, _hit, _normalization, resolved_terms = self.resolve_query(q)
        occ_terms = parse_terms_param(json.dumps(terms or [], ensure_ascii=False)) or resolved_terms
        data = self.scan(canonical, terms=occ_terms)
        allow = self.scope_set(scope)
        scoped = data["items"] if allow is None else [i for i in data["items"] if i["doc"] in allow]
        items = [i for i in scoped if i["work"] == work] if work else scoped
        if work:      # 同一作品内：剧情文本 > 设定集 > 访谈 > 广播剧 > 其他
            items = sorted(items, key=lambda i: KIND_STORY_RANK.get(self.docs[i["doc"]]["kind"], 4))
        page = items[offset:offset + limit]
        work_hits, work_segs, work_docs = {}, {}, {}
        for i in scoped:
            w = i["work"]
            work_hits[w] = work_hits.get(w, 0) + i["n"]
            work_segs[w] = work_segs.get(w, 0) + 1
            work_docs.setdefault(w, set()).add(i["doc"])
        return {
            "q": canonical, "requested_q": requested, "work": work, "offset": offset, "scope": scope,
            "scope_name": self.scope_name(scope),
            "highlight_terms": occ_terms,
            "total": work_hits.get(work, 0) if work else sum(work_hits.values()),
            "all_total": data["hits"],
            "passages": len(items),
            "docs": len(work_docs.get(work, set())) if work else len(set().union(*work_docs.values())
                                                                      if work_docs else set()),
            "truncated": data["truncated"],
            "works": [[w, work_hits[w], work_segs.get(w, 0), len(work_docs.get(w, set()))]
                      for w, _ in sorted(work_hits.items(), key=lambda x: -x[1])],
            "items": [dict(self._occ(i, canonical, terms=occ_terms), n=i["n"]) for i in page],
            "has_more": offset + limit < len(items),
        }

    def doc_view(self, doc_id, block_order, q, chap_start=None, chap_end=None, chapter_key=None):
        if doc_id in self.story_blocks:
            zh = [{"o": order, "t": text, "lang": "zh"}
                  for order, text in sorted(self.story_blocks[doc_id].items())]
        else:
            zh = [{"o": order, "t": strip_body_links(self.corpus[start:start + length]), "lang": "zh"}
                  for order, start, length in self.doc_index.get(doc_id, [])]
        ja = [{"o": order, "t": text, "lang": "ja"}
              for order, text in self.jp_index.get(doc_id, {}).items()]
        if self.story_doc_owner.get(doc_id) == "访谈":
            allowed_orders = set(self.story_blocks.get(doc_id, {}))
            ja = [b for b in ja if b["o"] in allowed_orders]
        if chap_start is not None:
            hi = chap_end if chap_end is not None else 10 ** 9
            zh = [b for b in zh if chap_start <= b["o"] < hi or b["o"] == chap_start]
            ja = [b for b in ja if chap_start <= b["o"] < hi]
        blocks = sorted(zh + ja, key=lambda b: b["o"])
        out = {"doc": self.docs[doc_id], "blocks": blocks, "target": block_order, "q": q,
               "untranslated": len(ja),
               "chars": sum(len(b["t"]) for b in blocks)}
        if chap_start is not None:
            info = self.story_chapter_by_key.get(chapter_key) if chapter_key else None
            if info is None:
                info = self.story_chapter_at.get((doc_id, chap_start))
            if info:
                work, route, i = info
                chs = route["chapters"]
                out["story"] = {
                    "work": work, "work_name": WORK_LABEL.get(work, work),
                    "route": route["name"], "group": chs[i].get("group", ""),
                    "prereq": bool(chs[i].get("prereq", False)),
                    "main_index": chs[i].get("main_index"),
                    "index": i + 1, "total": len(chs),
                    "title": chs[i]["title"],
                    "prev": {"doc": chs[i - 1]["doc"], "start": chs[i - 1]["start"],
                             "title": chs[i - 1]["title"], "key": chs[i - 1].get("key")} if i > 0 else None,
                    "next": {"doc": chs[i + 1]["doc"], "start": chs[i + 1]["start"],
                             "title": chs[i + 1]["title"], "key": chs[i + 1].get("key")} if i + 1 < len(chs) else None}
        return out

STORE = None
