"""data/osm_raw.json（位置・名称）と data/manual.json（公式で確認した料金など）を合わせて data/camps.json を作る。

python scripts/build_data.py
"""
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "osm_raw.json"
MANUAL = ROOT / "data" / "manual.json"
OUT = ROOT / "data" / "camps.json"

# キャンプ場らしい名前（これに当たらず公式URLもないものは除外）
LIKE = re.compile(r"キャンプ|ｷｬﾝﾌﾟ|camp|野営|テント|幕営|グランピング|glamping|キャンピング|オート|バンガロー|ケビン|コテージ|村|の森|高原|公園|牧場|野外|ベース|フィールド|field|base|village|の家|の郷|の里|PICA|ヴィレッジ|キャンプ村", re.I)
# キャンプ場ではない・情報として役に立たないもの
EXCLUDE = re.compile(r"発電所|ヘリポート|分岐|昼ごはん|洞窟|海水浴場$|デイキャンプ|ボーイスカウト|貸しテント場|^中央広場$", re.I)
JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
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


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    blocked = manual.get("blocked_urls", [])

    def clean_url(u: str) -> str:
        if not u:
            return ""
        if not re.match(r"^https?://", u):
            u = "http://" + u
        return "" if any(b in u for b in blocked) else u

    # 1) OSMの絞り込み
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
        cands.append({"e": e, "name": name, "n": n, "web": clean_url(website(t))})

    # 2) 重複の統合（同名 or 同じ公式ドメインで2km以内）
    def richness(c):
        return len(c["e"]["tags"]) + (5 if c["web"] else 0)

    cands.sort(key=richness, reverse=True)
    kept = []
    for c in cands:
        pos = (c["e"]["lat"], c["e"]["lon"])
        dup = None
        for k in kept:
            kpos = (k["e"]["lat"], k["e"]["lon"])
            if dist_km(pos, kpos) > 2:
                continue
            short = min(len(c["n"]), len(k["n"]))
            if c["n"] == k["n"] or (short >= 4 and (c["n"] in k["n"] or k["n"] in c["n"])):
                dup = k
                break
            if c["web"] and k["web"] and host(c["web"]) == host(k["web"]):
                dup = k
                break
            if dist_km(pos, kpos) < 0.2:
                dup = k
                break
        if dup:
            for key, val in c["e"]["tags"].items():
                dup["e"]["tags"].setdefault(key, val)
            dup["web"] = dup["web"] or c["web"]
            dup["names"].append(c["name"])
        else:
            c["names"] = [c["name"]]
            kept.append(c)

    # 3) 手入力データとの突き合わせ
    by_key = {}
    for k in kept:
        for nm in k["names"]:
            by_key.setdefault((k["e"]["pref"], norm(nm)), k)
        # 表示名は日本語の名前を優先
        ja = [nm for nm in k["names"] if JA.search(nm)]
        k["name"] = unicodedata.normalize("NFKC", ja[0] if ja else k["name"]).strip()
    matched = set()
    unmatched_manual = []
    for m in manual["camps"]:
        key = (m["pref"], norm(m["match"]))
        k = by_key.get(key)
        if not k:
            unmatched_manual.append(m["match"])
            continue
        k["manual"] = m
        matched.add(id(k))

    # 4) 出力
    out = []
    pref_no = {}
    for k in sorted(kept, key=lambda x: (x["e"]["pref"], x["e"]["lat"])):
        e, t = k["e"], k["e"]["tags"]
        m = k.get("manual") or {}
        pref = e["pref"]
        pref_no[pref] = pref_no.get(pref, 0) + 1
        fees = [m.get("site_fee"), m.get("adult_fee"), m.get("other_fee")] if m else [None, None, None]
        total = None
        if m and all(v is not None for v in fees):
            total = fees[0] + fees[1] * 2 + fees[2]
        pet = m.get("pet") if m else ({"yes": True, "leashed": True, "no": False}.get(t.get("dog")))
        rec = {
            "id": e["osm"].replace("/", "-"),
            "name": m.get("name") or k["name"],
            "pref": pref,
            "city": t.get("addr:city", ""),
            "address": address(t),
            "lat": e["lat"],
            "lng": e["lon"],
            "site_fee": fees[0],
            "adult_fee": fees[1],
            "other_fee": fees[2],
            "other_fee_label": m.get("other_fee_label", ""),
            "total": total,
            "price_note": m.get("price_note", ""),
            "site_types": m.get("site_types", []),
            "facilities": m.get("facilities") if m else osm_facilities(t),
            "pet": pet,
            "booking_type": m.get("booking_type"),
            "booking_url": clean_url(m.get("booking_url", "")),
            "official_url": clean_url(m.get("official_url", "")) or k["web"],
            "tel": (m.get("tel") if m else "") or phone(t),
            "season": m.get("season") or "",
            "checkin": m.get("checkin", ""),
            "checkout": m.get("checkout", ""),
            "mountain": t.get("backcountry") == "yes",
            "affiliate_url": "",
            "source": "公式サイト等で確認" if m else "OpenStreetMap",
            "source_url": m.get("source_url", ""),
            "verified_at": manual.get("verified_at_default") if m else "",
            "confidence": m.get("confidence", ""),
            "osm": e["osm"],
        }
        out.append(rec)

    meta = {
        "generated_from": "OpenStreetMap contributors (ODbL) + manual.json",
        "osm_timestamp": raw.get("timestamp_osm_base", ""),
        "count": len(out),
        "priced": sum(1 for r in out if r["total"] is not None),
    }
    OUT.write_text(json.dumps({"meta": meta, "camps": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"出力 {len(out)}件（料金確認済み {meta['priced']}件）→ {OUT}")
    for p, n in pref_no.items():
        print(f"  {p}: {n}")
    if unmatched_manual:
        print("OSMと突き合わせできなかった手入力データ: " + "、".join(unmatched_manual))
    return 0


if __name__ == "__main__":
    sys.exit(main())
