# キャンプ場マップ（自分用MVP）

愛知・岐阜・長野・静岡・三重のキャンプ場を地図で探すサイト。検索エンジンには載らない設定（noindex・robots.txt）です。

## 仕組み

- `data/osm_raw.json`：OpenStreetMap から取得した位置と名称（GitHub Actions が毎月自動更新）
- `data/coverage.json`：自治体・観光協会・公式サイト等で洗い出したキャンプ場一覧（1,348件。閉鎖も記録）
- `data/geocode_cache.json`：coverage.json の住所を国土地理院の住所検索で位置に変換した結果
- `data/manual.json`：公式サイト等で確認した料金の内訳・予約方法・設備（手で追記する）
- `data/camps.json`：上の2つを合わせたもの。サイトはこれだけを読む
- `scripts/fetch_osm.py`：OpenStreetMap からの取得
- `scripts/geocode.py`：住所から位置への変換（新しい住所だけ問い合わせる）
- `scripts/build_data.py`：camps.json の作成

`data/manual.json` を更新して push すると、Actions が camps.json を作り直して GitHub Pages に公開します。OpenStreetMap の取り直しは毎月1回（Actions の手動実行でも可）。

## 料金の考え方

画面で選んだ人数・テント・タープ・車の数から合計を計算し、1人あたり（合計÷大人と子供の人数）を表示・検索に使う。

合計 = site_fee + 大人×adult_fee + 子供×child_fee + 区画に含まれる人数を超えた分×extra_person_fee + 追加テント×tent_fee + タープ×tarp_fee + 車×vehicle_fee + fixed_fee + 大人×per_person_tax

未確認の項目は null にしておくと、画面では「未確認」と表示され、合計には含めません（金額の後ろに「〜」が付きます）。

## 出典

- 地図：国土地理院 地理院タイル
- キャンプ場の位置・名称：© OpenStreetMap contributors（ODbL）
