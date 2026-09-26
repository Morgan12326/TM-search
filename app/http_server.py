# -*- coding: utf-8 -*-
"""HTTP routing and response handling."""
from __future__ import annotations

try:
    from . import store as runtime_store
    from .core import *
except ImportError:  # Direct execution compatibility.
    import store as runtime_store
    from core import *

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False), MIME[".json"])

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        q = (query.get("q") or [""])[0]
        try:
            if path == "/api/suggest":
                return self._json({"items": runtime_store.STORE.suggest(q, 10)})
            if path == "/api/search":
                scope = (query.get("scope") or [""])[0]
                return self._json(runtime_store.STORE.search(q, 60, scope))
            if path == "/api/doc":
                doc_id = int((query.get("id") or ["-1"])[0])
                block = int((query.get("block") or ["0"])[0])
                cs = query.get("start") or [None]
                ce = query.get("end") or [None]
                chap_start = int(cs[0]) if cs[0] not in (None, "") else None
                chap_end = int(ce[0]) if ce[0] not in (None, "") else None
                chapter_key = (query.get("chapter") or [None])[0]
                if not 0 <= doc_id < len(runtime_store.STORE.docs):
                    return self._send(404, "文档不存在", "text/plain; charset=utf-8")
                return self._json(runtime_store.STORE.doc_view(doc_id, block, q, chap_start, chap_end, chapter_key))
            if path == "/api/list":
                work = (query.get("work") or [""])[0]
                scope = (query.get("scope") or [""])[0]
                offset = int((query.get("offset") or ["0"])[0])
                limit = min(int((query.get("limit") or ["50"])[0]), 200)
                if (query.get("multi") or ["0"])[0] == "1":
                    return self._json(runtime_store.STORE.list_view_multi(q, work, offset, limit, scope))
                terms = parse_terms_param((query.get("terms") or [""])[0])
                return self._json(runtime_store.STORE.list_view(q, work, offset, limit, scope, terms))
            if path == "/api/official":
                scope = (query.get("scope") or [""])[0]
                offset = max(int((query.get("offset") or ["0"])[0]), 0)
                limit = min(max(int((query.get("limit") or ["20"])[0]), 1), 100)
                multi = (query.get("multi") or ["0"])[0] == "1"
                return self._json(runtime_store.STORE.official_view(q, offset, limit, scope, multi=multi))
            if path == "/api/defs":
                scope = (query.get("scope") or [""])[0]
                offset = max(int((query.get("offset") or ["0"])[0]), 0)
                limit = min(max(int((query.get("limit") or ["20"])[0]), 1), 100)
                if (query.get("multi") or ["0"])[0] == "1":
                    return self._json(runtime_store.STORE.definitions_multi(q, scope, offset, limit))
                hit = alias_lookup(q)
                if hit and len(hit[1]) == 1:
                    q = hit[1][0]
                    cards, _canonical = runtime_store.STORE.ordered_definitions(q, runtime_store.STORE.scope_set(scope))
                elif hit:
                    cards = []
                    for target in hit[1]:
                        target_cards, _unused = runtime_store.STORE.ordered_definitions(target, runtime_store.STORE.scope_set(scope))
                        cards.extend(c for c in target_cards if c["match"] == "exact")
                else:
                    cards, _canonical = runtime_store.STORE.ordered_definitions(q, runtime_store.STORE.scope_set(scope))
                return self._json({"q": q, "scope": scope, "scope_name": runtime_store.STORE.scope_name(scope),
                                   "total": len(cards), "offset": offset, "limit": limit,
                                   "has_more": offset + limit < len(cards),
                                   "items": cards[offset:offset + limit]})
            if path == "/api/aliases":
                return self._json(ALIAS)
            if path == "/api/alias-data":
                return self._json({"targets": ALIAS_TARGETS, "notes": ALIAS_NOTES})
            if path == "/api/taxonomy":
                return self._json({"tops": runtime_store.STORE.taxonomy})
            if path == "/api/wiki/tree":
                return self._json({"tree": runtime_store.STORE.wiki_tree})
            if path == "/api/story/tree":
                tree = runtime_store.STORE.story_tree()
                return self._json({"tree": tree, "jp_only": runtime_store.STORE.story_jp_only,
                                   "chapters": sum(t["chapters"] for t in tree)})
            if path == "/api/story/leaf":
                key = (query.get("key") or [""])[0]
                return self._json(runtime_store.STORE.story_leaf(key))
            if path == "/api/story/node":
                key = (query.get("key") or ["work:FGO"])[0]
                return self._json(runtime_store.STORE.story_node(key))
            if path == "/api/fgo/chapter":
                wid = int((query.get("id") or ["0"])[0])
                data = runtime_store.STORE.fgo_chapter(wid)
                if not data:
                    return self._send(404, "章节不存在", "text/plain; charset=utf-8")
                return self._json(data)
            if path == "/api/official/chapter":
                work = (query.get("work") or ["FGO"])[0]
                cid = int((query.get("id") or ["0"])[0])
                data = runtime_store.STORE.official_chapter(work, cid)
                if not data:
                    return self._send(404, "章节不存在", "text/plain; charset=utf-8")
                return self._json(data)
            if path == "/api/wiki/leaf":
                key = (query.get("key") or [""])[0]
                # 作品层（work:）允许把子分类聚合后再返回，交给 wiki_leaf 判定
                if key not in runtime_store.STORE.wiki_leaf_terms and not key.startswith("work:"):
                    return self._json({"key": key, "name": "（无此类目）", "total": 0,
                                       "items": [], "has_more": False, "categories": []})
                offset = int((query.get("offset") or ["0"])[0])
                limit = min(int((query.get("limit") or ["100"])[0]), 500)
                filt = (query.get("filter") or [""])[0].strip()
                cat = (query.get("cat") or [""])[0].strip()
                return self._json(runtime_store.STORE.wiki_leaf(key, offset, limit, filt, cat))
            if path == "/api/status":
                return self._json({"build": SERVER_BUILD,
                                   "corpus": len(runtime_store.STORE.corpus), "docs": len(runtime_store.STORE.docs),
                                   "entries": len(runtime_store.STORE.entries), "qa": len(runtime_store.STORE.qa),
                                   "interviews": len(runtime_store.STORE.interviews),
                                   "official_qa": len(runtime_store.STORE.official_qa),
                                   "official_supplements": len(runtime_store.STORE.official_supplements),
                                   "vocab": len(runtime_store.STORE.vocab), "taxonomy": runtime_store.STORE.taxonomy})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, f"内部错误：{exc}", "text/plain; charset=utf-8")
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = os.path.normpath(os.path.join(WEB, rel))
        if not target.startswith(WEB) or not os.path.isfile(target):
            return self._send(404, "未找到", "text/plain; charset=utf-8")
        ext = os.path.splitext(target)[1]
        self._send(200, read_bytes(target), MIME.get(ext, "application/octet-stream"))
