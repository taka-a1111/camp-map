"""県の観光協会サイトのスポットページから、日帰り入浴施設のページ（名前・住所・位置・料金・営業時間）を集める（GitHub Actions で毎月実行）。
地図データ（OpenStreetMap）に載っていない施設を補うのと、料金を読み取るのに使う。
一度見て入浴施設ではなかったページは半年間見直さない。入浴施設のページは毎回取り直して料金の変更を拾う。

python scripts/fetch_onsen_tourism.py [--budget 秒]
出力：data/onsen_tourism.json
  {"checked": {url: "YYYY-MM-DD"}, "pages": {url: {pref, site, name, lines, hours, address, official, lat, lng, fetched}}}
"""
import argparse
import datetime as dt
import html as htmlmod
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_pages import fetch, page_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "onsen_tourism.json"
TODAY = dt.date.today()
RECHECK_DAYS = 180
DELAY = 1.0  # 同じサイトへの間隔（秒）

SITES = [
    {"site": "観光三重", "pref": "三重県", "sitemap": "https://www.kankomie.or.jp/sitemap.xml", "pat": r"^https://www\.kankomie\.or\.jp/spot/\d+$"},
    {"site": "岐阜の旅ガイド", "pref": "岐阜県", "sitemap": "https://www.kankou-gifu.jp/sitemap.xml", "pat": r"^https://www\.kankou-gifu\.jp/spot/detail_\d+\.html$"},
    {"site": "ハローナビしずおか", "pref": "静岡県", "sitemap": "https://hellonavi.jp/storage/sitemap/sitemap.xml", "pat": r"^https://hellonavi\.jp/spot/[^/?#]+$"},
    {"site": "Go NAGANO", "pref": "長野県", "sitemap": "https://www.go-nagano.net/sitemap.xml",
     "pat": r"^https://www\.go-nagano\.net/(?!en/|zh-|th/|ko/|fr/|de/|es/|it/|vi/|id/|ms/)[a-z-]+/id\d+$"},
    {"site": "Aichi Now", "pref": "愛知県", "list": "https://aichinow.pref.aichi.jp/spots/?page={n}", "pat": r"/spots/detail/\d+/"},
]
BATH = re.compile(r"温泉|入浴|浴場|銭湯|スパ|の湯|湯$|湯\b|湯屋|湯処|湯宿")
FEE_LINE = re.compile(r"料金|入浴|入館|利用料|大人|一般|小人|小学生|子供|こども|子ども|中学生|幼児|円")
UA = "camp-map/1.0 (+https://github.com/taka-a1111/camp-map)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def sitemap_urls(url, depth=0):
    try:
        t = get(url)
    except Exception as e:  # noqa: BLE001
        print("  サイトマップ失敗", url, e, flush=True)
        return []
    locs = [htmlmod.unescape(x.strip()) for x in re.findall(r"<loc>([^<]+)</loc>", t)]
    if "<sitemapindex" in t and depth < 2:
        out = []
        for u in locs:
            out += sitemap_urls(u, depth + 1)
            time.sleep(DELAY)
        return out
    return locs


def list_urls(tpl, pat, base):
    out, seen_pages = [], 0
    for n in range(1, 400):
        try:
            t = get(tpl.format(n=n))
        except Exception:  # noqa: BLE001
            break
        found = [urllib.parse.urljoin(base, h) for h in re.findall(r'href="([^"]*?%s)"' % pat, t)]
        new = [u for u in dict.fromkeys(found) if u not in out]
        if not new:
            break
        out += new
        seen_pages = n
        time.sleep(DELAY)
    print(f"  一覧 {seen_pages}ページ", flush=True)
    return out


def page_name(html_text, site_name=""):
    cands = []
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html_text, re.I) or \
        re.search(r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"', html_text, re.I)
    if m:
        cands.append(m.group(1))
    m = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    if m:
        cands.append(m.group(1))
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.S | re.I)
    if m:
        cands.append(re.sub(r"<[^>]+>", "", m.group(1)))
    for c in cands:
        c = htmlmod.unescape(re.sub(r"\s+", " ", c)).strip()
        c = re.split(r"\s*[|｜]\s*|\s+[-–—]\s+", c)[0].strip()
        c = re.sub(r"(\s+[ぁ-ゖァ-ヴー・]+)+$", "", c).strip()  # 後ろに付いた読みがな
        if c and len(c) <= 60 and c != site_name and site_name not in c:
            return c
    return ""


def parse(url, html_text, site):
    name = page_name(html_text, site["site"])
    text, links = page_text(html_text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not name or re.search(r"海水浴|プール|キャンプ", name):
        return None
    if not (BATH.search(name) or (re.search(r"ホテル|旅館|荘|館|宿", name) and re.search(r"日帰り入浴|立ち寄り湯|入浴料", text))):
        return None
    # 記事ページ（見出しが文章）や温泉地の紹介ページは施設として扱わない
    if len(name) > 30 or re.search(r"[。、！？!?「」]", name):
        return None
    if not re.search(r"入浴|営業時間|利用時間|開館時間|定休日|休館日|休業日", text):
        return None
    fee = [l for l in lines if FEE_LINE.search(l) and len(l) <= 160]
    rec = {"pref": site["pref"], "site": site["site"], "name": name, "lines": fee[:40], "fetched": TODAY.isoformat()}
    for i, l in enumerate(lines):
        if re.match(r"^(営業時間|利用時間|入浴時間|開館時間)", l):
            v = re.sub(r"^(営業時間|利用時間|入浴時間|開館時間)[：:\s]*", "", l) or (lines[i + 1] if i + 1 < len(lines) else "")
            v = re.sub(r"^(営業時間|利用時間|入浴時間|開館時間)[：:\s]*", "", v)
            rec["hours"] = v[:60]
            break
    for i, l in enumerate(lines):
        if re.match(r"^(住所|所在地)", l):
            v = re.sub(r"^(住所|所在地)[：:\s]*", "", l) or (lines[i + 1] if i + 1 < len(lines) else "")
            rec["address"] = v[:80]
            break
    m = re.search(r"(?:q=|@|ll=|center=)(3[0-9]\.\d{4,}),\s*(13[0-9]\.\d{4,})", html_text) or \
        re.search(r'data-lat(?:itude)?="(3[0-9]\.\d+)"[^>]*data-(?:lng|lon|longitude)="(13[0-9]\.\d+)"', html_text)
    if m:
        rec["lat"], rec["lng"] = float(m.group(1)), float(m.group(2))
    for i, l in enumerate(lines):
        if re.match(r"^(公式URL|公式サイト|ホームページ|URL|HP)$", l) and i + 1 < len(lines) and lines[i + 1].startswith("http"):
            rec["official"] = lines[i + 1]
            break
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=4 * 3600)
    ap.add_argument("--limit", type=int, default=0, help="試験用：各サイトで見る件数の上限")
    ap.add_argument("--only", default="", help="試験用：このサイト名だけ")
    a = ap.parse_args()
    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"checked": {}, "pages": {}}
    lock = threading.Lock()
    start = time.time()

    def run_site(site):
        base = site.get("sitemap") or site["list"]
        if site.get("sitemap"):
            urls = [u for u in sitemap_urls(site["sitemap"]) if re.match(site["pat"], u)]
        else:
            urls = list_urls(site["list"], site["pat"], base)
        urls = list(dict.fromkeys(urls))
        todo = []
        for u in urls:
            last = store["checked"].get(u)
            if u in store["pages"] or not last or (TODAY - dt.date.fromisoformat(last)).days > RECHECK_DAYS:
                todo.append(u)
        if a.limit:
            todo = todo[: a.limit]
        print(f"{site['site']}: スポット {len(urls)}件・今回見る {len(todo)}件", flush=True)
        found = 0
        for i, u in enumerate(todo):
            if time.time() - start > a.budget:
                print(f"  {site['site']}: 時間の上限で中断（{i}件まで）", flush=True)
                break
            try:
                h, _ = fetch(u)
            except Exception:  # noqa: BLE001
                time.sleep(DELAY)
                continue
            rec = parse(u, h, site) if h else None
            with lock:
                store["checked"][u] = TODAY.isoformat()
                if rec:
                    store["pages"][u] = rec
                    found += 1
                elif u in store["pages"]:
                    store["pages"].pop(u)
            time.sleep(DELAY)
        print(f"  {site['site']}: 入浴施設のページ {found}件", flush=True)

    with ThreadPoolExecutor(max_workers=len(SITES)) as ex:
        list(ex.map(run_site, [x for x in SITES if not a.only or a.only in x["site"]]))
    OUT.write_text(json.dumps(store, ensure_ascii=False, indent=0), encoding="utf-8")
    print("入浴施設のページ 合計", len(store["pages"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
