"""data/coverage.json の住所を国土地理院のジオコーダ（住所検索API）で緯度経度に変換し、
data/geocode_cache.json に保存する。一度調べた住所は再問い合わせしない。

python scripts/geocode.py
"""
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVER = ROOT / "data" / "coverage.json"
CACHE = ROOT / "data" / "geocode_cache.json"
API = "https://msearch.gsi.go.jp/address-search/AddressSearch?q="

# 日本のおおまかな範囲（外れた結果は捨てる）
BBOX = (20.0, 122.0, 46.0, 154.0)


def clean_address(a: str) -> str:
    a = unicodedata.normalize("NFKC", a or "")
    a = re.sub(r"[（(].*?[）)]", "", a)          # 括弧書きを除く
    a = re.sub(r"〒?\d{3}-?\d{4}", "", a)        # 郵便番号
    a = a.split(" ")[0].split("　")[0]            # 空白以降（施設名・補足）を除く
    a = re.sub(r"(番地|番)の?", "-", a)
    a = re.sub(r"-+$", "", a.strip())
    return a.strip()


def query(q: str):
    url = API + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": "camp-map/1.0 (github.com/taka-a1111/camp-map)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def pick(results, pref: str, addr: str):
    best = None
    for r in results or []:
        title = r.get("properties", {}).get("title", "")
        lon, lat = r["geometry"]["coordinates"]
        if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
            continue
        if pref and not title.startswith(pref):
            continue
        score = 0
        a = addr.replace(pref, "", 1)
        t = title.replace(pref, "", 1)
        while score < min(len(a), len(t)) and a[score] == t[score]:
            score += 1
        if best is None or score > best[0]:
            best = (score, lat, lon, title)
    return best


def main() -> int:
    cover = json.loads(COVER.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = []
    for c in cover:
        if c.get("status") == "closed":
            continue
        addr = clean_address(c.get("address", ""))
        if addr and not addr.startswith(c["pref"]):
            addr = c["pref"] + addr
        key = addr or ""
        if key and key not in cache:
            todo.append((key, c["pref"]))
    todo = list(dict.fromkeys(todo))
    print(f"新しく調べる住所 {len(todo)}件（キャッシュ {len(cache)}件）")
    def work(item):
        addr, pref = item
        err = None
        for attempt in range(3):
            try:
                res = query(addr)
                break
            except Exception as e:  # noqa: BLE001
                err = e
                time.sleep(3 * (attempt + 1))
        else:
            print(f"  失敗 {addr}: {err}")
            return addr, "error"
        time.sleep(0.3)
        b = pick(res, pref, addr)
        if not b:
            return addr, None
        score, lat, lon, title = b
        # 一致した部分に番地の数字が含まれれば「住所」、市町村・字までなら「地域」扱い
        matched = title.replace(pref, "", 1)
        level = "address" if re.search(r"\d", matched) else "area"
        return addr, {"lat": round(lat, 6), "lng": round(lon, 6), "title": title, "level": level}

    # 同時に3件まで問い合わせる（国土地理院のサーバーに負担をかけない範囲）
    with ThreadPoolExecutor(max_workers=3) as ex:
        for i, (addr, val) in enumerate(ex.map(work, todo), 1):
            if val != "error":
                cache[addr] = val
            if i % 100 == 0:
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
                print(f"  {i}/{len(todo)}", flush=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    ok = sum(1 for v in cache.values() if v)
    print(f"完了：位置が付いた住所 {ok}/{len(cache)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
