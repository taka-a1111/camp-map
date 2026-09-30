"""抜け漏れ確認用の候補リストを集める（無料・格安の野営地まとめ「旅人茶屋」の県別ページ）。
名前・所在地・料金の記載を候補として使い、公式ページでの確認や注意書き付きの掲載に回す。

python scripts/fetch_checklists.py
出力：crawl_out/checklist_tabinchuya.jsonl
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
PREFS = {"aiti": "愛知県", "gifu": "岐阜県", "nagano": "長野県", "shizuoka": "静岡県", "mie": "三重県"}
BASE = "https://camp.tabinchuya.com/"


def main():
    OUT.mkdir(exist_ok=True)
    n = 0
    with open(OUT / "checklist_tabinchuya.jsonl", "w", encoding="utf-8") as f:
        for slug, pref in PREFS.items():
            index = BASE + slug + "/"
            try:
                html, _ = fetch(index)
            except Exception as e:  # noqa: BLE001
                print("失敗", index, e)
                continue
            text, links = page_text(html)
            f.write(json.dumps({"kind": "index", "pref": pref, "url": index, "text": text[:30000]}, ensure_ascii=False) + "\n")
            details = []
            for href, label in links:
                full = urllib.parse.urljoin(index, href or "")
                if re.match(re.escape(BASE + slug + "/") + r"[^/]+\.html$", full) and full not in details:
                    details.append(full)
            print(pref, "詳細ページ", len(details), flush=True)
            for url in details:
                time.sleep(1.5)
                try:
                    html, _ = fetch(url)
                except Exception as e:  # noqa: BLE001
                    print("  失敗", url, e)
                    continue
                t, _ = page_text(html)
                f.write(json.dumps({"kind": "detail", "pref": pref, "url": url, "text": t[:6000]}, ensure_ascii=False) + "\n")
                n += 1
    print("完了", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
