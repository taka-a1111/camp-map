"""OpenStreetMap（Overpass API）から対象県のキャンプ場を取得して data/osm_raw.json に保存する。

GitHub Actions から実行する想定（ローカルでも python scripts/fetch_osm.py で動く）。
対象県を増やすときは PREFS に ISO3166-2 コードと県名を足す。
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PREFS = {
    "JP-23": "愛知県",
    "JP-21": "岐阜県",
    "JP-20": "長野県",
    "JP-22": "静岡県",
    "JP-24": "三重県",
}

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

OUT = Path(__file__).resolve().parent.parent / "data" / "osm_raw.json"


def query_pref(code: str) -> dict:
    q = f"""[out:json][timeout:120];
area["ISO3166-2"="{code}"]->.p;
nwr["tourism"="camp_site"](area.p);
out center tags;"""
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": "camp-map/1.0 (github.com/taka-a1111/camp-map)"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass取得に失敗: {code}: {last}")


def main() -> int:
    rows = []
    stamp = ""
    for code, pref in PREFS.items():
        try:
            d = query_pref(code)
        except RuntimeError as e:
            # Overpass が混雑して取れないときは、前回取得したデータのまま公開を続ける
            if OUT.exists():
                print(f"::warning::{e}。前回取得したデータ（{OUT.name}）をそのまま使います")
                return 0
            raise
        stamp = d.get("osm3s", {}).get("timestamp_osm_base", stamp)
        n = 0
        for e in d.get("elements", []):
            c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
            if c.get("lat") is None:
                continue
            rows.append({
                "osm": f"{e['type']}/{e['id']}",
                "pref": pref,
                "lat": round(c["lat"], 6),
                "lon": round(c["lon"], 6),
                "tags": e.get("tags", {}),
            })
            n += 1
        print(f"{pref}: {n}件")
        time.sleep(5)
    if len(rows) < 50:
        print("取得件数が少なすぎるため保存しません", file=sys.stderr)
        if OUT.exists():
            print(f"::warning::前回取得したデータ（{OUT.name}）をそのまま使います")
            return 0
        return 1
    OUT.write_text(json.dumps({"timestamp_osm_base": stamp, "elements": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"合計 {len(rows)}件 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
