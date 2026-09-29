# キャンプ場マップ（自分用MVP）

愛知・岐阜・長野・静岡・三重のキャンプ場を地図で探すサイト。検索エンジンには載らない設定（noindex・robots.txt）です。

## 仕組み

- `data/osm_raw.json`：OpenStreetMap から取得した位置と名称（GitHub Actions が毎月自動更新）
- `data/manual.json`：公式サイト等で確認した料金・予約方法・設備（手で追記する）
- `data/camps.json`：上の2つを合わせたもの。サイトはこれだけを読む
- `scripts/fetch_osm.py`：OpenStreetMap からの取得
- `scripts/build_data.py`：camps.json の作成

`data/manual.json` を更新して push すると、Actions が camps.json を作り直して GitHub Pages に公開します。OpenStreetMap の取り直しは毎月1回（Actions の手動実行でも可）。

## 料金の考え方

表示・検索に使う総額は「大人2人・車1台・テント1張で1泊」。

総額 = site_fee（サイト料）+ adult_fee（大人1人の入場料・人数料金）× 2 + other_fee（車両料金など必ずかかるもの）

未確認の項目は null にしておくと、画面では「未確認」と表示され、予算の絞り込みからは外れます。

## 出典

- 地図：国土地理院 地理院タイル
- キャンプ場の位置・名称：© OpenStreetMap contributors（ODbL）
