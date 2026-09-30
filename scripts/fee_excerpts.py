"""キャンプ場の公式・自治体ページの本文（scripts/crawl_pages.py の結果）から、料金が書かれた行を抜き出して data/fee_text.json に保存する。
Claude（AI）は使わず、文字パターンで「円」「無料」を含む料金らしい行を拾うだけ。総額の計算には使わず、詳細画面にそのまま載せる。

python scripts/fee_excerpts.py [crawl_out/pages.jsonl.gz]
"""
import datetime as dt
import gzip
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fee_text.json"
FEE_WORD = re.compile(r"料金|利用料|使用料|施設料|入場|入村|管理費|サイト|区画|フリー|オート|大人|小人|子供|子ども|こども|小学生|中学生|幼児|"
                      r"1泊|１泊|一泊|宿泊|テント|タープ|持込|持ち込み|車|駐車|バイク|バンガロー|コテージ|ケビン|キャビン|トレーラー|グランピング|"
                      r"デイキャンプ|日帰り|ゴミ|ごみ|薪|電源|シャワー|チェックイン|平日|休日|土曜|繁忙期|ハイシーズン|通常期")
NOT_FEE = re.compile(r"泊[0-9０-９一二三]食|メニュー|ランチ|定食|ドリンク|ビール|ソフトクリーム|ジェラート|コーヒー|弁当|販売|セール|送料|ポイント|クーポン|会員登録|"
                     r"求人|時給|月給|アルバイト|募集|お土産|グッズ|税抜価格|カート|ふるさと納税|特典|キャンペーン|プレゼント|実質|ランキング|おすすめ|選[0-9０-９]*$|[0-9０-９]+選|最新|人気の理由|足湯")
YEN = re.compile(r"[0-9０-９][0-9０-９,，]*\s*円|無料")
MAX_LINES = 12


def pick_lines(pages):
    out, seen = [], set()
    url = ""
    for p in pages:
        for raw in (p.get("text") or "").split("\n"):
            l = re.sub(r"\s*\|\s*", "　", unicodedata.normalize("NFKC", raw)).strip("　 ")
            l = re.sub(r"\s+", " ", l)
            if not (4 <= len(l) <= 140) or not YEN.search(l) or not FEE_WORD.search(l) or NOT_FEE.search(l):
                continue
            if l in seen:
                continue
            seen.add(l)
            out.append(l)
            url = url or p.get("url", "")
            if len(out) >= MAX_LINES:
                return out, url
    return out, url


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "crawl_out" / "pages.jsonl.gz"
    camps = json.loads((ROOT / "data" / "camps.json").read_text(encoding="utf-8"))["camps"]
    by_id = {c["id"]: c for c in camps}
    by_name = defaultdict(list)
    for c in camps:
        by_name[c["name"]].append(c)
    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    today = dt.date.today().isoformat()
    n = 0
    with gzip.open(src, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            c = by_id.get(r["id"])
            if not c or c["name"] != r["name"]:
                cs = by_name.get(r["name"], [])
                c = cs[0] if len(cs) == 1 else None
            if not c:
                continue
            ok_pages = [p for p in r["pages"] if p.get("text")]
            if not ok_pages:
                continue  # 取得できなかったときは前回の抜き出しを残す
            lines, url = pick_lines(ok_pages)
            key = f"{c['pref']}|{c['name']}"
            if lines:
                store[key] = {"lines": lines, "url": url, "fetched": today}
                n += 1
            else:
                store.pop(key, None)
    OUT.write_text(json.dumps(store, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"料金の記載を抜き出したキャンプ場 {n}件（保存 計 {len(store)}件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
