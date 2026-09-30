"""地図に載せる日帰り入浴施設の一覧 data/onsens.json を作る。
- data/onsen_osm.json      ：OpenStreetMap の入浴施設（scripts/fetch_onsen.py）
- data/onsen_tourism.json  ：県の観光協会サイトの入浴施設ページ（scripts/fetch_onsen_tourism.py）
                              OSM に無い施設はここから追加し、料金も文字パターンで読み取る
- data/onsen_manual.json   ：公式・自治体などで確認した料金（手入力。自動の値より優先）
- data/onsen_extra.json    ：市町村ごとの調査・県の温泉協会の一覧・利用者の情報で見つけた施設（名前・住所・料金）
                              source_kind が official（公式・自治体・温泉協会・観光協会）なら確認済み、agg（旅行サイト等）なら参考扱い
観光協会ページに緯度経度が無い施設は、住所を国土地理院の住所検索で位置にする（data/onsen_geocode_cache.json に保存）。

python scripts/build_onsens.py [--no-geocode]
"""
import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from onsen_fee_parse import extract, keys, km, same  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = D / "onsens.json"
GEO = D / "onsen_geocode_cache.json"
WEEK = {"Mo": "月", "Tu": "火", "We": "水", "Th": "木", "Fr": "金", "Sa": "土", "Su": "日", "PH": "祝"}


def load(name, default):
    p = D / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def clean(n):
    return re.sub(r"\s*[;；]\s*", " ", n or "").strip()


def osm_hours(h):
    if not h or len(h) > 60:
        return ""
    h = re.sub(r"\b(Mo|Tu|We|Th|Fr|Sa|Su|PH)\b", lambda m: WEEK[m.group(1)], h)
    return h.replace("off", "休").replace("-", "〜").replace("; ", "・").replace(",", "・") + "（地図データの情報）"


def geocode(addr, pref, cache, enabled):
    a = unicodedata.normalize("NFKC", addr or "")
    a = re.sub(r"〒?\d{3}-?\d{4}", "", a)
    a = re.sub(r"[（(].*?[）)]", "", a).split(" ")[0].strip()
    if not a:
        return None
    if not a.startswith(pref):
        a = pref + re.sub(r"^.{2,3}?[都道府県]", "", a)
    if a in cache:
        return cache[a]
    if not enabled:
        return None
    try:
        req = urllib.request.Request("https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(a),
                                     headers={"User-Agent": "camp-map/1.0 (github.com/taka-a1111/camp-map)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    time.sleep(0.3)
    best = None
    for x in res or []:
        t = x["properties"]["title"]
        if not t.startswith(pref):
            continue
        lon, lat = x["geometry"]["coordinates"]
        # 町名（字）まで一致したものだけ使う（市町村の中心だと数km〜数十kmずれるため）
        level = len(t) - len(pref)
        if best is None or level > best[2]:
            best = (round(lat, 6), round(lon, 6), level, t)
    val = [best[0], best[1]] if best and re.search(r"[市町村区].+", best[3][len(pref):]) else None
    cache[a] = val
    return val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-geocode", action="store_true")
    a = ap.parse_args()
    osm = load("onsen_osm.json", [])
    manual = load("onsen_manual.json", {})
    pages = load("onsen_tourism.json", {"pages": {}})["pages"]
    cache = load("onsen_geocode_cache.json", {})
    extra_list = load("onsen_extra.json", [])

    out = []
    for r in osm:
        t = r.get("tags", {})
        o = {"id": r["osm"].replace("/", "-"), "name": clean(r["name"]), "pref": r["pref"], "lat": r["lat"], "lng": r["lon"], "src": "osm"}
        bt = t.get("bath:type")
        if bt in ("sento", "super_sento"):
            o["type"] = "銭湯" if bt == "sento" else "スーパー銭湯"
        u = t.get("website") or t.get("contact:website") or t.get("url") or ""
        if u:
            o["url"] = u if u.startswith("http") else "http://" + u
        h = osm_hours(t.get("opening_hours"))
        if h:
            o["hours"] = h
        out.append(o)

    # 観光協会のページを施設に結び付ける（同じ県・名前が一致・位置がわかるなら3km以内、候補が1つだけのとき）
    okeys = [keys(o["name"]) for o in out]
    by_pref = {}
    for i, o in enumerate(out):
        by_pref.setdefault(o["pref"], []).append(i)
    linked, extra = {}, []
    for url, p in pages.items():
        pk = keys(p["name"])
        if not pk:
            continue
        pos = [p["lat"], p["lng"]] if p.get("lat") is not None else geocode(p.get("address"), p["pref"], cache, not a.no_geocode)
        cand = [i for i in by_pref.get(p["pref"], []) if same(okeys[i], pk)]
        if pos:
            cand = [i for i in cand if km((out[i]["lat"], out[i]["lng"]), pos) <= 3]
        if len(cand) == 1:
            linked.setdefault(cand[0], []).append(url)
        elif not cand and pos:
            extra.append((url, p, pos))

    # 地図データに無い施設を観光協会のページから追加（同じ施設の重複ページはまとめる）
    added = []
    for url, p, pos in extra:
        pk = keys(p["name"])
        if any(q["pref"] == p["pref"] and same(keys(q["name"]), pk) and km((q["lat"], q["lng"]), pos) <= 3 for q in added):
            continue
        o = {"id": "t-" + hashlib.md5(url.encode()).hexdigest()[:10], "name": p["name"], "pref": p["pref"], "lat": pos[0], "lng": pos[1],
             "src": "tourism", "page": url, "site": p["site"]}
        if p.get("official"):
            o["url"] = p["official"]
        if p.get("hours"):
            o["hours"] = p["hours"][:50]
        o["_page"] = url
        added.append(o)
    for i, urls in linked.items():
        if len(urls) == 1:
            out[i]["_page"] = urls[0]
            out[i]["page"] = urls[0]
            out[i]["site"] = pages[urls[0]]["site"]
    out += added

    # 調査で見つけた施設：既存の施設と同じなら料金などを補い、無ければ住所の位置で追加する
    n_extra = 0
    for x in extra_list:
        xk = keys(x["name"])
        pos = geocode(x.get("address"), x["pref"], cache, not a.no_geocode)
        cand = [o for o in out if o["pref"] == x["pref"] and same(keys(o["name"]), xk)]
        if pos:
            cand = [o for o in cand if km((o["lat"], o["lng"]), pos) <= 3]
        if len(cand) > 1:
            continue
        if cand:
            o = cand[0]
        elif pos:
            o = {"id": "x-" + hashlib.md5((x["pref"] + x["name"]).encode()).hexdigest()[:10], "name": x["name"], "pref": x["pref"],
                 "lat": pos[0], "lng": pos[1], "src": "extra"}
            if x.get("kind") in ("銭湯", "スーパー銭湯"):
                o["type"] = x["kind"]
            out.append(o)
            n_extra += 1
        else:
            continue
        if x.get("url") and not o.get("url"):
            o["url"] = x["url"]
        if x.get("adult") is not None and o.get("adult") is None and not manual.get(o["id"].replace("-", "/", 1), {}).get("adult"):
            o["adult"] = x["adult"]
            if x.get("child") is not None:
                o["child"], o["child_label"] = x["child"], x.get("child_label", "")
            o["fee_url"] = x.get("source_url", "")
            o["fee_src"] = "ref" if x.get("source_kind") == "agg" else "checked"

    n_auto = n_manual = 0
    for o in out:
        pu = o.pop("_page", None)
        p = pages.get(pu) if pu else None
        if p:
            if not o.get("url") and p.get("official"):
                o["url"] = p["official"]
            if p.get("hours") and (not o.get("hours") or o["hours"].endswith("（地図データの情報）")):
                o["hours"] = p["hours"][:50]
        m = manual.get(o["id"].replace("-", "/", 1))
        if m:
            for k, v in m.items():
                if k == "hours" and not v:
                    continue
                o[k] = v
            if m.get("adult") is not None:
                n_manual += 1
                continue
        if p and o.get("adult") is None and o.get("fee_src") not in ("checked", "ref"):
            r = extract(p.get("lines", []))
            if r:
                o.update(r)
                o["fee_src"] = "auto"
                o["fee_site"] = p["site"]
                o["fee_url"] = pu
                n_auto += 1

    GEO.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    OUT.write_text(json.dumps({"generated_from": "OpenStreetMap contributors (ODbL) amenity=public_bath/leisure=spa・県の観光協会サイト・公式/自治体ページ",
                               "onsens": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"入浴施設 {len(out)}件（地図データ {len(osm)}・観光協会サイトから追加 {len(added)}・調査から追加 {n_extra}）")
    print(f"観光協会ページ {len(pages)}件のうち地図データの施設と結び付いたもの {len(linked)}件")
    print(f"料金あり {n_manual + n_auto}件（確認済み {n_manual}・観光協会ページから自動 {n_auto}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
