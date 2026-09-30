"""全国の無料キャンプ場の候補（旅人茶屋の県別リスト＋OSMの fee=no）を、coverage.json / manual.json / season.json に取り込む。
python scripts/import_free_nationwide.py [候補ファイルのフォルダ（crawl_out/）]
"""
import json
import re
import sys
import unicodedata

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import build_data as b  # noqa: E402

ROOT = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data") + "/"
W = sys.argv[1] if len(sys.argv) > 1 else "crawl_out/"
ISO = {f"JP-{i:02d}": p for i, p in enumerate(
    ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県",
     "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
     "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県",
     "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"], 1)}

entries = json.load(open(W + "tabinchuya_entries.json"))
try:
    osm = json.load(open(W + "osm_camps_japan.json"))
except FileNotFoundError:
    osm = []
camps = json.load(open(ROOT + "camps.json"))["camps"]
cov = json.load(open(ROOT + "coverage.json"))
man = json.load(open(ROOT + "manual.json"))
season = json.load(open(ROOT + "season.json"))

have_manual = {(c["pref"], b.norm(c["match"])) for c in man["camps"]}
existing = {}
for c in camps:
    existing.setdefault(c["pref"], []).append(c)
cov_keys = {(c["pref"], c["name"]) for c in cov}

osm_by_pref = {}
for o in osm:
    nm = o["tags"].get("name:ja") or o["tags"].get("name") or ""
    if nm:
        osm_by_pref.setdefault(ISO.get(o["iso"], ""), []).append((b.norm(nm), o))

BASE = dict(site_label="キャンプ場（無料）", site_fee=0, site_includes="", site_capacity=None, adult_fee=0, adult_label="",
            child_fee=0, child_label="", infant_fee=0, people_included_in_site=0, extra_person_fee=0, tent_fee=0,
            tent_included=None, tarp_fee=0, vehicle_fee=None, vehicle_note="", fixed_fee=0, fixed_label="", per_person_tax=0,
            site_types=[], facilities=[], pet=None, booking_type=None, booking_url="", official_url="", tel="", season="",
            checkin="", checkout="", confidence="low")


OLD = re.compile(r"[（(]旧[）)]|旧キャンプ場")


def months_from(text):
    m = re.search(r"(\d{1,2})月[^～〜\-]*[～〜\-]\s*(\d{1,2})月", text)
    if not m:
        return None
    a, z = int(m.group(1)), int(m.group(2))
    if not (1 <= a <= 12 and 1 <= z <= 12):
        return None
    return list(range(a, z + 1)) if a <= z else list(range(a, 13)) + list(range(1, z + 1))


def find_existing(pref, name):
    n = b.norm(name)
    for c in existing.get(pref, []):
        if b.same_name(n, b.norm(c["name"])):
            return c
    return None


def find_osm(pref, name):
    n = b.norm(name)
    hits = [o for nn, o in osm_by_pref.get(pref, []) if b.same_name(n, nn)]
    return hits[0] if len(hits) == 1 else None


added_cov = added_man = matched_existing = 0
skipped = []
for e in entries:
    fee = e.get("fee", "")
    if not re.match(r"利用料[：:]\s*無料", fee) or re.search(r"閉鎖|禁止|有料化|利用不可|休止|(今|現在)はキャンプ場ではありません|廃止", fee):
        continue
    if OLD.search(e["name"]):
        continue
    pref, name = e["pref"], e["name"].strip()
    if not pref or not name:
        continue
    addr = e["loc"].split("・")[0].strip()
    date = re.sub(r"^※|の情報$", "", e.get("date", "")).strip()
    cond = re.sub(r"^利用料[：:]\s*", "", fee)
    notice = "公式ページでは料金を確認できていません。無料は無料野営地のまとめサイト（旅人茶屋）の情報" + (f"（{date}時点）" if date else "") + "によるもので、最新の状況は利用前に確認してください。"
    ex = find_existing(pref, name)
    key_name = ex["name"] if ex else name
    if ex:
        matched_existing += 1
    elif (pref, name) not in cov_keys:
        rec = {"name": name, "pref": pref, "city": "", "address": addr, "official_url": "", "source_url": e["url"],
               "source_kind": "aggregator", "status": "unknown", "types": "フリー" if "フリー" in e.get("ground", "") else "",
               "note": "無料野営地まとめサイト（旅人茶屋）の情報"}
        o = find_osm(pref, name)
        if o:
            rec.update(lat=round(o["lat"], 6), lng=round(o["lon"], 6), geo="osm")
        cov.append(rec)
        cov_keys.add((pref, name))
        added_cov += 1
    if (pref, b.norm(key_name)) in have_manual:
        continue
    m = dict(BASE)
    m.update(match=key_name, pref=pref, fee_note=f"利用料：{cond}" + (f"（{date}時点・利用者の情報）" if date else "（利用者の情報）"),
             source_url=e["url"], notice=notice)
    man["camps"].append(m)
    have_manual.add((pref, b.norm(key_name)))
    added_man += 1
    ms = months_from(cond)
    if ms and f"{pref}|{key_name}" not in season:
        season[f"{pref}|{key_name}"] = {"months": ms, "text": re.sub(r"[()（）]", "", cond.replace("無料", "")).strip("・ "), "closed_note": "", "quote": fee, "confidence": "low"}

# OSM で fee=no のキャンプ場（旅人茶屋に無いもの）
osm_added = 0
for o in osm:
    t = o["tags"]
    if t.get("fee") != "no" or t.get("access") in ("private", "no"):
        continue
    pref = ISO.get(o["iso"], "")
    name = t.get("name:ja") or t.get("name") or ""
    if not pref or not name or b.norm(name) in b.GENERIC or not b.JA.search(name) or re.search(r"デイキャンプ", name):
        continue
    ex = find_existing(pref, name)
    key_name = ex["name"] if ex else name
    if not ex and (pref, name) not in cov_keys:
        cov.append({"name": name, "pref": pref, "city": t.get("addr:city", ""), "address": "", "official_url": t.get("website", ""),
                    "source_url": f"https://www.openstreetmap.org/{o['osm']}", "source_kind": "aggregator", "status": "unknown",
                    "types": "", "note": "OpenStreetMap の登録情報", "lat": round(o["lat"], 6), "lng": round(o["lon"], 6), "geo": "osm"})
        cov_keys.add((pref, name))
    if (pref, b.norm(key_name)) in have_manual:
        continue
    m = dict(BASE)
    m.update(match=key_name, pref=pref, fee_note="OpenStreetMap の登録で料金なし（fee=no）", source_url=f"https://www.openstreetmap.org/{o['osm']}",
             official_url=t.get("website", ""),
             notice="公式ページでは料金を確認できていません。無料は OpenStreetMap の登録情報によるもので、利用前に確認してください。")
    man["camps"].append(m)
    have_manual.add((pref, b.norm(key_name)))
    osm_added += 1

old_names = {(e["pref"], e["name"].strip()) for e in entries if OLD.search(e["name"]) or re.search(r"(今|現在)はキャンプ場ではありません|廃止", e.get("fee", ""))}
n0 = len(cov)
cov = [r for r in cov if (r["pref"], r["name"]) not in old_names]
man["camps"] = [m for m in man["camps"] if (m["pref"], m["match"]) not in old_names]
print(f"以前の取り込みから外した旧キャンプ場 {n0 - len(cov)}件")

# 既に取り込んだ候補のうち、位置が住所（市町村）からの目安のものは OSM の位置に合わせる
moved = 0
for rec in cov:
    if rec.get("geo") == "osm" or rec.get("source_kind") != "aggregator" or rec["pref"] in ("愛知県", "岐阜県", "長野県", "静岡県", "三重県"):
        continue
    o = find_osm(rec["pref"], rec["name"])
    if o:
        rec.update(lat=round(o["lat"], 6), lng=round(o["lon"], 6), geo="osm")
        moved += 1
print(f"OSMの位置に合わせた候補 {moved}件")

json.dump(cov, open(ROOT + "coverage.json", "w"), ensure_ascii=False, indent=0)
json.dump(man, open(ROOT + "manual.json", "w"), ensure_ascii=False, indent=1)
json.dump(season, open(ROOT + "season.json", "w"), ensure_ascii=False, indent=0)
print(f"既存と一致 {matched_existing}・新規候補 {added_cov}・無料として登録 {added_man}・OSM料金なし {osm_added}")
