"""県が公表しているツキノワグマの出没（目撃）情報を集めて data/bears.json にまとめる。
あわせて、各キャンプ場の市町村名を国土地理院の逆ジオコーダで調べて data/camp_muni.json に保存する。
GitHub Actions で週1回実行する（県のサイトはコンテナからは届かないものがあるため）。

取り込み元（2026年9月時点）
- 静岡県：Googleマイマップ（KML）…地点の緯度経度あり
- 三重県：ArcGIS（三重県の地図サービス）…地点の緯度経度あり、直近1年分
- 長野県：月ごとの目撃一覧（PDF）…市町村単位（地点の緯度経度なし）
- 愛知県：年度ごとの出没一覧（PDF）…町字まで。国土地理院の住所検索で町字の位置にする
- 岐阜県：クママップ（県域統合型GIS）…取り込み方法を確認中。取得したページを bears_debug/ に残す

python scripts/fetch_bears.py
"""
import datetime as dt
import html
import json
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "bears.json"
MUNI_OUT = ROOT / "data" / "camp_muni.json"
GEO_CACHE = ROOT / "data" / "bear_geocode_cache.json"
DEBUG = ROOT / "bears_debug"
UA = "Mozilla/5.0 (compatible; camp-map/1.0; +https://github.com/taka-a1111/camp-map)"
KEEP_DAYS = 400
TODAY = dt.date.today()

SOURCES = {
    "静岡県": {"name": "静岡県 ツキノワグマ出没情報", "url": "https://www.pref.shizuoka.jp/kurashikankyo/shizenkankyo/wild/1017680.html"},
    "三重県": {"name": "三重県 ツキノワグマ出没情報", "url": "https://www.pref.mie.lg.jp/JTAISAKU/HP/m0114900048.htm"},
    "長野県": {"name": "長野県 ツキノワグマ目撃情報", "url": "https://www.pref.nagano.lg.jp/shinrin/sangyo/ringyo/choju/joho/kuma-map.html"},
    "愛知県": {"name": "愛知県 ツキノワグマ出没情報", "url": "https://www.pref.aichi.jp/soshiki/shizen/tsukinowaguma.html"},
    "岐阜県": {"name": "岐阜県 クママップ", "url": "https://www.pref.gifu.lg.jp/page/4964.html"},
}
MIE_WEBMAP = "a52667738d034a92a5f62bb7851721a1"


def get(url, binary=False, timeout=40, legacy_tls=False):
    ctx = None
    if legacy_tls:
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                raw = r.read()
                if binary:
                    return raw
                enc = r.headers.get_content_charset() or "utf-8"
                return raw.decode(enc, errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


def debug(name, text):
    DEBUG.mkdir(exist_ok=True)
    (DEBUG / name).write_text(text if isinstance(text, str) else str(text), encoding="utf-8")


def pdf_text(raw):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(raw)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, check=True).stdout


def links(page_html, base):
    out = []
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page_html, re.S | re.I):
        out.append((urllib.parse.urljoin(base, html.unescape(m.group(1))), re.sub(r"<[^>]+>", "", m.group(2)).strip()))
    return out


# ---- 市町村名の一覧（国土地理院 muni.js）
MUNI = {}  # code -> (pref, name)


def load_muni():
    js = get("https://maps.gsi.go.jp/js/muni.js")
    for m in re.finditer(r"MUNI_ARRAY\[\"(\d+)\"\]\s*=\s*'(\d+),([^,]+),(\d+),([^']+)'", js):
        code, pref, name = m.group(1), m.group(3), m.group(5)
        MUNI[code.lstrip("0")] = (pref, name.replace("　", ""))


def muni_names(pref):
    names = set()
    for p, n in MUNI.values():
        if p == pref:
            names.add(n)
            # 政令市の区（静岡市葵区など）は市名でも一致させる
            m = re.match(r"(.+?市)(.+区)$", n)
            if m:
                names.add(m.group(1))
    return sorted(names, key=len, reverse=True)


def find_muni(text, names):
    """文中で最初に出てくる市町村名（同じ位置なら長い名前）。説明文に出てくる別の市町村名を拾わないため。"""
    best = None
    for n in names:
        i = text.find(n)
        if i >= 0 and (best is None or i < best[0] or (i == best[0] and len(n) > len(best[1]))):
            best = (i, n)
    return best[1] if best else ""


def wareki(s):
    s = s.strip()
    m = re.match(r"(?:R|令和)\s*(\d+)[.年/](\d+)[.月/](\d+)", s)
    if m:
        return dt.date(2018 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(20\d\d)[/.\-年](\d+)[/.\-月](\d+)", s)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def geocode(q, cache):
    if q in cache:
        return cache[q]
    try:
        res = json.loads(get("https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(q)))
    except Exception:  # noqa: BLE001
        return None
    time.sleep(0.3)
    best = None
    for r in res or []:
        t = r["properties"]["title"]
        if not q.startswith(t[:4]):
            continue
        if best is None or len(t) > len(best[2]):
            lon, lat = r["geometry"]["coordinates"]
            best = (round(lat, 5), round(lon, 5), t)
    cache[q] = best
    return best


# ---- 各県
def shizuoka():
    page = get(SOURCES["静岡県"]["url"])
    mids = list(dict.fromkeys(re.findall(r"google\.com/maps/d/[^\"']*?mid=([\w-]+)", page)))
    recs = []
    for mid in mids:
        kml = get(f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1")
        for pm in re.findall(r"<Placemark>(.*?)</Placemark>", kml, re.S):
            d = dict(re.findall(r'<Data name="([^"]+)">\s*<value>(.*?)</value>', pm, re.S))
            day = wareki(d.get("日付", ""))
            try:
                lat, lng = float(d.get("緯度")), float(d.get("経度"))
            except (TypeError, ValueError):
                m = re.search(r"<coordinates>\s*([\d.]+),([\d.]+)", pm)
                if not m:
                    continue
                lng, lat = float(m.group(1)), float(m.group(2))
            if not day:
                continue
            style = re.search(r"<styleUrl>(.*?)</styleUrl>", pm)
            gray = bool(style and "757575" in style.group(1))  # 県の凡例：灰色＝クマの可能性がある情報
            recs.append({"d": day.isoformat(), "c": html.unescape(d.get("市町", "")), "pl": html.unescape(d.get("地名", "")),
                         "lat": round(lat, 5), "lng": round(lng, 5), "g": "point",
                         "k": "クマの可能性" if gray else "目撃", "n": html.unescape(d.get("備考", ""))[:60]})
    return recs, f"マイマップ {len(mids)}件"


def mie():
    wm = json.loads(get(f"https://www.arcgis.com/sharing/rest/content/items/{MIE_WEBMAP}/data?f=json"))
    layer = next(l for l in wm.get("operationalLayers", []) if "クマ" in (l.get("title") or "") or "クマ" in (l.get("url") or ""))
    url = urllib.parse.quote(layer["url"], safe=":/")
    recs, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json",
                                    "resultOffset": offset, "resultRecordCount": 1000})
        d = json.loads(get(url + "/query?" + q))
        feats = d.get("features", [])
        for f in feats:
            a, g = f["attributes"], f.get("geometry") or {}
            day = wareki(str(a.get("目撃日", "")))
            if not day or "x" not in g:
                continue
            place = a.get("場所") or ""
            recs.append({"d": day.isoformat(), "c": "", "pl": place, "lat": round(g["y"], 5), "lng": round(g["x"], 5), "g": "point",
                         "k": "・".join(x for x in [a.get("表示"), a.get("種別")] if x)})
        if len(feats) < 1000 or not d.get("exceededTransferLimit"):
            break
        offset += 1000
    names = muni_names("三重県")
    for r in recs:
        r["c"] = find_muni(r["pl"], names)
    return recs, layer.get("title", "")


def nagano():
    base = SOURCES["長野県"]["url"]
    page = get(base)
    pdfs = [u for u, t in links(page, base) if u.endswith(".pdf") and "mokugeki" in u]
    names = muni_names("長野県")
    recs, seen = [], set()
    for u in dict.fromkeys(pdfs):
        try:
            txt = pdf_text(get(u, binary=True))
        except Exception as e:  # noqa: BLE001
            print("  長野 PDF 失敗", u, e)
            continue
        for line in txt.split("\n"):
            m = re.search(r"(20\d\d/\d{1,2}/\d{1,2})", line)
            if not m:
                continue
            day = wareki(m.group(1))
            city = find_muni(line, names)
            if not day or not city:
                continue
            kind = "人身被害" if "人身被害" in line else ("痕跡" if "痕跡" in line else ("センサーカメラ" if "センサーカメラ" in line else "目撃"))
            key = (line.strip(), u)
            if key in seen:
                continue
            seen.add(key)
            recs.append({"d": day.isoformat(), "c": city, "pl": "", "lat": None, "lng": None, "g": "city", "k": kind})
    return recs, f"PDF {len(pdfs)}件"


def aichi(geo_cache):
    base = SOURCES["愛知県"]["url"]
    page = get(base)
    debug("aichi_page.html", page)
    pdfs = [(u, t) for u, t in links(page, base) if u.endswith(".pdf") and re.search(r"出没|確認", t)]
    names = muni_names("愛知県")
    recs = []
    for u, t in pdfs:
        try:
            txt = pdf_text(get(u, binary=True))
        except Exception as e:  # noqa: BLE001
            print("  愛知 PDF 失敗", u, e)
            continue
        debug("aichi_" + Path(u).stem + ".txt", txt)
        fy = None
        for line in txt.split("\n"):
            m = re.search(r"令和\s*(\d+|元)\s*年度", line)
            if m:
                fy = 2018 + (1 if m.group(1) == "元" else int(m.group(1)))
            # 例：「1 4 8 豊田市黒田町一色地内 …」または「令和7年4月8日 …」
            m = re.match(r"\s*\d+\s+(\d{1,2})\s+(\d{1,2})\s+(\S+)", line)
            day = None
            place = ""
            if m and fy:
                mo, da = int(m.group(1)), int(m.group(2))
                if 1 <= mo <= 12 and 1 <= da <= 31:
                    try:
                        day = dt.date(fy + (1 if mo <= 3 else 0), mo, da)
                    except ValueError:
                        day = None
                    place = m.group(3)
            else:
                m = re.search(r"(令和\s*\d+年\s*\d+月\s*\d+日|R\d+\.\d+\.\d+|20\d\d/\d+/\d+)\s+(\S+)", line)
                if m:
                    day = wareki(re.sub(r"\s", "", m.group(1)))
                    place = m.group(2)
            if not day:
                continue
            city = find_muni(place, names)
            if not city:
                continue
            q = "愛知県" + re.sub(r"(地内|付近|周辺|地先).*$", "", place)
            g = geocode(q, geo_cache)
            rec = {"d": day.isoformat(), "c": city, "pl": re.sub(r"地内$", "", place), "k": "クマらしき動物" if "らしき" in line else "目撃"}
            if g and len(g[2]) > len("愛知県" + city):
                rec.update(lat=g[0], lng=g[1], g="area")
            else:
                rec.update(lat=None, lng=None, g="city")
            recs.append(rec)
    # 同じ出没が複数の PDF（今年度と過去5年間）に載るので重複を除く
    uniq = {(r["d"], r["pl"]): r for r in recs}
    return list(uniq.values()), f"PDF {len(pdfs)}件"


def gifu_probe():
    """岐阜県のクママップの仕組みを確認するため、ページと読み込んでいるスクリプトを保存する（取り込みはまだしない）。"""
    url = "https://gis-gifu.jp/gifu/maps.action?mp=P10535,_default&ll=137.3461761,36.1609268&z=3"
    page = get(url, legacy_tls=True)
    debug("gifu_map.html", page)
    for i, s in enumerate(re.findall(r'<script[^>]+src="([^"]+)"', page)[:40]):
        full = urllib.parse.urljoin(url, s)
        if "gis-gifu" not in full:
            continue
        try:
            debug(f"gifu_js_{i}.js", get(full, legacy_tls=True))
        except Exception as e:  # noqa: BLE001
            debug(f"gifu_js_{i}.err", f"{full} {e}")
    return [], "未対応（確認中）"


# ---- キャンプ場の市町村（逆ジオコーダ）
def camp_muni():
    camps = json.loads((ROOT / "data" / "camps.json").read_text(encoding="utf-8"))["camps"]
    cache = json.loads(MUNI_OUT.read_text(encoding="utf-8")) if MUNI_OUT.exists() else {}
    n = 0
    for c in camps:
        if c["pref"] not in SOURCES:
            continue
        k = f"{c['lat']:.5f},{c['lng']:.5f}"
        if k in cache:
            continue
        try:
            d = json.loads(get(f"https://mreversegeoc.gsi.go.jp/reverse-geocoder/LonLatToAddress?lat={c['lat']}&lon={c['lng']}"))
            code = (d.get("results") or {}).get("muniCd", "")
            cache[k] = MUNI.get(code.lstrip("0"), ("", ""))[1]
        except Exception as e:  # noqa: BLE001
            print("  逆ジオコーダ失敗", c["name"], e)
            continue
        n += 1
        time.sleep(0.2)
    MUNI_OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"キャンプ場の市町村：新しく {n}件（計 {len(cache)}件）")


def main():
    load_muni()
    print("市町村一覧", len(MUNI))
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"sources": {}, "records": {}}
    geo_cache = json.loads(GEO_CACHE.read_text(encoding="utf-8")) if GEO_CACHE.exists() else {}
    result = {"updated": TODAY.isoformat(), "sources": {}, "records": {}}
    cutoff = (TODAY - dt.timedelta(days=KEEP_DAYS)).isoformat()
    jobs = {"静岡県": shizuoka, "三重県": mie, "長野県": nagano, "愛知県": lambda: aichi(geo_cache), "岐阜県": gifu_probe}
    for pref, fn in jobs.items():
        src = dict(SOURCES[pref])
        try:
            recs, note = fn()
            recs = [r for r in recs if r["d"] >= cutoff and r["d"] <= TODAY.isoformat()]
            recs.sort(key=lambda r: r["d"], reverse=True)
            src.update(ok=bool(recs), fetched=TODAY.isoformat(), note=note, count=len(recs))
            print(f"{pref}: {len(recs)}件（{note}）")
        except Exception as e:  # noqa: BLE001
            print(f"{pref}: 失敗 {e}")
            recs = []
            src.update(ok=False, error=str(e)[:200])
        if not recs and old.get("records", {}).get(pref):
            # 取れなかったときは前回の結果を使い続ける（日付が古ければ表示側で注意書き）
            recs = old["records"][pref]
            prev = old["sources"].get(pref, {})
            src.update(ok=prev.get("ok", False), fetched=prev.get("fetched"), count=len(recs), stale=True)
        result["sources"][pref] = src
        result["records"][pref] = recs
    GEO_CACHE.write_text(json.dumps(geo_cache, ensure_ascii=False, indent=0), encoding="utf-8")
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        camp_muni()
    except Exception as e:  # noqa: BLE001
        print("キャンプ場の市町村：失敗", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
