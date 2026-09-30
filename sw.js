/* キャンプ場マップ：アプリとして使うためのサービスワーカー
   - 画面・スクリプト：キャッシュを先に使い、裏で更新（BUILD が変わると入れ替え）
   - データ（data/*.json）：通信を優先し、圏外ではキャッシュ
   - 地図タイル：見た範囲をある程度保存し、圏外でも表示できるように */
var VERSION = "2026-09-30l";
var APP = "app-" + VERSION;
var DATA = "data-v1";
var TILES = "tiles-v1";
var TILE_MAX = 600;
var SHELL = [
  "./", "index.html", "css/style.css?v=" + VERSION, "js/app.js?v=" + VERSION, "manifest.webmanifest",
  "icons/icon-192.png", "icons/apple-touch-icon.png",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.Default.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.min.js"
];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(APP).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf("app-") === 0 && k !== APP; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function trimTiles() {
  caches.open(TILES).then(function (c) {
    c.keys().then(function (keys) {
      if (keys.length > TILE_MAX) keys.slice(0, keys.length - TILE_MAX).forEach(function (k) { c.delete(k); });
    });
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);

  if (url.hostname === "cyberjapandata.gsi.go.jp") {
    e.respondWith(caches.open(TILES).then(function (c) {
      return c.match(req).then(function (hit) {
        var net = fetch(req).then(function (res) { if (res.ok) { c.put(req, res.clone()); trimTiles(); } return res; });
        return hit || net;
      });
    }));
    return;
  }
  if (url.origin === location.origin && url.pathname.indexOf("/data/") >= 0) {
    e.respondWith(fetch(req).then(function (res) {
      if (res.ok) { var copy = res.clone(); caches.open(DATA).then(function (c) { c.put(req, copy); }); }
      return res;
    }).catch(function () { return caches.open(DATA).then(function (c) { return c.match(req, { ignoreSearch: true }); }); }));
    return;
  }
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(function (res) {
      var copy = res.clone(); caches.open(APP).then(function (c) { c.put("index.html", copy); });
      return res;
    }).catch(function () { return caches.match("index.html"); }));
    return;
  }
  if (url.origin === location.origin || url.hostname === "cdnjs.cloudflare.com") {
    e.respondWith(caches.match(req).then(function (hit) {
      return hit || fetch(req).then(function (res) {
        if (res.ok) { var copy = res.clone(); caches.open(APP).then(function (c) { c.put(req, copy); }); }
        return res;
      });
    }));
  }
});
