"""OpenStreetMap に登録されている日本国内のキャンプ場を都道府県ごとに取得する（全国の候補の位置合わせと、料金なし fee=no の候補）。
python scripts/fetch_osm_free.py → crawl_out/osm_camps_japan.json
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "crawl_out"
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def query(code):
    q = f"""[out:json][timeout:180];
area["ISO3166-2"="{code}"]->.p;
nwr["tourism"="camp_site"](area.p);
out center tags;"""
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(4):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "camp-map/1.0 (github.com/taka-a1111/camp-map)"})
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(20 * (attempt + 1))
    print("失敗", code, last, flush=True)
    return {"elements": []}


def main():
    OUT.mkdir(exist_ok=True)
    rows = []
    for n in range(1, 48):
        code = f"JP-{n:02d}"
        d = query(code)
        k = 0
        for e in d.get("elements", []):
            c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
            if c.get("lat") is None:
                continue
            rows.append({"osm": f"{e['type']}/{e['id']}", "iso": code, "lat": c["lat"], "lon": c["lon"], "tags": e.get("tags", {})})
            k += 1
        print(code, k, flush=True)
        time.sleep(5)
    (OUT / "osm_camps_japan.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print("件数", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
