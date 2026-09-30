"""3つのデータを合わせて data/camps.json を作る。
- data/osm_raw.json：OpenStreetMap の位置・名称
- data/coverage.json：自治体・観光協会・公式サイト等で洗い出したキャンプ場一覧（住所は scripts/geocode.py で位置に変換）
- data/manual.json：公式サイト等で確認した料金・予約方法・設備

python scripts/build_data.py
"""
import json
import importlib.util
import math
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "osm_raw.json"
MANUAL = ROOT / "data" / "manual.json"
COVER = ROOT / "data" / "coverage.json"
GEOCACHE = ROOT / "data" / "geocode_cache.json"
FEESTATUS = ROOT / "data" / "fee_status.json"
OUT = ROOT / "data" / "camps.json"

# キャンプ場らしい名前（これに当たらず公式URLもないものは除外）
LIKE = re.compile(r"キャンプ|ｷｬﾝﾌﾟ|camp|野営|テント|幕営|グランピング|glamping|キャンピング|オート|バンガロー|ケビン|コテージ|村|の森|高原|公園|牧場|野外|ベース|フィールド|field|base|village|の家|の郷|の里|PICA|ヴィレッジ|キャンプ村", re.I)
# キャンプ場ではない・情報として役に立たないもの
EXCLUDE = re.compile(r"発電所|ヘリポート|分岐|昼ごはん|洞窟|海水浴場$|デイキャンプ|ボーイスカウト|貸しテント場|^中央広場$", re.I)
JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
# 予約サイトなど、複数の施設が同じドメインを使うもの（ドメイン一致を同一施設とみなさない）
SHARED_HOSTS = {"nap-camp.com", "hinata-spot.me", "camp.travel.rakuten.co.jp", "reserve.489ban.net", "select-type.com",
                "instagram.com", "facebook.com", "twitter.com", "x.com", "note.com", "ameblo.jp", "sites.google.com",
                "camprsv.com", "d-reserve.jp", "jalan.net", "booking.com", "linktr.ee", "lit.link"}
GENERIC = {"キャンプ場", "キャンプサイト", "テントサイト", "オートキャンプ場", "campsite", "campingground", "aキャンプ場", "bキャンプ場", "デイキャンプ"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[\s　・（）()\-－—~〜]", "", s)
    return s


def dist_km(a, b) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def pick_name(t: dict) -> str:
    return t.get("name:ja") or t.get("name") or ""


def website(t: dict) -> str:
    return t.get("website") or t.get("contact:website") or t.get("contact:website:ja") or t.get("url") or ""


def phone(t: dict) -> str:
    p = t.get("phone") or t.get("contact:phone") or ""
    p = p.split(";")[0].strip()
    if p.startswith("+81"):
        p = "0" + re.sub(r"^\+81[\s-]?", "", p)
        p = re.sub(r"\s+", "-", p)
    return p


def address(t: dict) -> str:
    parts = [t.get("addr:province", ""), t.get("addr:county", ""), t.get("addr:city", ""), t.get("addr:suburb", ""),
             t.get("addr:quarter", ""), t.get("addr:neighbourhood", ""), t.get("addr:place", ""), t.get("addr:block_number", "")]
    s = "".join(p for p in parts if p)
    if t.get("addr:housenumber"):
        s += ("-" if t.get("addr:block_number") else "") + t["addr:housenumber"]
    return s


def osm_facilities(t: dict) -> list:
    f = []
    if t.get("power_supply") == "yes":
        f.append("power")
    if t.get("shower") in ("yes", "hot"):
        f.append("shower")
    if t.get("toilets:disposal") == "flush":
        f.append("flush_toilet")
    return f


def load_geocode():
    spec = importlib.util.spec_from_file_location("geocode", ROOT / "scripts" / "geocode.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.clean_address


TYPE_MAP = [("オート", "auto"), ("区画", "kukaku"), ("フリー", "free"), ("バンガロー", "bungalow"),
            ("コテージ", "cottage"), ("ロッジ", "cottage"), ("ケビン", "cottage"), ("キャビン", "cottage"),
            ("トレーラー", "cottage"), ("グランピング", "glamping")]

FEE_KEYS = ["site_label", "site_fee", "site_includes", "site_capacity", "adult_fee", "adult_label", "child_fee",
            "child_label", "infant_fee", "people_included_in_site", "extra_person_fee", "tent_fee", "tent_included",
            "tarp_fee", "vehicle_fee", "vehicle_note", "fixed_fee", "fixed_label", "per_person_tax", "fee_note"]


def types_from_text(s: str) -> list:
    out = []
    for word, code in TYPE_MAP:
        if word in (s or "") and code not in out:
            out.append(code)
    return out


def same_name(a: str, b: str) -> bool:
    if not a or not b:
        return False
    short = min(len(a), len(b))
    return a == b or (short >= 4 and (a in b or b in a))


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    cover = json.loads(COVER.read_text(encoding="utf-8")) if COVER.exists() else []
    geocache = json.loads(GEOCACHE.read_text(encoding="utf-8")) if GEOCACHE.exists() else {}
    clean_address = load_geocode()
    fee_status = json.loads(FEESTATUS.read_text(encoding="utf-8")) if FEESTATUS.exists() else {}
    blocked = manual.get("blocked_urls", [])

    def clean_url(u: str) -> str:
        if not u:
            return ""
        if not re.match(r"^https?://", u):
            u = "http://" + u
        return "" if any(b in u for b in blocked) else u

    # 1) OSMの絞り込み
    places = []
    cands = []
    for e in raw["elements"]:
        t = e["tags"]
        name = pick_name(t)
        if not name:
            continue
        if t.get("access") in ("private", "no") or t.get("group_only") == "yes":
            continue
        if EXCLUDE.search(name):
            continue
        n = norm(name)
        if n in GENERIC and not website(t):
            continue
        if not LIKE.search(name) and not website(t):
            continue
        cands.append({"pref": e["pref"], "lat": e["lat"], "lng": e["lon"], "names": [name], "tags": t,
                      "web": clean_url(website(t)), "osm": e["osm"], "geo": "osm"})
    cands.sort(key=lambda c: len(c["tags"]) + (5 if c["web"] else 0), reverse=True)
    for c in cands:
        pos = (c["lat"], c["lng"])
        dup = None
        for k in places:
            d = dist_km(pos, (k["lat"], k["lng"]))
            if d > 2:
                continue
            if same_name(norm(c["names"][0]), norm(k["names"][0])) or d < 0.2 or \
                    (c["web"] and k["web"] and host(c["web"]) == host(k["web"])):
                dup = k
                break
        if dup:
            for key, val in c["tags"].items():
                dup["tags"].setdefault(key, val)
            dup["web"] = dup["web"] or c["web"]
            dup["names"].append(c["names"][0])
        else:
            places.append(c)

    # 2) 網羅調査リストの統合
    def find_place(pref, name, web, pos, radius):
        n = norm(name)
        best = None
        for k in places:
            if k["pref"] != pref:
                continue
            d = dist_km(pos, (k["lat"], k["lng"])) if pos else None
            if d is not None and d > radius:
                continue
            hit = any(same_name(n, norm(x)) for x in k["names"])
            if not hit and web and k["web"] and host(web) == host(k["web"]) and host(web) not in SHARED_HOSTS:
                hit = True
            if hit and (best is None or (d or 0) < best[0]):
                best = (d or 0, k)
        return best[1] if best else None

    added = merged = closed = nogeo = 0
    for cv in cover:
        addr = clean_address(cv.get("address", ""))
        if addr and not addr.startswith(cv["pref"]):
            addr = cv["pref"] + addr
        g = geocache.get(addr) if addr else None
        pos = (g["lat"], g["lng"]) if g else None
        web = clean_url(cv.get("official_url", ""))
        # 住所が地区レベルまでしか分からないときは、位置のずれを見込んで広めに同一施設を探す
        k = find_place(cv["pref"], cv["name"], web, pos, 8 if g["level"] == "address" else 30) if pos else \
            next((p for p in places if p["pref"] == cv["pref"] and any(same_name(norm(cv["name"]), norm(x)) for x in p["names"])), None)
        if cv.get("status") == "closed":
            if k:
                k["closed"] = True
                closed += 1
            continue
        if k:
            k.setdefault("cover", cv)
            if cv["name"] not in k["names"]:
                k["names"].insert(0, cv["name"])
            k["web"] = k["web"] or web
            merged += 1
            continue
        if not pos:
            nogeo += 1
            continue
        places.append({"pref": cv["pref"], "lat": pos[0], "lng": pos[1], "names": [cv["name"]], "tags": {},
                       "web": web, "osm": "", "geo": g["level"], "cover": cv})
        added += 1

    # 3) 手入力データとの突き合わせ
    unmatched_manual = []
    for m in manual["camps"]:
        n = norm(m["match"])
        k = next((p for p in places if p["pref"] == m["pref"] and not p.get("closed")
                  and any(norm(x) == n for x in p["names"])), None)
        k = k or next((p for p in places if p["pref"] == m["pref"] and not p.get("closed")
                       and any(same_name(n, norm(x)) for x in p["names"])), None)
        if not k:
            unmatched_manual.append(m["match"])
            continue
        k["manual"] = m

    # 4) 出力
    out = []
    pref_no = {}
    for i, k in enumerate(sorted([p for p in places if not p.get("closed")], key=lambda x: (x["pref"], x["lat"]))):
        t, m, cv = k["tags"], k.get("manual") or {}, k.get("cover") or {}
        pref = k["pref"]
        pref_no[pref] = pref_no.get(pref, 0) + 1
        ja = [nm for nm in k["names"] if JA.search(nm)]
        name = m.get("name") or unicodedata.normalize("NFKC", cv.get("name") or (ja[0] if ja else k["names"][0])).strip()
        types_text = cv.get("types", "")
        mountain = t.get("backcountry") == "yes" or "山岳" in types_text or "テント場" in name
        status = m.get("status") or ("open" if m else ("open" if cv.get("status") == "open" else "unknown"))
        rec = {
            "id": (k["osm"].replace("/", "-") if k["osm"] else "c-%s-%d" % (pref, i)),
            "name": name,
            "pref": pref,
            "city": cv.get("city") or t.get("addr:city", ""),
            "address": cv.get("address") or address(t),
            "lat": round(k["lat"], 6),
            "lng": round(k["lng"], 6),
            "geo": k["geo"],
            "status": status,
            "site_types": m.get("site_types") or types_from_text(types_text),
            "types_text": types_text,
            "facilities": m.get("facilities") if m else osm_facilities(t),
            "pet": m.get("pet") if m else ({"yes": True, "leashed": True, "no": False}.get(t.get("dog"))),
            "booking_type": m.get("booking_type"),
            "booking_url": clean_url(m.get("booking_url", "")),
            "official_url": clean_url(m.get("official_url", "")) or clean_url(cv.get("official_url", "")) or k["web"],
            "tel": (m.get("tel") if m else "") or phone(t),
            "season": m.get("season") or "",
            "checkin": m.get("checkin", ""),
            "checkout": m.get("checkout", ""),
            "mountain": mountain,
            "affiliate_url": "",
            "source": "公式サイト等で確認" if m else ({"official": "運営者の公式サイト", "municipal": "自治体のページ",
                                                  "tourism": "観光協会・観光サイト", "aggregator": "予約・検索サイトの掲載"}.get(cv.get("source_kind"), "OpenStreetMap")),
            "source_url": m.get("source_url") or cv.get("source_url", ""),
            "verified_at": manual.get("verified_at_default") if m else "",
            "confidence": m.get("confidence", ""),
            "notice": m.get("notice", ""),
        }
        fs = fee_status.get(f"{pref}|{name}")
        if fs and not m:
            rec["fee_status"] = fs["status"]
            rec["fee_quote"] = fs.get("quote", "")
            rec["fee_url"] = fs.get("url", "")
        if m:
            rec["priced"] = m.get("site_fee") is not None and m.get("status") != "unknown"
            for key in FEE_KEYS:
                rec[key] = m.get(key)
        # 空の項目は出力しない（ファイルを軽くするため）
        rec = {a: b for a, b in rec.items() if not (b in ("", [], None, False) and a not in FEE_KEYS)}
        out.append(rec)

    meta = {
        "generated_from": "OpenStreetMap contributors (ODbL) + coverage.json + manual.json",
        "osm_timestamp": raw.get("timestamp_osm_base", ""),
        "count": len(out),
        "priced": sum(1 for r in out if r.get("priced")),
        "open_confirmed": sum(1 for r in out if r.get("status") == "open"),
    }
    OUT.write_text(json.dumps({"meta": meta, "camps": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"出力 {len(out)}件（料金確認済み {meta['priced']}件、営業確認 {meta['open_confirmed']}件）→ {OUT}")
    print(f"  網羅調査：統合 {merged}件・新規追加 {added}件・閉鎖として除外 {closed}件・位置不明で保留 {nogeo}件")
    for p, n in pref_no.items():
        print(f"  {p}: {n}")
    if unmatched_manual:
        print("突き合わせできなかった手入力データ: " + "、".join(unmatched_manual))
    return 0


if __name__ == "__main__":
    sys.exit(main())
