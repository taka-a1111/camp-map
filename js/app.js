/* キャンプ場マップ BUILD_TAG: 2026-09-29a */
(function () {
  "use strict";
  console.log("BUILD_TAG: 2026-09-29a");

  var TYPE_LABEL = { auto: "オートサイト", kukaku: "区画サイト", free: "フリーサイト", bungalow: "バンガロー", cottage: "コテージ等", glamping: "グランピング" };
  var FAC_LABEL = { power: "AC電源", shower: "シャワー", onsen: "温泉", flush_toilet: "水洗トイレ", shop: "売店", rental: "レンタル" };
  var BOOK_LABEL = { web: "ネット予約可", phone: "電話予約", none: "予約不要" };
  var PREF_VIEW = {
    "": [[33.7, 135.8], [37.0, 139.3]],
    "愛知県": [[34.55, 136.65], [35.45, 137.85]],
    "岐阜県": [[35.1, 136.25], [36.5, 137.7]],
    "長野県": [[35.2, 137.3], [37.05, 138.8]],
    "静岡県": [[34.55, 137.45], [35.7, 139.2]],
    "三重県": [[33.7, 135.85], [35.3, 136.99]]
  };

  var $ = function (id) { return document.getElementById(id); };
  var els = {
    pref: $("pref"), max: $("max"), q: $("q"), more: $("moreBtn"), badge: $("badge"), filters: $("filters"),
    count: $("count"), detail: $("detail"), body: $("detailBody"), pet: $("pet"), known: $("known"), nomt: $("nomt")
  };

  var camps = [];
  var markers = {};
  var activeId = null;

  // 地図
  var map = L.map("map", { zoomControl: true, preferCanvas: false }).fitBounds(PREF_VIEW[""]);
  L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">地理院タイル</a> | キャンプ場データ © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'
  }).addTo(map);
  var cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45, spiderfyOnMaxZoom: true });
  map.addLayer(cluster);
  map.on("click", function () { closeDetail(); });

  function yen(n) { return n === 0 ? "無料" : n.toLocaleString("ja-JP") + "円"; }
  function fee(n) { return n === 0 ? "なし" : n.toLocaleString("ja-JP") + "円"; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function safeUrl(u) { return /^https?:\/\//.test(u || "") ? u : ""; }

  function iconFor(c) {
    var html = c.total != null ? '<div class="pin-price">' + (c.total === 0 ? "無料" : "¥" + c.total.toLocaleString("ja-JP")) + "</div>" : '<div class="pin-dot"></div>';
    return L.divIcon({ className: "pin" + (c.id === activeId ? " is-active" : ""), html: html, iconSize: c.total != null ? [0, 0] : [14, 14] });
  }

  // 条件
  function checked(key) {
    return Array.prototype.map.call(document.querySelectorAll('.chips[data-key="' + key + '"] input:checked'), function (i) { return i.value; });
  }
  function getState() {
    return {
      pref: els.pref.value,
      max: els.max.value,
      q: els.q.value.trim(),
      types: checked("types"),
      book: checked("book"),
      fac: checked("fac"),
      pet: els.pet.checked,
      known: els.known.checked,
      nomt: els.nomt.checked
    };
  }
  function norm(s) { return (s || "").normalize("NFKC").toLowerCase().replace(/\s/g, ""); }

  function match(c, s) {
    if (s.pref && c.pref !== s.pref) return false;
    if (s.max !== "") { if (c.total == null || c.total > Number(s.max)) return false; }
    if (s.known && c.total == null) return false;
    if (s.nomt && c.mountain) return false;
    if (s.pet && c.pet !== true) return false;
    if (s.q) {
      var hay = norm(c.name + c.pref + c.city + c.address);
      var words = norm(s.q).split(/[,、]/).filter(Boolean);
      for (var i = 0; i < words.length; i++) if (hay.indexOf(words[i]) < 0) return false;
    }
    if (s.types.length && !s.types.some(function (t) { return c.site_types.indexOf(t) >= 0; })) return false;
    if (s.book.length && s.book.indexOf(c.booking_type) < 0) return false;
    if (s.fac.length && !s.fac.every(function (f) { return c.facilities.indexOf(f) >= 0; })) return false;
    return true;
  }

  // URLに条件を保存
  function writeUrl(s) {
    var p = new URLSearchParams();
    if (s.pref) p.set("pref", s.pref);
    if (s.max !== "") p.set("max", s.max);
    if (s.q) p.set("q", s.q);
    if (s.types.length) p.set("types", s.types.join(","));
    if (s.book.length) p.set("book", s.book.join(","));
    if (s.fac.length) p.set("fac", s.fac.join(","));
    if (s.pet) p.set("pet", "1");
    if (s.known) p.set("known", "1");
    if (s.nomt) p.set("nomt", "1");
    if (activeId) p.set("id", activeId);
    var qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
  }
  function readUrl() {
    var p = new URLSearchParams(location.search);
    if (p.get("pref") && PREF_VIEW[p.get("pref")]) els.pref.value = p.get("pref");
    if (p.has("max")) els.max.value = p.get("max");
    if (p.get("q")) els.q.value = p.get("q");
    ["types", "book", "fac"].forEach(function (k) {
      var v = (p.get(k) || "").split(",");
      document.querySelectorAll('.chips[data-key="' + k + '"] input').forEach(function (i) { i.checked = v.indexOf(i.value) >= 0; });
    });
    els.pet.checked = p.get("pet") === "1";
    els.known.checked = p.get("known") === "1";
    els.nomt.checked = p.get("nomt") === "1";
    return p.get("id");
  }

  function apply(opts) {
    var s = getState();
    var hits = camps.filter(function (c) { return match(c, s); });
    cluster.clearLayers();
    cluster.addLayers(hits.map(function (c) { return markers[c.id]; }));
    var priced = hits.filter(function (c) { return c.total != null; }).length;
    els.count.textContent = "該当 " + hits.length + "件（料金確認済み " + priced + "件）";
    var extra = s.types.length + s.book.length + s.fac.length + (s.pet ? 1 : 0) + (s.known ? 1 : 0) + (s.nomt ? 1 : 0);
    els.badge.hidden = extra === 0;
    els.badge.textContent = extra;
    if (activeId && !hits.some(function (c) { return c.id === activeId; })) closeDetail(true);
    if (opts && opts.fit) map.fitBounds(PREF_VIEW[s.pref] || PREF_VIEW[""]);
    writeUrl(s);
  }

  // 詳細
  function row(label, val) { return val ? "<dt>" + esc(label) + "</dt><dd>" + esc(val) + "</dd>" : ""; }

  function tips(c) {
    var t = [];
    if (c.booking_type === "none") t.push("予約不要：連休や夏休みは早めの到着が安心です");
    if (c.site_types.indexOf("free") >= 0) t.push("フリーサイト：平らな場所を選べるよう、明るいうちの設営がおすすめです");
    if (c.pet === true) t.push("ペット可：リードと足ふきタオル、ペット用の水を用意");
    if (c.mountain) t.push("山岳テント場：軽量の装備と防寒着を。車は近くまで入れません");
    if (c.facilities.indexOf("onsen") >= 0) t.push("温泉あり：タオルと着替えを多めに");
    return t;
  }

  function render(c) {
    var h = [];
    h.push('<h2 class="d-name">' + esc(c.name) + "</h2>");
    h.push('<p class="d-area">' + esc(c.pref + (c.city ? " " + c.city : "")) + (c.mountain ? "　山岳テント場" : "") + "</p>");

    h.push('<div class="d-price"><div class="lbl">大人2人・1泊の総額（目安）</div>');
    if (c.total != null) {
      h.push('<div class="total">' + yen(c.total) + "</div><table>");
      h.push("<tr><td>サイト料</td><td>" + fee(c.site_fee) + "</td></tr>");
      h.push("<tr><td>入場料・人数料金" + (c.adult_fee ? "（大人" + yen(c.adult_fee) + "×2）" : "") + "</td><td>" + fee(c.adult_fee * 2) + "</td></tr>");
      h.push("<tr><td>その他" + (c.other_fee_label ? "（" + esc(c.other_fee_label) + "）" : "") + "</td><td>" + fee(c.other_fee) + "</td></tr>");
      h.push("</table>");
    } else if (c.site_fee != null || c.adult_fee != null) {
      h.push('<div class="total unknown">一部未確認</div><table>');
      h.push("<tr><td>サイト料</td><td>" + (c.site_fee != null ? fee(c.site_fee) : "未確認") + "</td></tr>");
      h.push("<tr><td>入場料・人数料金（大人1人）</td><td>" + (c.adult_fee != null ? fee(c.adult_fee) : "未確認") + "</td></tr>");
      h.push("<tr><td>その他</td><td>" + (c.other_fee != null ? fee(c.other_fee) : "未確認") + "</td></tr>");
      h.push("</table>");
    } else {
      h.push('<div class="total unknown">料金は未確認</div>');
    }
    if (c.price_note) h.push('<p class="d-note">' + esc(c.price_note) + "</p>");
    h.push("</div>");

    var tags = [];
    tags.push('<span class="tag-i book">' + esc(BOOK_LABEL[c.booking_type] || "予約方法 未確認") + "</span>");
    c.site_types.forEach(function (t) { tags.push('<span class="tag-i">' + esc(TYPE_LABEL[t] || t) + "</span>"); });
    if (c.pet === true) tags.push('<span class="tag-i">ペット可</span>');
    if (c.pet === false) tags.push('<span class="tag-i">ペット不可</span>');
    h.push('<div class="tags">' + tags.join("") + "</div>");

    var b = [];
    var bookUrl = safeUrl(c.affiliate_url) || safeUrl(c.booking_url);
    if (bookUrl) b.push('<a class="btn main" href="' + esc(bookUrl) + '" target="_blank" rel="noopener' + (c.affiliate_url ? " sponsored" : "") + '">予約ページを開く</a>');
    if (safeUrl(c.official_url)) b.push('<a class="btn" href="' + esc(c.official_url) + '" target="_blank" rel="noopener">公式サイト</a>');
    if (c.tel) b.push('<a class="btn" href="tel:' + esc(c.tel.replace(/[^0-9+]/g, "")) + '">電話 ' + esc(c.tel) + "</a>");
    b.push('<a class="btn" href="https://www.google.com/maps/dir/?api=1&destination=' + c.lat + "," + c.lng + '" target="_blank" rel="noopener">経路（Googleマップ）</a>');
    h.push('<div class="btns">' + b.join("") + "</div>");

    if (c.facilities.length) {
      h.push('<div class="d-sec"><h3>設備</h3><div class="tags">' + c.facilities.map(function (f) { return '<span class="tag-i">' + esc(FAC_LABEL[f] || f) + "</span>"; }).join("") + "</div></div>");
    }

    var info = row("営業期間", c.season) + row("チェックイン", c.checkin) + row("チェックアウト", c.checkout) + row("住所", c.address);
    if (info) h.push('<div class="d-sec"><h3>基本情報</h3><dl>' + info + "</dl></div>");

    var tp = tips(c);
    if (tp.length) h.push('<div class="d-sec"><h3>持ち物のヒント</h3><ul>' + tp.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>");

    var src = [];
    if (c.verified_at) {
      src.push("情報の確認日：" + esc(c.verified_at) + (c.confidence === "low" ? '　<span class="warn">（予約サイトの掲載値。公式で要確認）</span>' : ""));
      if (safeUrl(c.source_url)) src.push('料金の出典：<a href="' + esc(c.source_url) + '" target="_blank" rel="noopener">' + esc(c.source_url.replace(/^https?:\/\//, "").slice(0, 48)) + "</a>");
      src.push("記載のない設備は「なし」ではなく未確認です。");
    } else {
      src.push("位置と名称は OpenStreetMap のデータです。料金・予約方法はまだ確認していません。");
    }
    h.push('<div class="d-src">' + src.join("<br>") + "</div>");
    return h.join("");
  }

  function setActive(id) {
    var prev = activeId;
    activeId = id;
    [prev, id].forEach(function (k) {
      if (k && markers[k]) markers[k].setIcon(iconFor(markers[k].camp));
    });
  }

  function openDetail(c, pan) {
    setActive(c.id);
    els.body.innerHTML = render(c);
    els.detail.hidden = false;
    els.detail.scrollTop = 0;
    if (pan) {
      var z = Math.max(map.getZoom(), 11);
      cluster.zoomToShowLayer(markers[c.id], function () { map.setView([c.lat, c.lng], z); keepVisible(c); });
    } else {
      keepVisible(c);
    }
    writeUrl(getState());
  }
  // 詳細パネルでピンが隠れないように地図をずらす
  function keepVisible(c) {
    var size = map.getSize();
    var pt = map.latLngToContainerPoint([c.lat, c.lng]);
    if (window.innerWidth < 900) {
      var target = size.y * 0.2;
      if (pt.y > size.y * 0.3) map.panBy([0, pt.y - target]);
    } else {
      var right = size.x - 410;
      if (pt.x > right) map.panBy([pt.x - right * 0.6, 0]);
    }
  }
  function closeDetail(silent) {
    els.detail.hidden = true;
    setActive(null);
    if (!silent) writeUrl(getState());
  }

  // 操作
  els.pref.addEventListener("change", function () { apply({ fit: true }); });
  els.max.addEventListener("change", function () { apply(); });
  var qTimer;
  els.q.addEventListener("input", function () { clearTimeout(qTimer); qTimer = setTimeout(apply, 250); });
  els.filters.addEventListener("change", function () { apply(); });
  function toggleFilters(open) {
    els.filters.hidden = !open;
    els.more.setAttribute("aria-expanded", open ? "true" : "false");
  }
  els.more.addEventListener("click", function () { toggleFilters(els.filters.hidden); });
  $("closeFilters").addEventListener("click", function () { toggleFilters(false); });
  $("reset").addEventListener("click", function () {
    els.filters.querySelectorAll("input").forEach(function (i) { i.checked = false; });
    els.pref.value = ""; els.max.value = ""; els.q.value = "";
    apply({ fit: true });
  });
  $("closeDetail").addEventListener("click", function () { closeDetail(); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { if (!els.filters.hidden) toggleFilters(false); else closeDetail(); }
  });

  // データ読み込み
  fetch("data/camps.json?v=2026-09-29a")
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) {
      camps = d.camps;
      camps.forEach(function (c) {
        var m = L.marker([c.lat, c.lng], { icon: iconFor(c), title: c.name, riseOnHover: true, zIndexOffset: c.total != null ? 500 : 0 });
        m.camp = c;
        m.on("click", function (e) { L.DomEvent.stopPropagation(e); openDetail(c, false); });
        markers[c.id] = m;
      });
      var initId = readUrl();
      apply({ fit: true });
      var init = initId && camps.filter(function (c) { return c.id === initId; })[0];
      if (init) openDetail(init, true);
    })
    .catch(function (err) {
      els.count.textContent = "データを読み込めませんでした（" + err.message + "）";
      console.error(err);
    });
})();
