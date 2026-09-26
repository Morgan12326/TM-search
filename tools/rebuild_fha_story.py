# -*- coding: utf-8 -*-
"""Rebuild the Fate/hollow ataraxia reading tree from the original event index.

This script only changes FHA-owned documents and the FHA work node.  It keeps
the existing Steam REMASTERED Chinese body text, uses the original split-text
event table as the structural authority, and imports missing mainline scenes.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEFAULT_SPLIT_ROOT = Path(r"D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版 - 副本\原作文本\FHA\分割版")
EVENT_LIST = "全事件一覧.txt"

MAIN_ROUTE = "主线：复仇者与巴泽特"
DAILY_ROUTES = {
    "10月8日": "日常事件 · 10月8日",
    "10月9日": "日常事件 · 10月9日",
    "10月10日": "日常事件 · 10月10日",
    "10月11日": "日常事件 · 10月11日",
    "Einzbern城": "日常事件 · 艾因兹贝伦城",
}
EXTRAS_ROUTE = "其他番外"
EXTRAS_GROUPS = ("夜间短篇", "Eclipse 番外", "其他特别篇", "小游戏", "杂项")

KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# The event table is the primary ordering source.  These overrides cover
# spelling differences between the table, the split files, and old imports.
SOURCE_OVERRIDES = {
    ("prologue. 柳洞寺の怪談", "真・冒頭"): "prologue柳洞寺の怪談",
    ("夜の聖杯戦争１", "真・冒頭"): "夜の聖杯戦争1",
    ("夜の聖杯戦争２", "真・冒頭"): "夜の聖杯戦争2",
    ("夜の聖杯戦争３", "真・冒頭"): "夜の聖杯戦争3",
    ("夜の聖杯戦争４", "真・冒頭"): "夜の聖杯戦争4",
    ("夜の聖杯戦争５", "真・冒頭"): "夜の聖杯戦争5",
    ("夜の聖杯戦争６", "真・冒頭"): "夜の聖杯戦争6",
    ("夜の聖杯戦争７", "真・冒頭"): "夜の聖杯戦争7",
    ("サイカイ", "真・冒頭"): "再会(サイカイ)",
    ("サイカイ", "衛宮邸・1日目"): "サイカイ .txt",
    ("異状なし（１）", "夜編1"): "異状なし(1-3)",
    ("異状なし（２）", "夜編1"): "異状なし(1-3)",
    ("異状なし（３）", "夜編1"): "異状なし(1-3)",
    ("異常なし（Ⅰ）", "夜編2"): "異常なし(I-III)",
    ("異常なし（Ⅱ）", "夜編2"): "異常なし(I-III)",
    ("異常なし（Ⅲ）", "夜編2"): "異常なし(I-III)",
    ("デッドブリッジ（Ⅰ）", "夜編1"): "夜間．大橋『Dead Bridge（Ⅰ&2）』",
    ("デッドブリッジ（Ⅱ）", "夜編2"): "夜間．大橋『Dead Bridge（Ⅰ&2）』",
    ("営みの窓", "衛宮邸・夜開始"): "夕方．衛宮邸『営みの窓』",
    ("夜の街へ（戦闘）", "夜編2"): "夜間．『夜の街へ（戦闘）』",
    ("凛への相談", "衛宮邸・夜マップ"): "夜間．凛の部屋『凛への相談",
    ("合宿、承認", "学校・4日目"): "合宿 承認",
    ("ロンドンにて", "衛宮邸・夜マップ"): "伦敦见闻(ロンドンにて)",
    ("決戦", "夜編2"): "決戰",
    ("フォレスト", "真・冒頭"): "forest",
    ("ブロードブリッジ", "衛宮邸・夜開始"): "Broad bridge",
    ("－アトゴウラ－", "夜編1"): "四枝之浅滩(アトゴウラ)",
    ("Ｗｉｓｈ．", "街・特別編"): "Wish",
    ("epilogue.", "衛宮邸・夜開始"): "epilogue.",
    ("カレンⅠ", "カレン"): "カレン 1",
    ("カレンⅡ", "カレン"): "カレン 2",
    ("カレンⅢ", "カレン"): "カレン 3",
    ("カレンⅣ", "カレン"): "カレン 4",
    ("カレンⅤ", "カレン"): "カレン 5",
}

# Merge rows that share one imported text file in the old split corpus.
MERGE_GROUPS = {
    ("異状なし（１）", "夜編1"): "anomaly_night_1",
    ("異状なし（２）", "夜編1"): "anomaly_night_1",
    ("異状なし（３）", "夜編1"): "anomaly_night_1",
    ("異常なし（Ⅰ）", "夜編2"): "anomaly_night_2",
    ("異常なし（Ⅱ）", "夜編2"): "anomaly_night_2",
    ("異常なし（Ⅲ）", "夜編2"): "anomaly_night_2",
    ("デッドブリッジ（Ⅰ）", "夜編1"): "dead_bridge",
    ("デッドブリッジ（Ⅱ）", "夜編2"): "dead_bridge",
}

MERGE_META = {
    "anomaly_night_1": ("夜间侦察 I：异常记录 I-III", "異状なし 1-3"),
    "anomaly_night_2": ("夜间侦察 II：异常记录 I-III", "異常なし I-III"),
    "dead_bridge": ("大桥：死桥 I-II", "Dead Bridge I-II"),
}

CORE_GROUPS = {"真・冒頭", "夜編1", "夜編2", "衛宮邸・夜開始", "衛宮邸・夜マップ", "カレン"}

MAIN_TITLE_ZH = {
    ("prologue. 柳洞寺の怪談", "真・冒頭"): "柳洞寺怪谈",
    ("夜の聖杯戦争１", "真・冒頭"): "夜间圣杯战争 I",
    ("夜の聖杯戦争２", "真・冒頭"): "夜间圣杯战争 II",
    ("夜の聖杯戦争３", "真・冒頭"): "夜间圣杯战争 III",
    ("夜の聖杯戦争４", "真・冒頭"): "夜间圣杯战争 IV",
    ("夜の聖杯戦争５", "真・冒頭"): "夜间圣杯战争 V",
    ("夜の聖杯戦争６", "真・冒頭"): "夜间圣杯战争 VI",
    ("夜の聖杯戦争７", "真・冒頭"): "夜间圣杯战争 VII",
    ("サイカイ", "真・冒頭"): "再会 I",
    ("サイカイ", "衛宮邸・1日目"): "再会 II",
    ("朝の一時", "真・冒頭"): "早晨的一刻",
    ("来訪者", "街編・2日目"): "来访者",
    ("後継者", "街編・3日目"): "继承者",
    ("無人館の殺人", "街編・1日目"): "无人馆杀人事件",
    ("営みの窓", "衛宮邸・夜開始"): "生活的窗口",
    ("夜の街へ（哨戒）", "夜編1"): "夜间上街（侦察）",
    ("四夜の終末", "夜編1"): "四夜终末",
    ("おしまいの夜", "衛宮邸・夜開始"): "最后一夜",
    ("見知った子供", "街編・2日目"): "似曾相识的孩子",
    ("その未来は今", "衛宮邸・夜マップ"): "未来就在此刻",
    ("monster", "衛宮邸・夜マップ"): "怪物",
    ("戦士の心得", "ランサー港"): "战士的觉悟",
    ("間際の夢", "柳洞寺・1日目"): "临终之梦",
    ("覚醒（未）", "衛宮邸・夜マップ"): "觉醒（未）",
    ("夜の街へ（戦闘）", "夜編2"): "夜间上街（战斗）",
    ("憑夜のできごと", "夜編2"): "凭夜之事",
    ("探偵二人", "街編・3日目"): "两名侦探",
    ("忘れじの君へ", "街編・1日目"): "致难忘之人",
    ("覚醒（偽）", "衛宮邸・夜マップ"): "觉醒（伪）",
    ("残骸百景", "柳洞寺・2日目"): "残骸百景",
    ("決戦", "夜編2"): "决战",
    ("銀の糸", "夜編1"): "银之丝",
    ("処刑鑑賞", "夜編1"): "处刑鉴赏",
    ("対決", "夜編2"): "对决",
    ("凛帰国", "真・冒頭"): "凛归国",
    ("角笛（響かず）", "ランサー港"): "角笛（未响）",
    ("凛への相談", "衛宮邸・夜マップ"): "与凛商量",
    ("合宿、承認", "学校・4日目"): "合宿，批准",
    ("景山の一夜", "合宿編"): "景山之夜",
    ("カレンⅠ", "カレン"): "卡莲 I",
    ("カレンⅡ", "カレン"): "卡莲 II",
    ("カレンⅢ", "カレン"): "卡莲 III",
    ("カレンⅣ", "カレン"): "卡莲 IV",
    ("カレンⅤ", "カレン"): "卡莲 V",
    ("フォレスト", "真・冒頭"): "森林",
    ("その過去は既に", "ランサー港"): "那个过去已成过去",
    ("帰り道", "学校・4日目"): "归途",
    ("ボーダー", "街編・4日目"): "境界线",
    ("桃源の夢", "柳洞寺・2日目"): "桃源之梦",
    ("Ｗｉｓｈ．", "街・特別編"): "愿望",
    ("常世の橋・右", "街編・1日目"): "常世之桥・右",
    ("ロンドンにて", "衛宮邸・夜マップ"): "伦敦见闻",
    ("双子館の殺人", "街編・1日目"): "双子馆杀人事件",
    ("角笛（確かに）", "ランサー港"): "角笛（响起）",
    ("－アトゴウラ－", "夜編1"): "四枝之浅滩",
    ("常夜の橋・左", "街編・3日目"): "常夜之桥・左",
    ("天の杯", "魔境編"): "天之杯",
    ("スパイラル・ラダー", "衛宮邸・夜開始"): "螺旋阶梯",
    ("ブロードブリッジ", "衛宮邸・夜開始"): "宽桥",
    ("天の逆月", "衛宮邸・夜開始"): "天之逆月",
    ("epilogue.", "衛宮邸・夜開始"): "终章",
}

EVENT_TITLE_ZH_BY_ID = {
    1414: "Emiya Ammer",
    1415: "蜘蛛阶梯",
    1417: "薯条与薯片",
    1495: "回归",
    1511: "何去何从",
    1556: "Dialog・Lost Loop II",
    1563: "水边的王者・序章",
    1592: "幽灵闲话 Gossip",
    1593: "幽灵闲话 Glamorous",
    1596: "晚安之夜・伊莉雅",
    1597: "晚安之夜・冬",
    1600: "Hotel・Einzbern",
    1630: "四重奏",
}
EVENT_TITLE_ZH = {
    "quo vadisクオバディス": "何去何从",
    "午前衛宮邸dialoglostloopⅱ": "Dialog・Lost Loop II",
    "水辺の王様序章": "水边的王者・序章",
    "ぺたぺた2": "啪嗒啪嗒 2",
    "ぺたぺた3": "啪嗒啪嗒 3",
    "returnリターン": "回归（Return）",
    "ghostgossipglamorousゴーストゴシップ": "幽灵闲话 Gossip",
    "ghostgossipglamorousゴーストゴシップグラマラス": "幽灵闲话 Glamorous",
    "あきらめる": "放弃",
    "おやすみの夜イリヤ": "晚安之夜・伊莉雅",
    "おやすみの夜冬": "晚安之夜・冬",
    "午後hotelアインツベルン": "Hotel・Einzbern",
    "エミヤアンマー": "Emiya Ammer",
    "スパイダーラダー": "蜘蛛阶梯",
    "チップチップス": "薯条与薯片",
    "quartetカルテット": "四重奏",
    "メディカルメディスン": "医疗药物",
    "働く槍さん花屋編": "打工的枪兵（花店篇）",
    "午前賢者の帰還": "贤者的归还",
    "午後商店街ワビサビツマミ": "商店街：寂寥与下酒菜",
    "帰国のあと": "归国之后",
    "彼女の別荘": "她的别墅",
    "思い出の海": "回忆之海",
    "間桐家の人々": "间桐家的人们",
    "お届けキャスター": "快递Caster",
    "ライダーとサンドイッチ": "Rider与三明治",
    "姉妹の昼食": "姐妹的午餐",
    "家路の灯り": "归家灯火",
    "昼飯に行こう": "去吃午饭吧！",
    "暴走ネコトラ一家": "暴走猫虎一家",
    "桜と特製お弁当": "樱与特制便当",
    "生徒会長健在です": "学生会长，健在",
    "藤ねえ教師フォーム": "藤姐教师形态",
    "墓参り": "扫墓",
    "午前土蔵アイリスの土蔵": "爱丽丝的土藏",
    "午前衛宮邸キビシスの鏡": "严苛之镜",
    "午後近頃のsaber": "最近的Saber",
    "午後道場午後の光": "午后之光",
    "藤ねえ柿祭り": "藤姐柿子祭",
    "お使いライダー帰還せず": "跑腿Rider，未归还",
    "ひとりで掃除": "独自打扫",
    "みんなで掃除": "大家一起打扫",
    "キャスターのお買い物良妻編": "Caster的购物（良妻篇）",
    "天使とダイヤモンド": "天使与钻石",
    "宝箱ミミック遠坂lv13": "宝箱（拟态远坂 LV1-3）",
    "あやしいふたり": "可疑的两人",
    "弓道部の或る日常": "弓道部的某个日常",
    "文化祭に向けて": "筹备文化祭",
    "蒔寺と凛のペンダント": "莳寺与凛的吊坠",
    "キャスター料理修行": "Caster的料理修行",
    "マロンパイの誘惑": "栗子派的诱惑",
    "ライダーと読書とやきもち桜": "Rider、读书与吃醋的樱",
    "五年越しの客": "五年后的客人",
    "砂糖菓子のteatime": "糖果TeaTime",
    "高級食材の罠": "高级食材的陷阱",
    "ある日の三人娘": "某天的三位少女",
    "凛の魔術指南": "凛的魔术指南",
    "氷室鐘の考察": "冰室钟的考察",
    "美綴リバイバル": "美缀复活",
    "頑張るお料理キャスター": "努力做菜的Caster",
    "夕日の蛇姫": "夕阳的蛇姬",
    "桜と美綴と弓道部": "樱、美缀与弓道部",
    "陸上部のお弁当": "田径部的便当",
    "午前セイバーの部屋王様の見立て役": "王的参谋",
    "午前ライダーの部屋週に二回の手入れですから": "因为每周要保养两次",
    "午前土蔵凛とovertechnology": "凛与Over Technology",
    "午後土蔵ゴルゴンの蔵": "戈尔贡的仓库",
    "午後自室脅迫状とpoolticket": "威胁信与泳池券",
    "桜の思い出": "樱的回忆",
    "ふたりのうわさ話": "两人的传闻",
    "午後遠坂邸メイドを巡る冒険": "围绕女仆的冒险",
    "午後駅前アナクロアナログ凛": "复古模拟凛",
    "慎ちゃんと海": "慎二与海",
    "桜とキャスター結束編": "樱与Caster，团结篇",
    "青豹たい黒豹": "青豹对黑豹",
    "詰め将棋とクロスワード": "将棋残局与纵横字谜",
    "その夜怪談": "那一夜的怪谈",
    "カースコレクター": "咒术收藏家",
    "ネコと坊主と堅物教師": "猫、和尚与死板教师",
    "凛の参詣": "凛的参拜",
    "午前山門参拝ですか": "是来参拜的吗？",
    "penguin型カキ氷機": "企鹅型刨冰机",
    "プールと魔眼殺し": "泳池与魔眼杀手",
    "夢見るお料理キャスター": "梦想中的料理Caster",
    "指圧の奥義哈真心です": "指压的奥义是真心",
    "遠坂探険隊": "远坂探险队",
}
TITLE_REPLACEMENTS = (
    ("ライダー", "Rider"), ("キャスター", "Caster"), ("セイバー", "Saber"),
    ("アーチャー", "Archer"), ("ランサー", "Lancer"), ("アサシン", "Assassin"),
    ("イリヤ", "伊莉雅"), ("凛", "凛"), ("桜", "樱"), ("士郎", "士郎"),
    ("衛宮邸", "卫宫邸"), ("柳洞寺", "柳洞寺"), ("冬木市", "冬木市"),
    ("学園", "学园"), ("教会", "教会"), ("港", "港口"), ("駅前", "站前"),
    ("大橋", "大桥"), ("土蔵", "土藏"), ("自室", "自室"), ("校庭", "校庭"),
    ("昼", "白天"), ("午前", "上午"), ("午後", "下午"), ("夕方", "傍晚"),
    ("夜間", "夜间"), ("深夜", "深夜"), ("翌日", "次日"), ("後日談", "后日谈"),
    ("お祭り", "祭典"), ("料理", "料理"), ("買い物", "购物"),
    ("掃除", "打扫"), ("約束", "约定"), ("夢", "梦"), ("帰り道", "归途"),
    ("勝負", "胜负"), ("決戦", "决战"), ("対決", "对决"), ("事件", "事件"),
    ("密室", "密室"), ("殺人", "杀人"), ("洋館", "洋馆"), ("城", "城"),
    ("森", "森林"), ("庭", "庭院"), ("部屋", "房间"), ("門", "门"),
    ("手紙", "信"), ("料理修行", "料理修行"), ("魔術", "魔术"),
)
KATAKANA_WORD_RE = re.compile(r"[ァ-ヶー]{2,}")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload, *, pretty=False):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def _decode_source(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"unsupported source encoding: {path}")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _stem_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.translate(str.maketrans({
        "Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4", "Ⅴ": "5",
        "Ⅵ": "6", "Ⅶ": "7", "Ⅷ": "8", "Ⅸ": "9", "Ⅹ": "10",
        "１": "1", "２": "2", "３": "3", "４": "4", "５": "5",
        "６": "6", "７": "7", "０": "0", "Ｗ": "W", "ｉ": "i",
        "ｓ": "s", "ｈ": "h",
    }))
    value = value.upper()
    return re.sub(r"[\s\.\,，。・:：\-—–―ー_()（）\[\]【】『』「」<>≪≫'\"]", "", value)


def _strip_file_ext(value: str) -> str:
    path = Path(value)
    return path.stem if path.suffix else value


def _event_rows(split_root: Path):
    path = split_root / EVENT_LIST
    text = path.read_bytes().decode("utf-16")
    rows = []
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 5 and cols[0] == "Hollow" and cols[1] == "本編":
            rows.append({"title": cols[2], "group": cols[3], "order": int(cols[4])})
    if len(rows) != 69:
        raise RuntimeError(f"expected 69 Hollow 本編 rows, found {len(rows)}")
    return rows


def _doc_stem(doc: dict) -> str:
    meta = doc.get("meta", {})
    value = meta.get("分章文件") or doc.get("file", "")
    return _strip_file_ext(str(value))


def _build_doc_index(docs: list[dict]):
    index = defaultdict(list)
    for doc in docs:
        if doc.get("work") != "FHA":
            continue
        for value in (_doc_stem(doc), Path(str(doc.get("file", ""))).stem):
            if value:
                index[_stem_key(value)].append(doc)
    return index


def _is_prereq(row: dict) -> bool:
    if row["group"] == "魔境編" and row["title"] == "天の杯":
        return False
    if row["group"] == "衛宮邸・1日目" and row["title"] == "サイカイ":
        return False
    return row["group"] not in CORE_GROUPS


def _sanitize_path(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", value).strip(" .") or "未命名"


def _display_title(zh: str, original: str) -> str:
    zh = zh.strip()
    original = original.strip()
    if not zh or _stem_key(zh) == _stem_key(original):
        return zh or original
    return f"{zh}（{original}）"


def _looks_like_heading(value: str) -> bool:
    value = value.strip("　 ")
    if not value or len(value) > 44:
        return False
    if re.search(r"[。！？!?]", value):
        return False
    if value.startswith(("译者", "翻譯", "翻译", "录入", "校對", "校对", "掃圖", "扫图")):
        return False
    return any(mark in value for mark in ("『", "「", "．", "·", "：", ":")) or value.startswith(
        ("夜", "朝", "午前", "午後", "傍晚", "深夜", "凌晨")
    )


def _candidate_from_heading(text: str) -> str:
    for line in text.splitlines()[:5]:
        clean = line.strip("　 ")
        if not _looks_like_heading(clean):
            continue
        for pattern in (r"『([^』]{2,34})』", r"「([^」]{2,34})」"):
            match = re.search(pattern, clean)
            if not match:
                continue
            candidate = match.group(1).strip()
            if HAN_RE.search(candidate) and len(KANA_RE.findall(candidate)) <= 3:
                return candidate
        if HAN_RE.search(clean) and not KANA_RE.search(clean) and len(clean) <= 30:
            return clean
    return ""


def _clean_japanese_title(value: str) -> str:
    result = value
    for source, target in TITLE_REPLACEMENTS:
        result = result.replace(source, target)
    result = re.sub(r"(?:のこと|という|というもの|について|のために|ように|する|した|して|です|ます|から|まで|だけ|でも|って|たち|頃|頃に)", "", result)
    result = result.replace("の", "之").replace("と", "与").replace("へ", "于")
    result = re.sub(r"[ぁ-ゖァ-ヺー]{1,}", "", result)
    result = re.sub(r"\s+", " ", result).strip("　 ．。・")
    return result


def _title_zh_for_doc(doc: dict, *texts: str) -> str:
    override = EVENT_TITLE_ZH_BY_ID.get(doc.get("id")) or EVENT_TITLE_ZH.get(_stem_key(_doc_stem(doc)))
    if override:
        return override
    current = _strip_file_ext(str(doc.get("meta", {}).get("分章文件") or doc.get("title", ""))).strip()
    event = current
    candidates = []
    for text in texts:
        candidate = _candidate_from_heading(text or "")
        if candidate:
            candidates.append(candidate)
    if candidates:
        candidate = min(
            candidates,
            key=lambda value: (len(KANA_RE.findall(value)), -len(HAN_RE.findall(value)), len(value)),
        )
        cleaned = _clean_japanese_title(candidate)
        if cleaned and HAN_RE.search(cleaned):
            return cleaned
    if event and not KANA_RE.search(event):
        return event
    cleaned = _clean_japanese_title(event)
    if cleaned and HAN_RE.search(cleaned):
        return cleaned
    return event or _doc_stem(doc)


def _prepare_missing_main_doc(entries: dict, story_blocks: list, offsets: list, split_root: Path):
    existing = next((d for d in entries["docs"] if d.get("meta", {}).get("fha_source_stem") == "おしまいの夜"), None)
    if existing:
        return existing["id"], None, False
    source = split_root / "夜間" / "おしまいの夜.txt"
    if not source.exists():
        raise RuntimeError(f"missing source: {source}")
    text = _decode_source(source)
    new_id = max(d.get("id", -1) for d in entries["docs"]) + 1
    doc = {
        "id": new_id,
        "title": "『おしまいの夜』",
        "work": "FHA",
        "kind": "原作",
        "file": f"剧情大全\\FHA\\{MAIN_ROUTE}\\『おしまいの夜』.txt",
        "chars": len(text),
        "lang": "zh",
        "ja_ratio": 0,
        "meta": {
            "来源": "FHA 参考分割文本",
            "导入来源": "FHA 主线补齐",
            "分章文件": "おしまいの夜.txt",
            "fha_source_stem": "おしまいの夜",
        },
    }
    entries["docs"].append(doc)
    story_blocks.append([new_id, 0, text])
    offsets.append([0, len(text), new_id, 0])
    return new_id, text, True


def _extract_main_specs(data_dir: Path, split_root: Path):
    entries = _load_json(data_dir / "entries.json")
    story = _load_json(data_dir / "story.json")
    story_blocks = _load_json(data_dir / "story_blocks.json")
    offsets = _load_json(data_dir / "offsets.json")
    new_doc_id, new_doc_text, added = _prepare_missing_main_doc(entries, story_blocks, offsets, split_root)
    docs = [d for d in entries["docs"] if d.get("work") == "FHA"]
    by_id = {d["id"]: d for d in docs}
    index = _build_doc_index(docs)
    out = []
    seen_merge = set()
    for row in _event_rows(split_root):
        source_stem = _strip_file_ext(SOURCE_OVERRIDES.get((row["title"], row["group"]), row["title"]))
        merge_key = MERGE_GROUPS.get((row["title"], row["group"]))
        if merge_key and merge_key in seen_merge:
            continue
        if merge_key:
            seen_merge.add(merge_key)
        if row["title"] == "おしまいの夜":
            candidates = [by_id[new_doc_id]]
        else:
            candidates = index.get(_stem_key(source_stem), [])
        if not candidates:
            raise RuntimeError(f"main event has no document: {row} -> {source_stem}")
        if len(candidates) > 1:
            candidates = [c for c in candidates if c.get("work") == "FHA"]
        doc = candidates[0]
        if merge_key:
            zh_title, original = MERGE_META[merge_key]
            prereq = False
        else:
            zh_title = MAIN_TITLE_ZH.get((row["title"], row["group"]))
            if not zh_title:
                zh_title = _title_zh_for_doc(doc, "\n".join(
                    text for d, _, text in story_blocks if d == doc["id"]
                ))
            original = row["title"]
            prereq = _is_prereq(row)
        out.append({
            "title": _display_title(zh_title, original),
            "doc": doc["id"],
            "start": 0,
            "end": None,
            "prereq": prereq,
            "source_group": row["group"],
            "source_order": row["order"],
            "source_title": row["title"],
        })
    for n, chapter in enumerate(out, 1):
        chapter["main_index"] = n
        prefix = f"{n:02d} "
        if chapter["prereq"]:
            prefix += "【前置】"
        chapter["title"] = prefix + chapter["title"]
    return entries, story, story_blocks, offsets, out, new_doc_id, new_doc_text, added


def _existing_work(story: dict):
    return next(w for w in story["works"] if w.get("work") == "FHA")


def _build_routes(entries: dict, story: dict, story_blocks: list, main_specs: list[dict], split_root: Path):
    work = _existing_work(story)
    docs = {d["id"]: d for d in entries["docs"] if d.get("work") == "FHA"}
    source_text_by_key = {}
    for source_path in split_root.rglob("*.txt"):
        source_text_by_key[_stem_key(source_path.stem)] = _decode_source(source_path)
    old_route = {}
    old_group = {}
    for route in work["routes"]:
        for chapter in route["chapters"]:
            old_route[chapter["doc"]] = route["name"]
            old_group[chapter["doc"]] = chapter.get("group", "")
    main_ids = {chapter["doc"] for chapter in main_specs}
    daily_name_to_key = {name: key for key, name in DAILY_ROUTES.items()}
    grouped = defaultdict(list)
    for doc_id, doc in docs.items():
        if doc_id in main_ids:
            continue
        if doc_id not in old_route:
            continue
        doc.setdefault("meta", {}).setdefault("FHA原始分类", old_route.get(doc_id))
        route = old_route.get(doc_id)
        if route == EXTRAS_ROUTE:
            group = old_group.get(doc_id)
            if group in EXTRAS_GROUPS:
                grouped[("extras", group)].append(doc_id)
                continue
        if route in daily_name_to_key:
            key = daily_name_to_key[route]
            grouped[("daily", key)].append(doc_id)
            continue
        route = doc["meta"].get("FHA原始分类") or route
        title = str(doc.get("meta", {}).get("分章文件") or doc.get("title", ""))
        date_hint = str(doc.get("title", "")) if route == "日常事件" else title
        if route == "日常事件":
            if doc_id in {1612, 1613, 1614, 1615, 1616, 1617}:
                grouped[("extras", "Eclipse 番外")].append(doc_id)
            elif date_hint.startswith("Einzbern城"):
                grouped[("daily", "Einzbern城")].append(doc_id)
            else:
                date_match = re.search(r"(10月\d+日)", date_hint)
                if not date_match:
                    raise RuntimeError(f"unrouted FHA daily document: {doc_id} {title}")
                grouped[("daily", date_match.group(1))].append(doc_id)
        elif route == "特別編":
            grouped[("extras", "其他特别篇")].append(doc_id)
        elif route in {"花札", "绘马"}:
            grouped[("extras", "小游戏")].append(doc_id)
        elif route in {"结局", "主线：四日循环"}:
            grouped[("extras", "夜间短篇")].append(doc_id)
        elif route == "其他":
            grouped[("extras", "杂项")].append(doc_id)
        else:
            raise RuntimeError(f"unexpected FHA route for doc {doc_id}: {route}")

    def chapter_for(doc_id: int, group: str = "", route_name: str = ""):
        doc = docs[doc_id]
        text = "\n".join(text for d, _, text in story_blocks if d == doc_id)
        source_text = source_text_by_key.get(_stem_key(_doc_stem(doc)), text)
        if group == "夜间短篇":
            original = _strip_file_ext(str(doc.get("meta", {}).get("分章文件") or doc.get("title", "")))
            zh = _title_zh_for_doc(doc, source_text, text)
            title = _display_title(zh, original)
        elif group in {"Eclipse 番外", "其他特别篇", "小游戏", "杂项"}:
            original = _strip_file_ext(str(doc.get("meta", {}).get("分章文件") or doc.get("title", "")))
            zh = _title_zh_for_doc(doc, source_text, text)
            title = _display_title(zh, original)
        else:
            original = str(doc.get("meta", {}).get("分章文件") or doc.get("title", ""))
            original = _strip_file_ext(original)
            location = "其他"
            m = re.match(r"^10月\d+日 · ([^·]+) ·", str(doc.get("title", "")))
            if m:
                location = m.group(1).strip()
            elif route_name.endswith("艾因兹贝伦城"):
                location = "艾因兹贝伦城"
            zh = _title_zh_for_doc(doc, source_text, text)
            title = f"{location} · {_display_title(zh, original)}"
        return {"title": title, "doc": doc_id, "start": 0, "end": None, "group": group}

    routes = []
    routes.append({"name": MAIN_ROUTE, "chapters": main_specs, "chars": 0, "extra": False})
    for key in ("10月8日", "10月9日", "10月10日", "10月11日", "Einzbern城"):
        ids = grouped.get(("daily", key), [])
        if not ids:
            continue
        routes.append({
            "name": DAILY_ROUTES[key],
            "chapters": [chapter_for(doc_id, route_name=DAILY_ROUTES[key]) for doc_id in ids],
            "chars": 0,
            "extra": False,
        })
    extras_ids = []
    for group in EXTRAS_GROUPS:
        extras_ids.extend(grouped.get(("extras", group), []))
    extras = [chapter_for(doc_id, _extras_group_for(doc_id, grouped)) for doc_id in extras_ids]
    routes.append({"name": EXTRAS_ROUTE, "chapters": extras, "chars": 0, "extra": True})
    for route in routes:
        route["chars"] = sum(docs[c["doc"]].get("chars", 0) for c in route["chapters"])
        for index, chapter in enumerate(route["chapters"]):
            chapter["key"] = f"FHA::{route['name']}::{index}"
    return routes


def _extras_group_for(doc_id: int, grouped):
    for group in EXTRAS_GROUPS:
        if doc_id in grouped.get(("extras", group), []):
            return group
    raise RuntimeError(f"extras document has no group: {doc_id}")


def _update_doc_metadata(entries: dict, routes: list[dict]):
    by_id = {d["id"]: d for d in entries["docs"] if d.get("work") == "FHA"}
    for route in routes:
        for chapter in route["chapters"]:
            doc = by_id[chapter["doc"]]
            group = chapter.get("group", "")
            location = route["name"]
            display = chapter["title"]
            doc["title"] = display
            doc.setdefault("meta", {})["剧情分类"] = route["name"]
            doc["meta"]["剧情分组"] = group
            doc["meta"]["FHA目录版本"] = 2
            if chapter.get("main_index") is not None:
                doc["meta"]["主线序号"] = chapter["main_index"]
                doc["meta"]["前置"] = bool(chapter.get("prereq"))
            suffix = _sanitize_path(display) + ".txt"
            parts = ["剧情大全", "FHA", _sanitize_path(route["name"])]
            if group:
                parts.append(_sanitize_path(group))
            parts.append(suffix)
            doc["file"] = "\\".join(parts)


def _append_missing_doc(data_dir: Path, offsets: list, doc_id: int, text: str | None):
    if not text:
        return
    corpus_path = data_dir / "corpus.txt"
    raw = corpus_path.read_bytes()
    prefix = b"" if not raw or raw.endswith(b"\n") else b"\n"
    start = len(raw.decode("utf-8")) + (1 if prefix else 0)
    with corpus_path.open("ab") as handle:
        handle.write(prefix)
        handle.write(text.encode("utf-8"))
    for row in offsets:
        if len(row) == 4 and row[2] == doc_id and row[3] == 0:
            row[0] = start
            row[1] = len(text)
            return


def rebuild(data_dir: Path, split_root: Path, *, write: bool = False):
    entries, story, story_blocks, offsets, main_specs, new_doc_id, new_doc_text, added = _extract_main_specs(data_dir, split_root)
    routes = _build_routes(entries, story, story_blocks, main_specs, split_root)
    work = _existing_work(story)
    work["routes"] = routes
    _update_doc_metadata(entries, routes)
    summary = {
        "main": len(main_specs),
        "daily": sum(len(r["chapters"]) for r in routes if r["name"].startswith("日常事件")),
        "extras": sum(len(r["chapters"]) for r in routes if r["name"] == EXTRAS_ROUTE),
        "routes": [r["name"] for r in routes],
        "extra_groups": {g: sum(1 for c in routes[-1]["chapters"] if c.get("group") == g) for g in EXTRAS_GROUPS},
        "new_doc": new_doc_id if added else 0,
    }
    if write:
        _append_missing_doc(data_dir, offsets, new_doc_id, new_doc_text)
        corpus_text = (data_dir / "corpus.txt").read_text(encoding="utf-8")
        recovered_path = data_dir / "zh_recovered_blocks.json"
        if recovered_path.exists():
            recovered = _load_json(recovered_path)
            recovered["base_corpus_length"] = len(corpus_text)
            _write_json(recovered_path, recovered, pretty=True)
        _write_json(data_dir / "entries.json", entries)
        _write_json(data_dir / "story.json", story, pretty=True)
        _write_json(data_dir / "story_blocks.json", story_blocks)
        _write_json(data_dir / "offsets.json", offsets)
    return summary, entries, story, story_blocks, offsets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--split-root", type=Path, default=DEFAULT_SPLIT_ROOT)
    args = parser.parse_args()
    summary, *_ = rebuild(args.data_dir, args.split_root, write=args.apply)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()














