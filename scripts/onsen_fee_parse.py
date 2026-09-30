"""入浴施設の名前の突き合わせと、ページの文章から「大人○○円」「小学生○○円」を読み取る部品（Claude・AIは使わない）。
scripts/build_onsens.py から使う。読み取りに自信がないもの（料金の候補が3つ以上、宿泊や食事の料金と混ざっている等）は None を返す。
"""
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONSENS = ROOT / "data" / "onsens.json"
PAGES = ROOT / "data" / "onsen_tourism.json"
AUTO_KEYS = ("adult", "child", "child_label", "fee_url", "fee_quote", "fee_src", "fee_site", "fee_note_auto")

ADULT = r"(大人|おとな|一般|中学生以上|中学生～|高校生以上|13歳以上|12歳以上)"
CHILD = r"(小学生以下|小学生|小人|子供|子ども|こども|児童)(?!未満)"
PAREN = r"(?:[（(【\[][^）)】\]]{0,20}[）)】\]])?"
NUM = r"([0-9][0-9,]{1,5})\s*円"
EXCL = re.compile(r"宿泊|1泊|一泊|泊\d|食事|ランチ|定食|コース|プラン|貸切|貸し切り|家族風呂|個室|回数券|綴り|年間|定期券|駐車|レンタル|"
                  r"タオル|マッサージ|エステ|岩盤浴|入湯税|ジェラート|ドリンク|メニュー|体験|ツアー|海水浴|プール|リフト|ゴンドラ|入園|"
                  r"キャンプ|テント|サイト|バンガロー|コテージ|駐輪")
GENERIC = {"温泉", "の湯", "日帰り温泉", "天然温泉", "日帰り入浴", "入浴施設", "温泉施設", "スパ", "銭湯", "足湯"}


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s・･.\-‐－—~〜～「」『』【】\"'’“”]", "", s)


def keys(name):
    n = unicodedata.normalize("NFKC", name or "")
    out = {norm(n), norm(re.sub(r"[（(].*?[）)]", "", n))}
    out |= {norm(x) for x in re.findall(r"[（(](.*?)[）)]", n)}
    out |= {norm(x) for x in re.split(r"[\s　]+", n) if len(norm(x)) >= 3}
    return {k for k in out if len(k) >= 3 and k not in GENERIC}


def same(a, b):
    for x in a:
        for y in b:
            if x == y:
                return True
            s, l = (x, y) if len(x) <= len(y) else (y, x)
            if len(s) >= 4 and s in l:
                return True
    return False


def km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def yen(s):
    return int(s.replace(",", ""))


def extract(lines):
    """料金の行から大人・子供の入浴料を読む。読めなければ None。"""
    L = [unicodedata.normalize("NFKC", l) for l in lines]
    # 「料金」だけの見出し行の次の行、ラベルと金額が別の行に分かれている場合をつなぐ
    joined = []
    for i, l in enumerate(L):
        if re.fullmatch(r"[【\[(（]?(?:" + ADULT + "|" + CHILD + r")" + PAREN + r"[^0-9円]{0,12}", l) and i + 1 < len(L):
            joined.append(l + " " + L[i + 1])
        else:
            joined.append(l)
    adults, children, quote = [], [], ""
    for l in joined:
        if EXCL.search(l) and not re.search(r"入浴|入館|日帰り", l):
            continue
        for m in re.finditer(ADULT + PAREN + r"(?:(?!小人|小学|子供|子ども|こども|児童|幼児|未就学)[^0-9円。]){0,15}?" + NUM, l):
            v = yen(m.group(2))
            if 100 <= v <= 3000:
                adults.append(v)
                if not quote:
                    quote = l
        for m in re.finditer(CHILD + PAREN + r"(?:(?!大人|一般|中学生以上|高校生以上|幼児|未就学)[^0-9円。]){0,15}?(?:" + NUM + r"|(無料))", l):
            v = 0 if m.group(3) else yen(m.group(2))
            if v <= 2000:
                children.append((v, m.group(1)))
    uniq = sorted(set(adults))
    if not uniq or len(uniq) > 2:
        return None
    r = {"adult": uniq[0], "fee_quote": quote[:80]}
    if len(uniq) == 2:
        r["fee_note_auto"] = f"曜日や時間帯で{uniq[1]:,}円の場合もあり"
    cu = sorted({v for v, _ in children})
    if len(cu) == 1 and cu[0] <= r["adult"]:
        r["child"] = cu[0]
        r["child_label"] = next(lab for v, lab in children if v == cu[0])
    return r
