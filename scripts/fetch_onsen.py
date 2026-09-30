"""日帰り入浴できる施設（温泉・スーパー銭湯・銭湯など）を OpenStreetMap から都道府県ごとに集める。GitHub Actions で毎月実行する。
対象：amenity=public_bath、leisure=spa（足湯・手湯・宿泊者専用は除く）
取得に失敗した都道府県は前回の結果を残す。

python scripts/fetch_onsen.py → data/onsen_osm.json
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "onsen_osm.json"
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
PREFS = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県",
         "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
         "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県",
         "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]
SKIP_NAME = re.compile(r"足湯|手湯|飲泉|源泉$|泉源|露天風呂跡|(男|女)湯$|廃業|閉業|閉館")
KEEP_TAGS = ("website", "contact:website", "url", "opening_hours", "bath:type", "phone", "contact:phone", "charge", "fee",
             "addr:province", "addr:city", "addr:quarter", "addr:neighbourhood", "addr:block_number", "addr:full")


def query(code):
    q = f"""[out:json][timeout:180];
area["ISO3166-2"="{code}"]->.p;
(nwr["amenity"="public_bath"](area.p);nwr["leisure"="spa"](area.p););
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
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    rows = []
    for i, pref in enumerate(PREFS, 1):
        d = query(f"JP-{i:02d}")
        if d is None:
            keep = [r for r in old if r["pref"] == pref]
            rows += keep
            print(pref, "前回の結果を使用", len(keep), flush=True)
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
            rows.append({"osm": f"{e['type']}/{e['id']}", "pref": pref, "lat": round(c["lat"], 6), "lon": round(c["lon"], 6),
                         "name": name, "tags": {k2: t[k2] for k2 in KEEP_TAGS if k2 in t}})
            k += 1
        print(pref, k, flush=True)
        time.sleep(5)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("入浴施設", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
