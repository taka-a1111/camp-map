"""キャンプ場の近くの日帰り入浴施設（温泉・銭湯）を集める。GitHub Actions で実行する。
1) OpenStreetMap の amenity=public_bath を都道府県ごとに取得
2) 各キャンプ場から近い順に3件（30km以内）を選び、その施設の公式サイトを取得（料金の読み取り用）

python scripts/fetch_onsen.py → crawl_out/onsen_osm.json, crawl_out/onsen_pages.jsonl.gz
"""
import gzip
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crawl_pages  # noqa: E402
from crawl_pages import allowed, crawl_one  # noqa: E402

# 入浴施設では「入浴」「日帰り」「営業時間」のページも料金が載っていることが多い
crawl_pages.LINK_WORDS = re.compile(r"料金|利用料|入浴|日帰り|営業時間|ご利用|利用案内|施設案内|price|fee|guide|spa|bath", re.I)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "crawl_out"
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
PREFS = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県",
         "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
         "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県",
         "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]
NEAR_KM = 30
PER_CAMP = 3
SKIP_NAME = re.compile(r"足湯|手湯|飲泉|源泉$|泉源|露天風呂跡|(男|女)湯$")


def dist_km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def query(code):
    q = f"""[out:json][timeout:180];
area["ISO3166-2"="{code}"]->.p;
nwr["amenity"="public_bath"](area.p);
out center tags;"""
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(5):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "camp-map/1.0 (github.com/taka-a1111/camp-map)"})
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(20 * (attempt + 1))
    print("失敗", code, last, flush=True)
    return None


def main():
    OUT.mkdir(exist_ok=True)
    camps = json.loads((ROOT / "data" / "camps.json").read_text(encoding="utf-8"))["camps"]
    want = sorted({c["pref"] for c in camps}, key=PREFS.index)
    rows = []
    for pref in want:
        code = f"JP-{PREFS.index(pref) + 1:02d}"
        d = query(code)
        if d is None:
            continue
        k = 0
        for e in d.get("elements", []):
            t = e.get("tags", {})
            c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
            name = t.get("name:ja") or t.get("name") or ""
            if c.get("lat") is None or not name or SKIP_NAME.search(name):
                continue
            if t.get("access") in ("private", "no", "customers") or t.get("bath:type") in ("foot_bath", "foot", "hand"):
                continue
            rows.append({"osm": f"{e['type']}/{e['id']}", "pref": pref, "lat": c["lat"], "lon": c["lon"], "name": name, "tags": t})
            k += 1
        print(pref, k, flush=True)
        time.sleep(5)
    (OUT / "onsen_osm.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print("入浴施設", len(rows), flush=True)

    # キャンプ場ごとに近い施設を選ぶ（公式サイトを取得する対象）
    pick = set()
    for c in camps:
        near = []
        for i, o in enumerate(rows):
            if abs(o["lat"] - c["lat"]) > 0.3 or abs(o["lon"] - c["lng"]) > 0.4:
                continue
            d = dist_km((c["lat"], c["lng"]), (o["lat"], o["lon"]))
            if d <= NEAR_KM:
                near.append((d, i))
        for _, i in sorted(near)[:PER_CAMP]:
            pick.add(i)
    items = []
    for i in sorted(pick):
        t = rows[i]["tags"]
        u = t.get("website") or t.get("contact:website") or t.get("url") or ""
        if u and not u.startswith("http"):
            u = "http://" + u
        if u and allowed(u):
            items.append((rows[i]["osm"], rows[i]["name"], [u]))
    print(f"キャンプ場の近くの施設 {len(pick)}件、うち公式サイトあり {len(items)}件", flush=True)
    n = 0
    with gzip.open(OUT / "onsen_pages.jsonl.gz", "wt", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=8) as ex:
        for rec in ex.map(crawl_one, items):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if n % 50 == 0:
                print(f"  {n}/{len(items)}", flush=True)
    (OUT / "onsen_picked.json").write_text(json.dumps(sorted(rows[i]["osm"] for i in pick)), encoding="utf-8")
    print("完了", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
