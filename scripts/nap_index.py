"""なっぷ（nap-camp.com）の掲載ページと施設名の対応表 data/nap_index.json を更新する。
詳細画面の「なっぷ」ボタンのリンク先に使う。robots.txt の Crawl-delay（30秒）を守って、名前が未取得のページだけ取りに行く。

python scripts/nap_index.py [--max N]
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "nap_index.json"
PREFS = {"aichi": "愛知県", "gifu": "岐阜県", "nagano": "長野県", "shizuoka": "静岡県", "mie": "三重県"}
UA = "camp-map/1.0 (+https://github.com/taka-a1111/camp-map)"
DELAY = 31


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(400_000).decode("utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=600)
    a = ap.parse_args()
    index = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []
    known = {x["id"] for x in index}
    listed = []
    try:
        sm = get("https://www.nap-camp.com/sitemap-dynamic-campsite.xml")
        listed = sorted(set(re.findall(r"<loc>https://www\.nap-camp\.com/(%s)/(\d+)/</loc>" % "|".join(PREFS), sm)))
        print(f"サイトマップ {len(sm)}文字", flush=True)
    except Exception as e:  # noqa: BLE001
        print("サイトマップ取得失敗", e, flush=True)
    listed_file = ROOT / "data" / "nap_listed.json"
    if listed:
        listed_file.write_text(json.dumps([f"{p}/{i}" for p, i in listed], indent=0), encoding="utf-8")
    elif listed_file.exists():
        # 取得できなかったときは前回の一覧を使う（一覧を空にして対応表を消さないため）
        listed = [tuple(x.split("/")) for x in json.loads(listed_file.read_text(encoding="utf-8"))]
        print("前回の掲載一覧を使用", len(listed), flush=True)
    if not listed:
        print("掲載一覧がないため中止")
        return 1
    listed_ids = {i for _, i in listed}
    todo = [(p, i) for p, i in listed if i not in known][: a.max]
    print(f"掲載 {len(listed)}件・未取得 {len(todo)}件", flush=True)
    fails = 0
    for n, (slug, cid) in enumerate(todo, 1):
        time.sleep(DELAY)
        url = f"https://www.nap-camp.com/{slug}/{cid}"
        try:
            html = get(url)
        except Exception as e:  # noqa: BLE001
            print("失敗", url, e, flush=True)
            fails += 1
            if fails >= 5 and fails == n:
                print("続けて失敗したため中止（アクセスが拒否されている可能性）")
                break
            continue
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        name = re.split(r"[｜|]", m.group(1))[0].strip() if m else ""
        addr = ""
        am = re.search(r"(%s)[^<\"]{2,60}" % PREFS[slug], html)
        if am:
            addr = am.group(0).strip()
        if name:
            name = re.sub(r"の口コミ・予約.*$", "", name).strip()
            index.append({"pref": PREFS[slug], "id": cid, "name": name, "addr": addr, "url": url})
        if n % 20 == 0:
            INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"  {n}/{len(todo)}", flush=True)
    # 掲載が終わったページは外す（一覧が十分に取れたときだけ）
    if len(listed_ids) > 500:
        index = [x for x in index if x["id"] in listed_ids]
    index.sort(key=lambda x: (x["pref"], int(x["id"])))
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=0), encoding="utf-8")
    print("完了", len(index))
    return 0


if __name__ == "__main__":
    sys.exit(main())
