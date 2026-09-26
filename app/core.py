# -*- coding: utf-8 -*-
"""型月搜索 · v1.1.7 搜索服务。

启动后在本机 127.0.0.1 提供搜索接口，只在本地运行，不联网。
"""
import bisect
import difflib
import heapq
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import unicodedata
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from .language_blocks import load_recovered_blocks
    from .multi_term import MultiTermEngine
    from .official_interviews import build_answer_excerpt
except ImportError:  # Direct execution: python app/server.py
    from language_blocks import load_recovered_blocks
    from multi_term import MultiTermEngine
    from official_interviews import build_answer_excerpt

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
    RESOURCE = getattr(sys, "_MEIPASS", BASE)
    DATA = os.path.join(RESOURCE, "data")
    WEB = os.path.join(RESOURCE, "app", "web")
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA = os.path.join(BASE, "data")
    WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PORT = int(os.environ.get("TM_DICT_PORT", "8765"))
SERVER_BUILD = "2026-09-26-fgo-story-live-v2"


def read_json(path, default=None):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}

KIND_ORDER = {"转载辞典": -1, "用语辞典": 0, "设定集": 1, "官方网页": 2, "问答": 3, "访谈": 4, "二手资料": 5}

# 占位式条目（语料里指向别处的说明、无实质内容）排在定义列表末尾
JUNK_HINT = ("与月姬正篇无关", "详细请参照", "参照用语", "见下文", "参见用语")

# 二级分类：只在需要细分的作品下生效（按文件路径判定）
SUBRULES = {
    "月姬": [("Melty", "Melty Blood"), ("MELTY", "Melty Blood"), ("\\MB\\", "Melty Blood"),
             ("MBAC", "Melty Blood"), ("MBAA", "Melty Blood"), ("MBR", "Melty Blood"),
             ("歌月十夜", "歌月十夜"), ("月姬plus", "月姬 PLUS"),
             ("读本", "月姬读本"), ("読本", "月姬读本")],
    "FE": [("CCC", "Fate/EXTRA CCC"), ("extella", "Fate/EXTRA Extella"),
           ("FEXM", "Fate/EXTRA Extella")],
}
DEFAULT_SUB = {"月姬": "月姬本篇", "FE": "Fate/EXTRA"}

# 百科叶子合并/显示规则：原始叶子 -> 注入目标叶子。
WIKI_LEAF_ALIASES = {
    "sub:FE|Fate/EXTRA Extella": "work:FEX",
}
# 同名词条的主定义来源优先级：数值越小越优先。
WIKI_LEAF_PRIORITY = {
    "sub:FE|Fate/EXTRA Extella": 0,
}
WIKI_LEAF_KIND_OVERRIDES = {
    "work:FEX": ("FEX", None),
}
WIKI_LEAF_LABELS = {
    "sub:FE|Fate/EXTRA": "Fate/EXTRA 系列",
}

WORK_LABEL = {
    "FGO": "Fate/Grand Order", "FSN": "Fate/stay night", "FHA": "Fate/hollow ataraxia",
    "FZ": "Fate/Zero", "FA": "Fate/Apocrypha", "FE": "Fate/EXTRA 系列",
    "FEX": "Fate/EXTELLA", "FEXL": "Fate/EXTELLA LINK",
    "FE_CCC": "Fate/Extra CCC",
    "FSF": "Fate/strange fake", "FSR": "Fate/Samurai Remnant",
    "FP": "Fate/Prototype 系列",
    "FKL": "Fate/kaleid liner・Koha Ace", "二世事件簿": "君主·埃尔梅罗二世事件簿",
    "月姬": "月姬", "MB": "MB", "魔法使之夜": "魔法使之夜", "空之境界": "空之境界",
    "魔法使之箱": "魔法使之箱", "月姬R": "月姬R（蓝月之玻）",
    "DDD": "DDD", "FireGirl": "Fire Girl", "其他": "未归类资料",
    "月之珊瑚": "月之珊瑚", "2015年的时钟塔": "2015年的时钟塔",
    "广播剧": "广播剧", "访谈": "访谈", "FUC": "FUC",
}

TAXONOMY = [("fate", "Fate 系列", ["FGO", "FSN", "FHA", "FZ", "FA", "FE", "FEX", "FEXL", "FSF", "FSR", "FP",
                                   "FKL", "二世事件簿"]),
            ("tsukihime", "月姬", ["月姬", "月姬R"]),
            ("mahoyo", "魔法使之夜", ["魔法使之夜"]),
            ("mahotsukai", "魔法使之箱", ["魔法使之箱"]),
            ("kara", "空之境界", ["空之境界"]),
            ("other", "其他作品与杂项", ["DDD", "FireGirl", "其他"])]

# 剧情大全使用独立的作品节点：搜索/百科仍保留“未归类资料”。
STORY_SYNTHETIC_WORKS = {"MB", "FE_CCC", "广播剧", "访谈", "FUC", "月之珊瑚", "2015年的时钟塔"}

STORY_TAXONOMY = [
    ("fate", "Fate 系列", ["FGO", "FSN", "FHA", "FZ", "FA", "FE_CCC", "FEX", "FEXL", "FSF", "FSR", "FP",
                          "FKL", "二世事件簿"]),
    ("tsukihime", "月姬", ["月姬", "MB", "月姬R"]),
    ("mahoyo", "魔法使之夜", ["魔法使之夜"]),
    ("kara", "空之境界", ["空之境界"]),
    ("other", "其他作品与杂项", ["DDD", "魔法使之箱", "月之珊瑚", "2015年的时钟塔", "广播剧", "访谈", "FUC", "FireGirl"]),
]

# 出现位置的作品顺序：直接沿用剧情大全目录（Fate 系列在上，「其他」永远最末）
_WORK_SEQ = [w for _tid, _tname, _ws in TAXONOMY for w in _ws if w != "其他"]
WORK_ORDER = {w: i for i, w in enumerate(_WORK_SEQ)}
WORK_ORDER["其他"] = len(_WORK_SEQ) + 1


def work_rank(w):
    """作品排序键：TAXONOMY 顺序；未收录的排在「其他」之前。"""
    return WORK_ORDER.get(w, len(_WORK_SEQ) + 0.5)


# 检索结果的数量上限
CN_EXPAND_MAX = 8        # 中文：含该词的词条超过这个数，就不再展开「词解正文含该词」
CARD_TOTAL_MAX = 26      # 词解卡总数上限（= 精确不限 + 正文 6 + 含词 10，各桶独立封顶）
CARD_BODY_MAX = 6        # 「正文含该词」最多几张
CARD_CONTAINS_MAX = 10   # 「词条名含该词」最多几张（仅中文）
# 用户指定固定顺序的相关词解。
QUERY_PINS = {
    "人理烧却": ("盖提亚",),
}
# 常用短名在“词条名包含”桶中的确定首选；不改变精确匹配和同类词解规则。
QUERY_PRIMARY_GROUPS = {
    "士郎": "term:卫宫士郎",
    "樱": "term:间桐樱",
    "凛": "term:远坂凛",
    "言峰": "term:言峰绮礼",
    "志贵": "term:远野志贵",
}

# 指定词条必须使用某文档的定义作为主卡；值按 group_id 限定，避免同名条目互相影响。
DEFINITION_FORCED_PRIMARY = {
    "term:空想具现化": 825,
    "term:直死的魔眼": 828,
}
# 指定查询下，把对应词条组整体提前。
DEFINITION_FORCED_FIRST_GROUP = {
    "直死之魔眼": "term:直死的魔眼",
}
# 仅改变展示正文，不修改原始数据。
DEFINITION_BODY_PREFIXES = {
    ("死徒二十七祖", 729): "【旧设】",
    ("死徒二十七祖", 818): "【旧设】",
    ("死徒二十七祖", 828): "【旧设】",
}
# 定向显示替换：键为（词条名、来源文档），避免污染其他来源的同一词条。
DEFINITION_BODY_REPLACEMENTS = {
    ("红宝石之星/蓝宝石之星", 641): (("红白事", "红宝石"),),
}
# 群组级显示名覆盖：只改变卡片标题，不改变分组键、原始词条名或正文。
DEFINITION_GROUP_TERM_OVERRIDES = {
    "term:直死的魔眼": "直死之魔眼",
}


# 出现位置：同一作品内的资料类型优先级（剧情文本 > 设定集 > 访谈 > 广播剧 > 其他）
KIND_STORY_RANK = {"原作": 0, "设定集": 1, "访谈": 2, "广播剧": 3}

# Fate 系词条的跨组预排序分组；组内最终顺序由同类词解规则决定。
MAT_GROUP = {"FSN": 0, "FE": 1, "FEX": 2, "FEXL": 2}
FATE_WORKS = set(TAXONOMY[0][2])

# 同类词解卡：正常杯战作品固定顺位；FE 系作为特殊版本。
NORMAL_GRAIL_ORDER = {"FSN": 0, "FZ": 1, "FA": 2, "FSF": 3}
SPECIAL_GRAIL_ORDER = {"FE": 0, "FE_CCC": 0, "FEX": 1, "FEXL": 2}
DEFINITION_COVERAGE_MIN_CHARS = 40
DEFINITION_COVERAGE_MIN_RATIO = 0.70
DEFINITION_COVERAGE_LENGTH_RATIO = 1.35
DEFINITION_DUPLICATE_MIN_RATIO = 0.70
DEFINITION_DUPLICATE_LENGTH_RATIO = 0.85

RE_CJK = re.compile(r"[\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\uff66-\\uff9f]")

BODY_LINK_RE = re.compile(r"(?i)(?:https?://|www\.)[^\s<>\"“”]+")
MD_BODY_LINK_RE = re.compile(r"\[([^\]]{0,200})\]\((?:(?:https?://|www\.)[^)]+)\)", re.I)
HTML_BODY_LINK_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S)
HTML_TAG_RE = re.compile(r"<[^>]+>")
DEFINITION_CATEGORY_RE = re.compile(r"\[(?:Category|分类)[^\]]*\]", re.I)


def strip_body_links(text):
    text = HTML_BODY_LINK_RE.sub(r"\1", str(text or ""))
    text = MD_BODY_LINK_RE.sub(r"\1", text)
    text = BODY_LINK_RE.sub("", text)
    out = []
    for line in text.splitlines():
        s = line.strip(" \t;；,，、:：-—–·")
        if not s:
            continue
        if s in ("官网", "来源", "原文", "网址", "链接", "离线版", "其他版本"):
            continue
        out.append(line.strip())
    return "\\n".join(out)


SEARCH_NORMALIZE = (
    ("以太", "乙太"),
    ("Ⅱ", "II"),
    ("Ⅲ", "III"),
    ("Ⅳ", "IV"),
    ("Ⅴ", "V"),
    ("Ⅵ", "VI"),
    ("Ⅶ", "VII"),
    ("Ⅷ", "VIII"),
)


def normalize_search_text(q):
    """统一常见异体字、全角字符和用户查询标点。"""
    notes = []
    out = unicodedata.normalize("NFKC", q or "")
    for old, new in SEARCH_NORMALIZE:
        if old in out and old != new:
            out = out.replace(old, new)
            notes.append("%s→%s" % (old, new))
    return out, notes


def replace_query_aliases(q):
    """仅在整段查询与别名完全一致时替换，避免中文别名污染更长词条。"""
    hit = alias_lookup(q)
    if not hit:
        return q, []
    nick, raw = hit
    targets = raw if isinstance(raw, list) else [raw]
    if len(targets) != 1 or not targets[0] or targets[0] == q:
        return q, []
    return targets[0], ["%s→%s" % (nick, targets[0])]

def normalize_query(q):
    q, notes1 = normalize_search_text(q)
    q, notes2 = replace_query_aliases(q)
    return q, notes1 + notes2


def term_key(text):
    text = unicodedata.normalize("NFKC", text or "").strip()
    text = text.replace(" ", "").replace("　", "")
    return ALIAS.get(text, text)


def is_latin_query(q):
    """查询串不含中日文、且含至少一个拉丁字母 → 按英文（词首）逻辑检索。"""
    return bool(re.search(r"[A-Za-z]", q)) and not RE_CJK.search(q)


def query_pattern(q, latin=None, kind="name"):
    """检索正则（一律忽略大小写）：
    · 中文查询＝子串匹配；
    · 英文查询：kind="name"（词条名）＝词首匹配，kind="text"（正文/语料）＝整词匹配。
    """
    if latin is None:
        latin = is_latin_query(q)
    body = re.escape(q)
    if latin:
        if kind == "name":
            body = r"(?<![A-Za-z0-9])" + body + r"[A-Za-z0-9]*"
        else:
            body = r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])"
    return re.compile(body, re.I)


OCC_PUNCT = "·・‧．."
OCCURRENCE_SHORT_ALIASES = {"白姬", "雪儿"}


def occurrence_term_pattern(term):
    term = (term or "").strip()
    if not term:
        return ""
    out = []
    for ch in term:
        if ch in OCC_PUNCT or ch.isspace():
            out.append(r"[·・‧．.\s]*")
        else:
            out.append(re.escape(ch))
    pattern = "".join(out)
    if re.search(r"[A-Za-z]", term) and not RE_CJK.search(term):
        pattern = r"(?<![A-Za-z0-9])" + pattern + r"(?![A-Za-z0-9])"
    return pattern


def occurrence_pattern(terms):
    ordered, seen = [], set()
    for term in terms or []:
        term = (term or "").strip()
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        ordered.append(term)
    ordered.sort(key=lambda x: (-len(x), x))
    return re.compile("|".join("(?:%s)" % occurrence_term_pattern(t) for t in ordered), re.I)


def parse_terms_param(raw, limit=32):
    """解析 /api/list 的 terms 参数，返回稳定、去重后的词集。"""
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    out, seen = [], set()
    for value in values:
        term = str(value or "").strip()
        if not term or len(term) > 80:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= limit:
            break
    return out


CAT_RANK = {"人名": 0, "人物": 0, "从者": 1, "Servant": 1, "英灵": 2, "宝具": 3, "技能": 4,
            "盈月录": 12,
            "技名": 4, "固有技能": 5, "魔术": 6, "魔術": 6, "用语": 7, "用語": 7,
            "概念": 7, "组织": 8, "组织名": 8, "地名": 9, "地形": 9, "事项": 10,
            "事象": 10, "道具": 11, "武器名": 11, "装飾": 11, "装饰": 11,
            "Introduction": 20, "Explanation": 20}


def cat_rank(cat):
    return CAT_RANK.get(cat or "", 30)


# 旧译名 → 统一后的译名（搜索时自动转换并提示）
ALIAS = {"雪儿": "希耶尔", "阿尔奎德": "爱尔奎特", "阿尔奎特": "爱尔奎特",
         "Ciel": "希耶尔",
         # 术语同义/旧译（正文实际写法与词条名的对应）
         "纤维型信息记忆体": "神之丝", "神之纤维": "神之丝",
         "对肃清防御": "对肃正防御",
         "崩坏的宝具": "崩坏的幻想",
         "载体": "传承保菌者",
         "思想基盘": "思想盘", "思想键纹": "思想键",
         "脑髓体": "头脑体"}

# 角色黑称／俗称／同义词表：由 temp/95_build_aliases.py 生成（数据源 fgo.wiki 黑话页 + 角色简称表）
ALIAS_FILE = os.path.join(DATA, "aliases.json")
if os.path.exists(ALIAS_FILE):
    try:
        for _k, _v in read_json(ALIAS_FILE).items():
            if _k and _v and _k != _v:
                ALIAS.setdefault(_k, _v)
    except Exception as exc:  # noqa: BLE001
        print("别名表加载失败：%s" % exc)

# 多目标别名与纯梗说明（新版电脑版读取；旧版 aliases.json 仍保留单目标格式）
ALIAS_TARGETS = {}
ALIAS_NOTES = {}
_targets_file = os.path.join(DATA, "alias_targets.json")
_notes_file = os.path.join(DATA, "alias_notes.json")
try:
    if os.path.exists(_targets_file):
        ALIAS_TARGETS = read_json(_targets_file) or {}
    if os.path.exists(_notes_file):
        ALIAS_NOTES = read_json(_notes_file) or {}
except Exception as exc:  # noqa: BLE001
    print("多目标别名表加载失败：%s" % exc)

# 大小写不敏感索引（B叔 / b叔、CBA / cba、R姐 / r姐 都能命中）
QUERY_REWRITES = {}
SUGGEST_OVERRIDES = {}
_qr_file = os.path.join(DATA, "query_rewrites.json")
if os.path.exists(_qr_file):
    try:
        QUERY_REWRITES = read_json(_qr_file) or {}
    except Exception as exc:  # noqa: BLE001
        print("查询改写表加载失败：%s" % exc)

_suggest_file = os.path.join(DATA, "suggest_overrides.json")
if os.path.exists(_suggest_file):
    try:
        SUGGEST_OVERRIDES = read_json(_suggest_file) or {}
    except Exception as exc:  # noqa: BLE001
        print("联想优先级表加载失败：%s" % exc)


def query_rewrite_parts(q):
    out = []
    for phrase, targets in QUERY_REWRITES.items():
        if phrase and phrase in q:
            values = targets if isinstance(targets, list) else [targets]
            for value in values:
                if value and value not in out:
                    out.append(value)
    return out


ALIAS_CI = {}
for _nick, _term in ALIAS.items():
    ALIAS_CI.setdefault(_nick.lower(), (_nick, _term))
ALIAS_TARGET_CI = {}
for _nick, _target in ALIAS_TARGETS.items():
    ALIAS_TARGET_CI.setdefault(_nick.lower(), (_nick, _target))
ALIAS_NOTES_CI = {}
for _nick, _note in ALIAS_NOTES.items():
    ALIAS_NOTES_CI.setdefault(_nick.lower(), _note)


def alias_lookup(q):
    """返回 (用户输入昵称, 目标数组)；旧单目标表自动转成数组。"""
    if q in ALIAS_TARGETS:
        raw = ALIAS_TARGETS[q]
        return q, raw if isinstance(raw, list) else [raw]
    low = q.lower()
    if low in ALIAS_TARGET_CI:
        nick, raw = ALIAS_TARGET_CI[low]
        return nick, raw if isinstance(raw, list) else [raw]
    if q in ALIAS:
        return q, [ALIAS[q]]
    hit = ALIAS_CI.get(low)
    return (hit[0], [hit[1]]) if hit else None


def alias_note_lookup(q):
    if q in ALIAS_NOTES:
        return ALIAS_NOTES[q]
    return ALIAS_NOTES_CI.get(q.lower())


def alias_prefix(q, limit=3):
    """按前缀找别名；值为目标数组。"""
    ql = q.lower()
    out = []
    for nick, raw in ALIAS_TARGETS.items():
        if nick != q and nick.lower().startswith(ql):
            out.append((nick, raw if isinstance(raw, list) else [raw]))
            if len(out) >= limit:
                break
    if not out:
        for nick, target in ALIAS.items():
            if nick != q and nick.lower().startswith(ql):
                out.append((nick, [target]))
                if len(out) >= limit:
                    break
    return out

MULTI_TERM_SPLIT_RE = re.compile(r"[,，;；|｜、\r\n]+")


def split_multi_terms(q):
    """Return distinct non-empty query fragments only when a real separator was used."""
    parts = [part.strip() for part in MULTI_TERM_SPLIT_RE.split(q or "")]
    parts = [part for part in parts if part]
    return parts if len(parts) >= 2 else []


def combination_membership_count(k):
    """Number of size>=2 combinations represented by a unit matching k term groups."""
    if k < 2:
        return 0
    return (1 << k) - 1 - k


def shortest_span(position_groups):
    """Minimum character span containing at least one position from every group."""
    groups = []
    for values in position_groups or []:
        values = sorted({int(value) for value in values})
        if not values:
            return None
        groups.append(values)
    if not groups:
        return None
    if len(groups) == 1:
        return 0

    heap = []
    current_max = -1
    for group_id, values in enumerate(groups):
        current_max = max(current_max, values[0])
        heapq.heappush(heap, (values[0], group_id, 0))
    best = None
    while heap:
        low, group_id, index = heapq.heappop(heap)
        span = current_max - low
        best = span if best is None else min(best, span)
        next_index = index + 1
        if next_index >= len(groups[group_id]):
            break
        next_pos = groups[group_id][next_index]
        current_max = max(current_max, next_pos)
        heapq.heappush(heap, (next_pos, group_id, next_index))
    return best

def first_matching_level(masks, max_level):
    """Highest coverage level present in the candidate masks."""
    for level in range(max_level, 0, -1):
        if any(int(mask).bit_count() >= level for mask in masks):
            return level
    return 0


def compile_multi_term_pattern(groups):
    """Compile one shared regex for every synonym group and remember variant ownership."""
    alternatives, owners = [], {}
    for group_id, group in enumerate(groups or []):
        variants = sorted(
            {str(value or "").strip() for value in (group.get("variants") or []) if str(value or "").strip()},
            key=lambda value: (-len(value), value.casefold()),
        )
        for variant_id, variant in enumerate(variants):
            name = "m%dx%d" % (group_id, variant_id)
            alternatives.append("(?P<%s>%s)" % (name, occurrence_term_pattern(variant)))
            owners[name] = group_id
    if not alternatives:
        return re.compile(r"(?!x)x"), owners
    return re.compile("|".join(alternatives), re.I), owners


def match_multi_term_groups(text, pattern, owners):
    """Return matched positions per group plus the group bitmask."""
    positions = defaultdict(set)
    for match in pattern.finditer(text or ""):
        group_id = owners.get(match.lastgroup)
        if group_id is not None:
            positions[group_id].add(match.start())
    mask = 0
    for group_id in positions:
        mask |= 1 << group_id
    return {group_id: sorted(values) for group_id, values in positions.items()}, mask


SNIPPET_TARGET_LEN = 360
SNIPPET_HARD_MAX = 600
SNIPPET_PARAGRAPH_TARGET = 600
SNIPPET_PARAGRAPH_HARD = 800
SNIPPET_SHORT_PARAGRAPH = 180
SNIPPET_SENT_END = "。！？!?…"
SNIPPET_SENT_CLOSE = "」』”\"）)》〉】"
SNIPPET_CLAUSE_END = "，；：,;:"


def _sentence_start(text, pos):
    i = min(max(pos - 1, -1), len(text) - 1)
    while i >= 0 and text[i].isspace():
        i -= 1
    while i >= 0:
        if text[i] in SNIPPET_SENT_END:
            start = i + 1
            while start < len(text) and text[start] in SNIPPET_SENT_CLOSE + " \t":
                start += 1
            return start
        if text[i] in "\n\r":
            return i + 1
        i -= 1
    return 0


def _sentence_end(text, pos):
    i = min(max(pos, 0), len(text))
    while i < len(text) and text[i].isspace():
        i += 1
    while i < len(text):
        if text[i] in SNIPPET_SENT_END:
            end = i + 1
            while end < len(text) and text[end] in SNIPPET_SENT_CLOSE:
                end += 1
            return end
        if text[i] in "\n\r":
            return i
        i += 1
    return len(text)


def _sentence_span(text, pos):
    return _sentence_start(text, pos), _sentence_end(text, pos)


def _paragraph_bounds(text, pos):
    start = max(text.rfind("\n", 0, pos), text.rfind("\r", 0, pos)) + 1
    ends = [value for value in (text.find("\n", pos), text.find("\r", pos)) if value >= 0]
    return start, min(ends) if ends else len(text)


def _oversized_sentence_span(text, match_start, match_end, hard_max):
    paragraph_start, paragraph_end = _paragraph_bounds(text, match_start)
    if paragraph_end - paragraph_start <= hard_max:
        return paragraph_start, paragraph_end

    boundaries = SNIPPET_CLAUSE_END + SNIPPET_SENT_END + "\n\r"
    starts = [paragraph_start]
    ends = [paragraph_end]
    for index in range(paragraph_start, paragraph_end):
        if text[index] in boundaries:
            if index < match_start:
                starts.append(index + 1)
            if index >= match_end:
                ends.append(index + 1)
    valid = [(start, end) for start in starts for end in ends
             if start <= match_start and end >= match_end and end - start <= hard_max]
    if valid:
        return max(valid, key=lambda pair: pair[1] - pair[0])

    match_len = max(1, match_end - match_start)
    start = max(paragraph_start, match_start - max(0, (hard_max - match_len) // 2))
    end = min(paragraph_end, start + hard_max)
    if end < match_end:
        end = min(paragraph_end, match_end)
        start = max(paragraph_start, end - hard_max)
    return start, end


def select_snippet_span(text, match_start, match_end, target_len=SNIPPET_TARGET_LEN,
                        hard_max=SNIPPET_HARD_MAX, before=2, after=2):
    """Select complete sentence boundaries, preserving the matching sentence."""
    text = str(text or "")
    if not text:
        return 0, 0
    match_start = min(max(int(match_start), 0), len(text))
    match_end = min(max(int(match_end), match_start), len(text))
    start, end = _sentence_span(text, match_start)
    if match_end > end:
        end = _sentence_end(text, match_end)
    if end - start > hard_max:
        return _oversized_sentence_span(text, match_start, match_end, hard_max)
    if end - start > target_len:
        return start, end

    added_before = added_after = 0
    while added_before < before or added_after < after:
        candidates = []
        if added_after < after:
            next_start = end
            while next_start < len(text) and text[next_start].isspace():
                next_start += 1
            if next_start < len(text):
                next_end = _sentence_end(text, next_start)
                if next_end > next_start:
                    candidates.append(("after", next_start, next_end))
        if added_before < before:
            previous_end = start
            while previous_end > 0 and text[previous_end - 1].isspace():
                previous_end -= 1
            if previous_end > 0:
                previous_start = _sentence_start(text, previous_end)
                if previous_start < previous_end:
                    candidates.append(("before", previous_start, previous_end))
        chosen = None
        for candidate in candidates:
            _side, candidate_start, candidate_end = candidate
            if candidate_end - start <= target_len and end - candidate_start <= target_len:
                chosen = candidate
                break
        if chosen is None:
            break
        side, candidate_start, candidate_end = chosen
        start = min(start, candidate_start)
        end = max(end, candidate_end)
        if side == "before":
            added_before += 1
        else:
            added_after += 1
    return start, end


OFFICIAL_MIN_SNIPPET_CHARS = 12
OFFICIAL_SNIPPET_PUNCT_RE = re.compile(
    r"""[\s…。！？!?，,、；;：:（）()《》〈〉「」『』\[\]【】—－\-/／·・.．"'“”‘’]+"""
)


def official_snippet_is_long_enough(text):
    return len(OFFICIAL_SNIPPET_PUNCT_RE.sub("", str(text or ""))) >= OFFICIAL_MIN_SNIPPET_CHARS


def _blocks_are_contiguous(text, left_end, right_start):
    if right_start < left_end:
        return False
    gap = right_start - left_end
    return gap <= 8 and not text[left_end:right_start].strip()


def select_block_snippet_span(text, blocks, match_start, match_end,
                             target_len=SNIPPET_PARAGRAPH_TARGET,
                             hard_max=SNIPPET_PARAGRAPH_HARD,
                             short_threshold=SNIPPET_SHORT_PARAGRAPH):
    """Prefer the whole matching paragraph, adding adjacent paragraphs only when short."""
    text = str(text or "")
    normalized = [(int(start), int(end)) for start, end in blocks or []
                  if int(end) > int(start)]
    if not normalized or not text:
        return 0, 0
    normalized.sort()
    match_start = min(max(int(match_start), 0), len(text))
    match_end = min(max(int(match_end), match_start), len(text))
    block_index = None
    for index, (start, end) in enumerate(normalized):
        if start <= match_start < end or (match_start == len(text) and end == len(text)):
            block_index = index
            break
    if block_index is None:
        return select_snippet_span(text, match_start, match_end,
                                   target_len=hard_max, hard_max=hard_max,
                                   before=100, after=100)

    start, end = normalized[block_index]
    block_len = end - start
    if block_len > hard_max:
        local_start, local_end = select_snippet_span(
            text[start:end], match_start - start, match_end - start,
            target_len=hard_max, hard_max=hard_max, before=100, after=100,
        )
        return start + local_start, start + local_end

    if block_len >= short_threshold:
        return start, end

    left = block_index - 1
    right = block_index + 1
    prefer_right = True
    while end - start < short_threshold:
        right_choice = None
        left_choice = None
        if right < len(normalized):
            next_start, next_end = normalized[right]
            if (_blocks_are_contiguous(text, end, next_start)
                    and next_end - start <= target_len):
                right_choice = ("right", next_start, next_end)
        if left >= 0:
            previous_start, previous_end = normalized[left]
            if (_blocks_are_contiguous(text, previous_end, start)
                    and end - previous_start <= target_len):
                left_choice = ("left", previous_start, previous_end)
        side, candidate_start, candidate_end = (
            right_choice if prefer_right and right_choice
            else left_choice if left_choice
            else right_choice if right_choice
            else (None, None, None)
        )
        if side is None:
            break
        start = min(start, candidate_start)
        end = max(end, candidate_end)
        if side == "left":
            left -= 1
            prefer_right = True
        else:
            right += 1
            prefer_right = False
    return start, end

__all__ = [name for name in globals() if not name.startswith("__")]
