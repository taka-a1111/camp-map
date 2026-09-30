"""抜け漏れ確認用の候補リストを集める（無料・格安の野営地まとめ「旅人茶屋」の都道府県別ページ）。
全都道府県のページを見つけて、各野営地の詳細ページから名前・所在地・利用料・情報の時期を取り出す。
名前・所在地・料金の記載を候補として使い、公式ページでの確認や注意書き付きの掲載に回す。

python scripts/fetch_checklists.py
出力：crawl_out/checklist_tabinchuya.jsonl（ページ本文）と crawl_out/tabinchuya_entries.json（取り出した項目）
"""
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_pages import fetch, page_text  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "crawl_out"
BASE = "https://camp.tabinchuya.com/"
PREF_NAMES = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県",
              "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
              "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県",
              "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]
DELAY = 2.0


def get_text(url):
    html, _ = fetch(url)
    return page_text(html)


def parse_entries(text, pref, url):
    lines = [l.strip() for l in text.split("\n")]
    out = []
    for i, l in enumerate(lines):
        if not l.startswith("所在地：") or i == 0:
            continue
        name = lines[i - 1]
        if name.startswith("座 標") or not name:
            continue
        block = lines[i + 1:i + 25]
        fee = next((x for x in block[:4] if x.startswith("利用料")), "")
        date = next((x for x in block if x.startswith("※20")), "")
        ground = next((x for x in block if x.startswith("地 面") or x.startswith("地面")), "")
        out.append({"pref": pref, "name": re.sub(r"（Google ?map）", "", name).strip(), "loc": l[4:], "fee": fee,
                    "date": date, "ground": ground, "url": url})
    return out


def main():
    OUT.mkdir(exist_ok=True)
    top_text, top_links = get_text(BASE)
    # 都道府県ページ（camp.tabinchuya.com/xxx/）を集める。地方ページ経由で見つかる場合もあるので2段階で探す
    cand = set()
    for href, _ in top_links:
        full = urllib.parse.urljoin(BASE, href or "")
        if re.match(re.escape(BASE) + r"[a-z]+/$", full):
            cand.add(full)
    pref_pages = {}
    visited = set()
    queue = sorted(cand)
    while queue:
        u = queue.pop(0)
        if u in visited:
            continue
        visited.add(u)
        time.sleep(DELAY)
        try:
            t, links = get_text(u)
        except Exception as e:  # noqa: BLE001
            print("失敗", u, e, flush=True)
            continue
        head = t[:200]
        pref = next((p for p in PREF_NAMES if head.find(p + "のキャンプ") >= 0), None)
        if pref:
            pref_pages[pref] = (u, t, links)
        else:
            for href, _ in links:
                full = urllib.parse.urljoin(u, href or "")
                if re.match(re.escape(BASE) + r"[a-z]+/$", full) and full not in visited:
                    queue.append(full)
    print("都道府県ページ", len(pref_pages), sorted(pref_pages), flush=True)
    entries = []
    with open(OUT / "checklist_tabinchuya.jsonl", "w", encoding="utf-8") as f:
        for pref, (u, t, links) in pref_pages.items():
            f.write(json.dumps({"kind": "index", "pref": pref, "url": u, "text": t[:30000]}, ensure_ascii=False) + "\n")
            entries += parse_entries(t, pref, u)
            details = []
            for href, _ in links:
                full = urllib.parse.urljoin(u, href or "")
                if full.startswith(u) and full.endswith(".html") and full not in details:
                    details.append(full)
            for d in details:
                time.sleep(DELAY)
                try:
                    dt, _ = get_text(d)
                except Exception as e:  # noqa: BLE001
                    print("失敗", d, e, flush=True)
                    continue
                f.write(json.dumps({"kind": "detail", "pref": pref, "url": d, "text": dt[:6000]}, ensure_ascii=False) + "\n")
                entries += parse_entries(dt, pref, d)
            print(pref, "詳細", len(details), flush=True)
    seen, uniq = set(), []
    for e in entries:
        k = (e["pref"], e["name"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    (OUT / "tabinchuya_entries.json").write_text(json.dumps(uniq, ensure_ascii=False, indent=0), encoding="utf-8")
    print("項目", len(uniq))
    return 0


if __name__ == "__main__":
    sys.exit(main())
