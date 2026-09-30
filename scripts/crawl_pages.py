"""キャンプ場ごとの公式・自治体・観光協会ページを取得し、料金の読み取り用に本文テキストを保存する。
GitHub Actions で実行し、結果は公開リポジトリには入れず Actions の一時ファイル（artifact）として受け取る。

python scripts/crawl_pages.py [--limit N] [--only-unpriced]
出力：crawl_out/pages.jsonl（1行＝1キャンプ場）
"""
import argparse
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPS = ROOT / "data" / "camps.json"
COVER = ROOT / "data" / "coverage.json"
OUT = ROOT / "crawl_out"

# 予約・まとめサイトは取得しない（利用規約への配慮）
SKIP_HOSTS = ("nap-camp.com", "hinata", "jalan.net", "rakuten", "iko-yo.net", "camphack", "garvyplus", "tabinchuya",
              "instagram.com", "facebook.com", "twitter.com", "x.com", "youtube.com", "mapion", "mapfan", "yahoo.co.jp",
              "google.", "booking.com", "asoview", "sotoasobi", "tripadvisor", "retty", "tabelog", "ameblo.jp", "hatenablog",
              "note.com", "livedoor", "fc2.com", "goo.ne.jp", "hatinosu", "navitime", "walkerplus", "mapple", "zenrin")
LINK_WORDS = re.compile(r"料金|利用料|使用料|ご利用|利用案内|施設案内|キャンプ|宿泊|プラン|price|fee|rate|guide|camp", re.I)
UA = "camp-map/1.0 (+https://github.com/taka-a1111/camp-map)"


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.links, self.skip, self._a = [], [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table", "dt", "dd"):
            self.out.append("\n")
        if tag in ("td", "th"):
            self.out.append(" | ")
        if tag == "a":
            href = dict(attrs).get("href")
            self._a = [href, ""]
        if tag == "img":
            alt = dict(attrs).get("alt") or ""
            src = dict(attrs).get("src") or ""
            if re.search(r"料金|price|fee|ryokin|charge", alt + src, re.I):
                self.out.append(f"[料金の画像:{src}]")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        if tag == "a" and self._a:
            self.links.append(tuple(self._a))
            self._a = None

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)
            if self._a is not None:
                self._a[1] += data


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=20) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            return None, ctype
        raw = r.read(2_000_000)
        enc = r.headers.get_content_charset() or ""
        if not enc:
            m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000])
            enc = m.group(1).decode() if m else "utf-8"
        return raw.decode(enc, errors="replace"), ctype


def page_text(html):
    p = TextParser()
    p.feed(html)
    text = re.sub(r"[ \t　]+", " ", "".join(p.out))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text, p.links


def allowed(url):
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return h and not any(s in h for s in SKIP_HOSTS)


def crawl_one(item):
    cid, name, urls = item
    pages, seen = [], set()
    queue = [u for u in urls if u and allowed(u)]
    extra = 0
    while queue and len(pages) < 4:
        url = queue.pop(0).split("#")[0]
        if url.rstrip("/") in seen:
            continue
        seen.add(url.rstrip("/"))
        try:
            html, ctype = fetch(url)
        except Exception as e:  # noqa: BLE001
            pages.append({"url": url, "error": str(e)[:120]})
            continue
        if html is None:
            pages.append({"url": url, "error": "not html: " + ctype})
            continue
        text, links = page_text(html)
        pages.append({"url": url, "text": text[:12000]})
        # 同じサイト内の「料金」「利用案内」などのページを最大3つ追加で見る
        if extra < 3:
            host = urllib.parse.urlparse(url).hostname
            for href, label in links:
                if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                    continue
                full = urllib.parse.urljoin(url, href)
                full = full.split("#")[0]
                if urllib.parse.urlparse(full).hostname != host or full.rstrip("/") in seen:
                    continue
                if LINK_WORDS.search(label or "") or LINK_WORDS.search(href):
                    if re.search(r"\.(jpg|jpeg|png|gif|pdf|zip)$", full, re.I):
                        continue
                    queue.append(full)
                    extra += 1
                    if extra >= 3:
                        break
        time.sleep(1.0)
    return {"id": cid, "name": name, "pages": pages}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-unpriced", action="store_true")
    a = ap.parse_args()
    camps = json.loads(CAMPS.read_text(encoding="utf-8"))["camps"]
    items = []
    for c in camps:
        if a.only_unpriced and c.get("priced"):
            continue
        urls = [c.get("official_url", ""), c.get("source_url", "")]
        urls = list(dict.fromkeys(u for u in urls if u and allowed(u)))
        if urls:
            items.append((c["id"], c["name"], urls))
    if a.limit:
        items = items[: a.limit]
    print(f"取得対象 {len(items)}件", flush=True)
    OUT.mkdir(exist_ok=True)
    n = 0
    with gzip.open(OUT / "pages.jsonl.gz", "wt", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=8) as ex:
        for rec in ex.map(crawl_one, items):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if n % 50 == 0:
                print(f"  {n}/{len(items)}", flush=True)
    print("完了", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
