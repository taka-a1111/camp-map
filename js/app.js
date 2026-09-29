/* キャンプ場マップ BUILD_TAG: 2026-09-29d */
(function () {
  "use strict";
  var BUILD = "2026-09-29d";
  console.log("BUILD_TAG: " + BUILD);

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
  var PARTY_KEYS = [
    { k: "a", label: "大人", min: 1, max: 10, def: 2 },
    { k: "c", label: "子供", min: 0, max: 10, def: 0 },
    { k: "tent", label: "テント", min: 1, max: 4, def: 1 },
    { k: "tarp", label: "タープ", min: 0, max: 3, def: 0 },
    { k: "car", label: "車", min: 0, max: 3, def: 1 }
  ];

  var $ = function (id) { return document.getElementById(id); };
  var els = {
    pref: $("pref"), budget: $("budget"), budgetBtn: $("budgetBtn"), q: $("q"), more: $("moreBtn"), badge: $("badge"), filters: $("filters"),
    count: $("count"), panel: $("detail"), body: $("detailBody"), pet: $("pet"), known: $("known"), nomt: $("nomt"),
    open: $("openOnly"), listBtn: $("listBtn"), toast: $("toast")
  };

  var camps = [];
  var markers = {};
  var activeId = null;
  var mode = null; // "detail" | "list" | null
  var hits = [];
  var party = {};
  var myPos = null;
  var sortBy = "price";
  var basis = "total"; // 予算とピンの金額の基準："total"（全員分の総額）｜"per"（1人あたり）
  var MAX_OPTS = { total: [0, 2000, 3000, 4000, 5000, 6000, 8000, 10000], per: [0, 1000, 1500, 2000, 2500, 3000, 4000] };

  // ---------- 地図 ----------
  var map = L.map("map", { zoomControl: true }).fitBounds(PREF_VIEW[""]);
  L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">地理院タイル</a> | 位置データの一部 © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>・住所検索：国土地理院'
  }).addTo(map);
  var cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45, spiderfyOnMaxZoom: true, chunkedLoading: true });
  map.addLayer(cluster);
  map.on("click", function () { if (mode === "detail") closePanel(); });

  // 現在地ボタン（右下）
  var meLayer = L.layerGroup().addTo(map);
  var Locate = L.Control.extend({
    options: { position: "bottomright" },
    onAdd: function () {
      var b = L.DomUtil.create("button", "locate-btn");
      b.type = "button";
      b.title = "現在地を表示";
      b.setAttribute("aria-label", "現在地を表示");
      b.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="currentColor"/><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 1v4M12 19v4M1 12h4M19 12h4" stroke="currentColor" stroke-width="2"/></svg>';
      L.DomEvent.disableClickPropagation(b);
      L.DomEvent.on(b, "click", locate);
      return b;
    }
  });
  map.addControl(new Locate());

  function locate() {
    if (!navigator.geolocation) { toast("この端末では現在地を取得できません"); return; }
    toast("現在地を取得しています…");
    navigator.geolocation.getCurrentPosition(function (p) {
      myPos = [p.coords.latitude, p.coords.longitude];
      meLayer.clearLayers();
      L.circle(myPos, { radius: Math.min(p.coords.accuracy, 2000), color: "#2a6fdb", weight: 1, fillOpacity: 0.12, interactive: false }).addTo(meLayer);
      L.circleMarker(myPos, { radius: 8, color: "#fff", weight: 3, fillColor: "#2a6fdb", fillOpacity: 1 }).bindTooltip("現在地").addTo(meLayer);
      map.setView(myPos, Math.max(map.getZoom(), 11));
      toast("");
      if (mode === "list") renderList();
    }, function (err) {
      toast(err.code === 1 ? "位置情報の利用が許可されていません（ブラウザの設定で許可してください）" : "現在地を取得できませんでした");
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  }

  var toastTimer;
  function toast(msg) {
    clearTimeout(toastTimer);
    els.toast.textContent = msg;
    els.toast.hidden = !msg;
    if (msg) toastTimer = setTimeout(function () { els.toast.hidden = true; }, 5000);
  }

  // ---------- 表示用 ----------
  function yen(n) { return n === 0 ? "無料" : Math.round(n).toLocaleString("ja-JP") + "円"; }
  function fee(n) { return n === 0 ? "なし" : Math.round(n).toLocaleString("ja-JP") + "円"; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function safeUrl(u) { return /^https?:\/\//.test(u || "") ? u : ""; }
  function kmBetween(a, b) {
    var r = 6371, t = Math.PI / 180;
    var dLat = (b[0] - a[0]) * t, dLng = (b[1] - a[1]) * t;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(a[0] * t) * Math.cos(b[0] * t) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * r * Math.asin(Math.sqrt(h));
  }

  // ---------- 料金の計算 ----------
  // 返り値：{ total, per, rows:[{label, amount|null}], unknown:[...], warn:[...] }（料金未確認なら null）
  function calc(c, P) {
    if (!c.priced) return null;
    var rows = [], unknown = [], warn = [];
    var A = P.a, C = P.c, people = A + C;
    function add(label, amount) { rows.push({ label: label, amount: amount }); if (amount == null) unknown.push(label); }

    add("サイト料" + (c.site_label ? "（" + c.site_label + "）" : ""), c.site_fee);

    var inc = c.people_included_in_site || 0;
    if (c.adult_fee) add("入場料・人数料金 大人 " + yen(c.adult_fee) + "×" + A + "人", c.adult_fee * A);
    else if (c.adult_fee == null) add("入場料・人数料金（大人）", null);
    if (C > 0 && !inc) {
      if (c.child_fee == null) add("子供の料金", null);
      else if (c.child_fee > 0) add("子供 " + yen(c.child_fee) + "×" + C + "人" + (c.child_label ? "（" + c.child_label + "）" : ""), c.child_fee * C);
    }
    if (inc > 0) {
      var exA = Math.max(0, A - inc);
      var left = Math.max(0, inc - A);
      var exC = Math.max(0, C - left);
      if (exA + exC > 0) {
        if (c.extra_person_fee == null) add("区画に含まれる" + inc + "人を超えた分", null);
        else {
          var childRate = c.child_fee ? c.child_fee : c.extra_person_fee;
          var amt = exA * c.extra_person_fee + exC * childRate;
          add("人数追加（" + inc + "人まで込み）大人" + exA + "人・子供" + exC + "人", amt);
        }
      }
    }
    if (P.tent > 0) {
      if (c.tent_included != null) {
        var exT = Math.max(0, P.tent - c.tent_included);
        if (exT > 0) {
          if (c.tent_fee == null) add("追加テント" + exT + "張", null);
          else add("追加テント " + yen(c.tent_fee) + "×" + exT + "張", c.tent_fee * exT);
        }
      } else if (P.tent > 1 && c.tent_fee == null) {
        add("2張目以降のテント", null);
      } else if (c.tent_fee) {
        add("テント " + yen(c.tent_fee) + "×" + P.tent + "張", c.tent_fee * P.tent);
      }
    }
    if (P.tarp > 0) {
      if (c.tarp_fee == null) add("タープ" + P.tarp + "張", null);
      else if (c.tarp_fee > 0) add("タープ " + yen(c.tarp_fee) + "×" + P.tarp + "張", c.tarp_fee * P.tarp);
    }
    if (P.car > 0) {
      if (c.vehicle_fee == null) add("車・駐車料金", null);
      else if (c.vehicle_fee > 0) add("車（1台目）", c.vehicle_fee);
      if (P.car > 1) warn.push("2台目以降の車の料金は下の注意書きを確認してください" + (c.vehicle_note ? "（" + c.vehicle_note + "）" : ""));
    }
    if (c.fixed_fee) add(c.fixed_label || "その他の料金", c.fixed_fee);
    if (c.per_person_tax) add("入湯税・宿泊税 " + yen(c.per_person_tax) + "×" + A + "人", c.per_person_tax * A);
    if (c.site_capacity && people > c.site_capacity) warn.push("1区画の定員は" + c.site_capacity + "人です。人数によっては2区画必要です");

    var total = rows.reduce(function (s, r) { return s + (r.amount || 0); }, 0);
    if (c.site_fee == null) return { total: null, per: null, rows: rows, unknown: unknown, warn: warn };
    return { total: total, per: people ? total / people : total, rows: rows, unknown: unknown, warn: warn };
  }

  function basisValue(r) { return basis === "total" ? r.total : r.per; }
  function priceText(r, which) {
    if (!r || r.total == null) return "";
    var v = Math.round(which === "per" ? r.per : which === "total" ? r.total : basisValue(r));
    return (v === 0 ? "無料" : "¥" + v.toLocaleString("ja-JP")) + (r.unknown.length ? "〜" : "");
  }

  function iconFor(c) {
    var r = c._calc;
    var active = c.id === activeId ? " is-active" : "";
    if (r && r.total != null) {
      return L.divIcon({ className: "pin" + active, html: '<div class="pin-price">' + priceText(r) + "</div>", iconSize: [0, 0] });
    }
    return L.divIcon({ className: "pin" + active, html: '<div class="pin-dot' + (c.status === "open" ? "" : " dim") + '"></div>', iconSize: [14, 14] });
  }

  // ---------- 条件 ----------
  function checked(key) {
    return Array.prototype.map.call(document.querySelectorAll('.chips[data-key="' + key + '"] input:checked'), function (i) { return i.value; });
  }
  function getState() {
    return {
      pref: els.pref.value, max: getMax(), q: els.q.value.trim(),
      types: checked("types"), book: checked("book"), fac: checked("fac"),
      pet: els.pet.checked, known: els.known.checked, nomt: els.nomt.checked, open: els.open.checked
    };
  }
  function norm(s) { return (s || "").normalize("NFKC").toLowerCase().replace(/\s/g, ""); }

  function match(c, s) {
    if (s.pref && c.pref !== s.pref) return false;
    var r = c._calc;
    if (s.max !== "") { if (!r || r.total == null || basisValue(r) > Number(s.max)) return false; }
    if (s.known && !(r && r.total != null)) return false;
    if (s.nomt && c.mountain) return false;
    if (s.open && c.status !== "open") return false;
    if (s.pet && c.pet !== true) return false;
    if (s.q) {
      var hay = norm(c.name + c.pref + (c.city || "") + (c.address || ""));
      var words = norm(s.q).split(/[,、]/).filter(Boolean);
      for (var i = 0; i < words.length; i++) if (hay.indexOf(words[i]) < 0) return false;
    }
    var st = c.site_types || [];
    if (s.types.length && !s.types.some(function (t) { return st.indexOf(t) >= 0; })) return false;
    if (s.book.length && s.book.indexOf(c.booking_type) < 0) return false;
    var fc = c.facilities || [];
    if (s.fac.length && !s.fac.every(function (f) { return fc.indexOf(f) >= 0; })) return false;
    return true;
  }

  function writeUrl(s) {
    var p = new URLSearchParams();
    if (s.pref) p.set("pref", s.pref);
    if (basis !== "total") p.set("basis", basis);
    if (s.max !== "") p.set("max", s.max);
    if (s.q) p.set("q", s.q);
    if (s.types.length) p.set("types", s.types.join(","));
    if (s.book.length) p.set("book", s.book.join(","));
    if (s.fac.length) p.set("fac", s.fac.join(","));
    ["pet", "known", "nomt", "open"].forEach(function (k) { if (s[k]) p.set(k, "1"); });
    PARTY_KEYS.forEach(function (d) { if (party[d.k] !== d.def) p.set("p" + d.k, party[d.k]); });
    if (activeId) p.set("id", activeId);
    var qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
  }
  function readUrl() {
    var p = new URLSearchParams(location.search);
    if (p.get("pref") && PREF_VIEW[p.get("pref")]) els.pref.value = p.get("pref");
    basis = p.get("basis") === "per" ? "per" : "total";
    document.querySelectorAll('input[name="basis"]').forEach(function (i) { i.checked = i.value === basis; });
    renderMaxChips();
    setMax(p.has("max") ? p.get("max") : "");
    if (p.get("q")) els.q.value = p.get("q");
    ["types", "book", "fac"].forEach(function (k) {
      var v = (p.get(k) || "").split(",");
      document.querySelectorAll('.chips[data-key="' + k + '"] input').forEach(function (i) { i.checked = v.indexOf(i.value) >= 0; });
    });
    els.pet.checked = p.get("pet") === "1";
    els.known.checked = p.get("known") === "1";
    els.nomt.checked = p.get("nomt") === "1";
    els.open.checked = p.get("open") === "1";
    PARTY_KEYS.forEach(function (d) {
      var v = parseInt(p.get("p" + d.k), 10);
      party[d.k] = isNaN(v) ? d.def : Math.min(d.max, Math.max(d.min, v));
    });
    return p.get("id");
  }

  // ---------- 人数・テントの入力 ----------
  function renderMaxChips() {
    var suf = basis === "total" ? "" : "/人";
    $("maxChips").innerHTML = '<label><input type="radio" name="max" value="" checked>指定なし</label>' + MAX_OPTS[basis].map(function (v) {
      return '<label><input type="radio" name="max" value="' + v + '">' + (v === 0 ? "無料" : "〜" + v.toLocaleString("ja-JP") + "円" + suf) + "</label>";
    }).join("");
  }
  function getMax() {
    var r = document.querySelector('input[name="max"]:checked');
    return r ? r.value : "";
  }
  function setMax(v) {
    document.querySelectorAll('input[name="max"]').forEach(function (i) { i.checked = i.value === v; });
    if (!document.querySelector('input[name="max"]:checked')) document.querySelector('input[name="max"][value=""]').checked = true;
  }
  function partyText() { return "大人" + party.a + (party.c ? "・子供" + party.c : ""); }
  function partyHtml(scope, keys) {
    return '<div class="party" data-scope="' + scope + '">' + PARTY_KEYS.filter(function (d) { return !keys || keys.indexOf(d.k) >= 0; }).map(function (d) {
      return '<div class="stepper"><span class="st-l">' + d.label + '</span><button type="button" data-k="' + d.k + '" data-d="-1" aria-label="' + d.label + 'を減らす">−</button><span class="st-v" data-v="' + d.k + '">' + party[d.k] + '</span><button type="button" data-k="' + d.k + '" data-d="1" aria-label="' + d.label + 'を増やす">＋</button></div>';
    }).join("") + "</div>";
  }
  function onPartyClick(e) {
    var b = e.target.closest("button[data-k]");
    if (!b) return;
    var d = PARTY_KEYS.filter(function (x) { return x.k === b.getAttribute("data-k"); })[0];
    party[d.k] = Math.min(d.max, Math.max(d.min, party[d.k] + Number(b.getAttribute("data-d"))));
    recalc();
    apply();
    if (mode === "detail" && activeId) renderDetail(byId(activeId), true);
  }
  function syncPartyUi() {
    document.querySelectorAll(".st-v").forEach(function (el) { el.textContent = party[el.getAttribute("data-v")]; });
    var m = getMax();
    $("budgetSummary").textContent = (m === "" ? "指定なし" : m === "0" ? "無料" : "〜" + Number(m).toLocaleString("ja-JP") + (basis === "total" ? "円（総額）" : "円/人")) + "・" + partyText();
    els.budgetBtn.classList.toggle("on", m !== "");
    $("gearSummary").textContent = "：テント" + party.tent + "・タープ" + party.tarp + "・車" + party.car;
  }

  function recalc() {
    camps.forEach(function (c) { c._calc = calc(c, party); });
    camps.forEach(function (c) { if (markers[c.id]) markers[c.id].setIcon(iconFor(c)); });
    syncPartyUi();
  }

  // ---------- 絞り込みと表示範囲 ----------
  function apply(opts) {
    var s = getState();
    hits = camps.filter(function (c) { return match(c, s); });
    cluster.clearLayers();
    cluster.addLayers(hits.map(function (c) { return markers[c.id]; }));
    var extra = s.types.length + s.book.length + s.fac.length + (s.pet ? 1 : 0) + (s.known ? 1 : 0) + (s.nomt ? 1 : 0) + (s.open ? 1 : 0);
    els.badge.hidden = extra === 0;
    els.badge.textContent = extra;
    if (activeId && !hits.some(function (c) { return c.id === activeId; }) && mode === "detail") closePanel(true);
    if (opts && opts.fit) map.fitBounds(PREF_VIEW[s.pref] || PREF_VIEW[""]);
    updateView();
    writeUrl(s);
  }

  // 地図を動かすたびに、表示範囲の件数と一覧を自動で更新する
  function inView() {
    var b = map.getBounds().pad(-0.02);
    return hits.filter(function (c) { return b.contains([c.lat, c.lng]); });
  }
  function updateView() {
    var v = inView();
    var priced = v.filter(function (c) { return c._calc && c._calc.total != null; }).length;
    els.count.textContent = "この範囲 " + v.length + "件 ／ 全" + hits.length + "件";
    els.count.title = "料金を確認済み：この範囲 " + priced + "件";
    els.listBtn.textContent = "一覧 " + v.length;
    if (mode === "list") renderList(v);
  }
  var moveTimer;
  map.on("moveend", function () { clearTimeout(moveTimer); moveTimer = setTimeout(updateView, 150); });

  // ---------- 一覧 ----------
  function renderList(v) {
    v = v || inView();
    var center = myPos || [map.getCenter().lat, map.getCenter().lng];
    v.forEach(function (c) { c._km = kmBetween(center, [c.lat, c.lng]); });
    v.sort(function (x, y) {
      if (sortBy === "price") {
        var px = x._calc && x._calc.total != null ? basisValue(x._calc) : Infinity;
        var py = y._calc && y._calc.total != null ? basisValue(y._calc) : Infinity;
        if (px !== py) return px - py;
      }
      return x._km - y._km;
    });
    var shown = v.slice(0, 150);
    var h = [];
    h.push('<div class="list-head"><h2 class="d-name">この範囲のキャンプ場 ' + v.length + "件</h2>");
    h.push('<div class="sort"><button type="button" data-sort="price"' + (sortBy === "price" ? ' class="on"' : "") + '>' + (basis === "total" ? "総額が安い順" : "1人あたりが安い順") + '</button><button type="button" data-sort="near"' + (sortBy === "near" ? ' class="on"' : "") + ">" + (myPos ? "現在地から近い順" : "地図の中心から近い順") + "</button></div>");
    h.push('<p class="list-note">地図を動かすと自動で入れ替わります。料金は' + esc(partyText()) + "で計算した" + (basis === "total" ? "全員分の総額" : "1人あたり") + "の目安です。</p></div>");
    if (!v.length) h.push('<p class="empty">この範囲に条件に合うキャンプ場はありません。地図を縮小するか、条件をゆるめてください。</p>');
    h.push('<ul class="list">');
    shown.forEach(function (c) {
      var r = c._calc;
      var price = r && r.total != null ? '<span class="li-price">' + priceText(r) + '<small>' + (basis === "total" ? "（" + (party.a + party.c) + "人）" : "/人") + '</small></span>' : '<span class="li-price none">料金未確認</span>';
      h.push('<li><button type="button" data-id="' + esc(c.id) + '"><span class="li-main"><span class="li-name">' + esc(c.name) + '</span><span class="li-sub">' + esc(c.pref + (c.city ? " " + c.city : "")) + " ・ " + c._km.toFixed(c._km < 10 ? 1 : 0) + "km" + (c.status !== "open" ? " ・ 営業状況未確認" : "") + "</span></span>" + price + "</button></li>");
    });
    h.push("</ul>");
    if (v.length > shown.length) h.push('<p class="list-note">ほか ' + (v.length - shown.length) + "件。地図を拡大すると絞り込めます。</p>");
    els.body.innerHTML = h.join("");
  }

  // ---------- 詳細 ----------
  function row(label, val) { return val ? "<dt>" + esc(label) + "</dt><dd>" + esc(val) + "</dd>" : ""; }

  function tips(c) {
    var t = [];
    var st = c.site_types || [];
    if (c.booking_type === "none") t.push("予約不要：連休や夏休みは早めの到着が安心です");
    if (st.indexOf("free") >= 0) t.push("フリーサイト：平らな場所を選べるよう、明るいうちの設営がおすすめです");
    if (c.pet === true) t.push("ペット可：リードと足ふきタオル、ペット用の水を用意");
    if (c.mountain) t.push("山岳テント場：軽量の装備と防寒着を。車は近くまで入れません");
    if ((c.facilities || []).indexOf("onsen") >= 0) t.push("温泉あり：タオルと着替えを多めに");
    return t;
  }

  function priceBlock(c) {
    var r = c._calc;
    var h = [];
    h.push('<div class="d-price">');
    h.push('<div class="lbl">料金の目安（1泊）</div>');
    h.push(partyHtml("detail"));
    if (!r) {
      h.push('<div class="total unknown">料金は未確認</div>');
      h.push('<p class="d-note">公式サイトで料金を確認してください。</p></div>');
      return h.join("");
    }
    if (r.total == null) {
      h.push('<div class="total unknown">サイト料が未確認</div>');
    } else {
      var people = party.a + party.c;
      var tot = '<div><span class="lbl">総額（' + people + '人・1泊）</span><span class="total' + (basis === "total" ? "" : " sub") + '">' + yen(r.total) + (r.unknown.length ? "〜" : "") + "</span></div>";
      var per = '<div><span class="lbl">1人あたり（総額÷' + people + '人）</span><span class="total' + (basis === "per" ? "" : " sub") + '">' + priceText(r, "per") + "</span></div>";
      h.push('<div class="totals">' + (basis === "total" ? tot + per : per + tot) + "</div>");
    }
    h.push("<table>");
    r.rows.forEach(function (x) {
      h.push("<tr><td>" + esc(x.label) + "</td><td>" + (x.amount == null ? '<span class="warn">未確認</span>' : fee(x.amount)) + "</td></tr>");
    });
    h.push("</table>");
    if (r.unknown.length) h.push('<p class="d-note warn">未確認の料金（' + esc(r.unknown.join("、")) + "）は合計に含んでいません。</p>");
    r.warn.forEach(function (w) { h.push('<p class="d-note warn">' + esc(w) + "</p>"); });
    var inc = [];
    if (c.site_includes) inc.push("区画に含まれるもの：" + c.site_includes);
    if (c.adult_label && c.adult_fee) inc.push("大人：" + c.adult_label);
    if (c.child_label) inc.push("子供：" + c.child_label + (c.child_fee != null ? " " + fee(c.child_fee) : ""));
    if (c.infant_fee != null) inc.push("未就学児：" + (c.infant_fee === 0 ? "無料" : yen(c.infant_fee)));
    if (c.tarp_fee != null) inc.push("タープ：" + (c.tarp_fee === 0 ? "追加料金なし" : yen(c.tarp_fee) + "/張"));
    if (c.vehicle_note) inc.push("車：" + c.vehicle_note);
    if (c.fee_note) inc.push(c.fee_note);
    if (inc.length) h.push('<ul class="d-inc">' + inc.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>");
    h.push("</div>");
    return h.join("");
  }

  function renderDetail(c, keepScroll) {
    var top = els.panel.scrollTop;
    var h = [];
    if (listWasOpen) h.push('<button type="button" class="back" id="backToList">← 一覧に戻る</button>');
    h.push('<h2 class="d-name">' + esc(c.name) + "</h2>");
    h.push('<p class="d-area">' + esc(c.pref + (c.city ? " " + c.city : "")) + (c.mountain ? "　山岳テント場" : "") + "</p>");
    if (c.status !== "open") h.push('<p class="notice">営業しているかは未確認です（掲載元：' + esc(c.source || "") + "）。行く前に必ず確認してください。</p>");
    h.push(priceBlock(c));

    var tags = [];
    tags.push('<span class="tag-i book">' + esc(BOOK_LABEL[c.booking_type] || "予約方法 未確認") + "</span>");
    (c.site_types || []).forEach(function (t) { tags.push('<span class="tag-i">' + esc(TYPE_LABEL[t] || t) + "</span>"); });
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

    if ((c.facilities || []).length) {
      h.push('<div class="d-sec"><h3>設備</h3><div class="tags">' + c.facilities.map(function (f) { return '<span class="tag-i">' + esc(FAC_LABEL[f] || f) + "</span>"; }).join("") + "</div></div>");
    }
    var info = row("営業期間", c.season) + row("チェックイン", c.checkin) + row("チェックアウト", c.checkout) + row("住所", c.address) + row("サイトの種類", !c.priced ? c.types_text : "");
    if (info) h.push('<div class="d-sec"><h3>基本情報</h3><dl>' + info + "</dl></div>");

    var tp = tips(c);
    if (tp.length) h.push('<div class="d-sec"><h3>持ち物のヒント</h3><ul>' + tp.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>");

    var src = [];
    if (c.verified_at) {
      src.push("料金の確認日：" + esc(c.verified_at) + (c.confidence === "low" ? '　<span class="warn">（予約サイトの掲載値。公式で要確認）</span>' : ""));
      if (safeUrl(c.source_url)) src.push('料金の出典：<a href="' + esc(c.source_url) + '" target="_blank" rel="noopener">' + esc(c.source_url.replace(/^https?:\/\//, "").slice(0, 48)) + "</a>");
      src.push("記載のない設備は「なし」ではなく未確認です。");
    } else {
      src.push("掲載元：" + esc(c.source || "OpenStreetMap") + (safeUrl(c.source_url) ? '（<a href="' + esc(c.source_url) + '" target="_blank" rel="noopener">ページ</a>）' : ""));
    }
    if (c.geo === "area") src.push("地図上の位置は住所（地区）からの目安で、実際の場所とずれることがあります。");
    src.push("料金は目安です。予約前に必ず公式サイトで確認してください。");
    h.push('<div class="d-src">' + src.join("<br>") + "</div>");
    els.body.innerHTML = h.join("");
    els.panel.scrollTop = keepScroll ? top : 0;
  }

  function byId(id) { return camps.filter(function (c) { return c.id === id; })[0]; }

  function setActive(id) {
    var prev = activeId;
    activeId = id;
    [prev, id].forEach(function (k) { if (k && markers[k]) markers[k].setIcon(iconFor(markers[k].camp)); });
  }

  var listWasOpen = false;
  function openDetail(c, pan) {
    listWasOpen = mode === "list" || (mode === "detail" && listWasOpen);
    mode = "detail";
    panelOpen(true);
    setActive(c.id);
    els.panel.hidden = false;
    els.panel.classList.remove("is-list");
    renderDetail(c);
    if (pan) {
      var z = Math.max(map.getZoom(), 12);
      cluster.zoomToShowLayer(markers[c.id], function () { map.setView([c.lat, c.lng], z); keepVisible(c); });
    } else {
      keepVisible(c);
    }
    writeUrl(getState());
  }
  function panelOpen(on) { document.querySelector(".stage").classList.toggle("panel-open", on); }
  function openList() {
    panelOpen(true);
    mode = "list";
    listWasOpen = false;
    setActive(null);
    els.panel.hidden = false;
    els.panel.classList.add("is-list");
    renderList();
    els.panel.scrollTop = 0;
    writeUrl(getState());
  }
  function keepVisible(c) {
    var size = map.getSize();
    var pt = map.latLngToContainerPoint([c.lat, c.lng]);
    if (window.innerWidth < 900) {
      if (pt.y > size.y * 0.3) map.panBy([0, pt.y - size.y * 0.2]);
    } else {
      var right = size.x - 410;
      if (pt.x > right) map.panBy([pt.x - right * 0.6, 0]);
    }
  }
  function closePanel(silent) {
    els.panel.hidden = true;
    panelOpen(false);
    mode = null;
    listWasOpen = false;
    setActive(null);
    if (!silent) writeUrl(getState());
  }

  // ---------- 操作 ----------
  els.pref.addEventListener("change", function () { apply({ fit: true }); });
  var qTimer;
  els.q.addEventListener("input", function () { clearTimeout(qTimer); qTimer = setTimeout(apply, 250); });
  els.filters.addEventListener("change", function () { apply(); });
  els.budget.addEventListener("change", function (e) {
    if (e.target.name === "basis") {
      basis = e.target.value;
      renderMaxChips();
      recalc();
      if (mode === "detail" && activeId) renderDetail(byId(activeId), true);
    }
    syncPartyUi();
    apply();
  });
  function toggleFilters(open) {
    els.filters.hidden = !open;
    els.more.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) toggleBudget(false);
  }
  function toggleBudget(open) {
    els.budget.hidden = !open;
    els.budgetBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) toggleFilters(false);
  }
  els.budgetBtn.addEventListener("click", function () { toggleBudget(els.budget.hidden); });
  $("closeBudget").addEventListener("click", function () { toggleBudget(false); });
  $("budgetReset").addEventListener("click", function () {
    setMax("");
    PARTY_KEYS.forEach(function (d) { party[d.k] = d.def; });
    recalc();
    apply();
    if (mode === "detail" && activeId) renderDetail(byId(activeId), true);
  });
  els.more.addEventListener("click", function () { toggleFilters(els.filters.hidden); });
  $("closeFilters").addEventListener("click", function () { toggleFilters(false); });
  $("reset").addEventListener("click", function () {
    els.filters.querySelectorAll('input[type="checkbox"]').forEach(function (i) { i.checked = false; });
    els.pref.value = ""; els.q.value = "";
    apply({ fit: true });
  });
  els.listBtn.addEventListener("click", function () { if (mode === "list") closePanel(); else openList(); });
  $("closeDetail").addEventListener("click", function () { closePanel(); });
  els.body.addEventListener("click", function (e) {
    var li = e.target.closest("button[data-id]");
    if (li) { openDetail(byId(li.getAttribute("data-id")), true); return; }
    var s = e.target.closest("button[data-sort]");
    if (s) { sortBy = s.getAttribute("data-sort"); renderList(); return; }
    if (e.target.id === "backToList") { openList(); return; }
    onPartyClick(e);
  });
  els.budget.addEventListener("click", onPartyClick);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (!els.filters.hidden) toggleFilters(false);
      else if (!els.budget.hidden) toggleBudget(false);
      else closePanel();
    }
  });

  // ---------- データ読み込み ----------
  fetch("data/camps.json?v=" + BUILD)
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) {
      camps = d.camps;
      var initId = readUrl();
      $("partyPeople").innerHTML = partyHtml("budget", ["a", "c"]);
      $("partyGear").innerHTML = partyHtml("budget", ["tent", "tarp", "car"]);
      var pricedCount = camps.filter(function (c) { return c.priced; }).length;
      $("budgetHint").textContent = "予算で絞り込めるのは、料金を確認済みのキャンプ場（現在" + pricedCount + "件）だけです。子供の料金は各キャンプ場の区分（小学生など）で計算します。";
      camps.forEach(function (c) {
        c._calc = calc(c, party);
        var m = L.marker([c.lat, c.lng], { icon: iconFor(c), title: c.name, riseOnHover: true, zIndexOffset: c._calc ? 500 : 0 });
        m.camp = c;
        m.on("click", function (e) { L.DomEvent.stopPropagation(e); openDetail(c, false); });
        markers[c.id] = m;
      });
      syncPartyUi();
      apply({ fit: true });
      var init = initId && byId(initId);
      if (init) openDetail(init, true);
    })
    .catch(function (err) {
      els.count.textContent = "データを読み込めませんでした（" + err.message + "）";
      console.error(err);
    });
})();
