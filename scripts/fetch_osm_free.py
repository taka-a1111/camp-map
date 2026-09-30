"""OpenStreetMap で「料金なし（fee=no）」とされている日本国内のキャンプ場を取得する（無料キャンプ場の候補）。
python scripts/fetch_osm_free.py → crawl_out/osm_free_japan.json
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "crawl_out"
Q = """[out:json][timeout:300];
area["ISO3166-1"="JP"][admin_level=2]->.jp;
nwr["tourism"="camp_site"]["fee"="no"](area.jp);
out center tags;"""


def main():
    OUT.mkdir(exist_ok=True)
    body = urllib.parse.urlencode({"data": Q}).encode()
    req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=body,
                                 headers={"User-Agent": "camp-map/1.0 (github.com/taka-a1111/camp-map)"})
    with urllib.request.urlopen(req, timeout=400) as r:
        d = json.loads(r.read().decode("utf-8"))
    rows = []
    for e in d.get("elements", []):
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        if c.get("lat") is None:
            continue
        rows.append({"osm": f"{e['type']}/{e['id']}", "lat": c["lat"], "lon": c["lon"], "tags": e.get("tags", {})})
    (OUT / "osm_free_japan.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print("件数", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
