# ミンダナオ本島の建物ポリゴン抽出（GlobalBuildingAtlas）

[GlobalBuildingAtlas](https://github.com/zhu-xlab/GlobalBuildingAtlas) の公式 5°×5° GeoJSON タイルから、フィリピン・ミンダナオ**本島**の建物ポリゴンを切り出し、1 つの GeoJSON にまとめる再現可能なツールです。

フィジー向けの先行実装: [fiji_buildings_from_GlobalBuildingAtlas](https://github.com/shirokawakita/fiji_buildings_from_GlobalBuildingAtlas)

> **注意:** GlobalBuildingAtlas 公式は Web Viewer の WFS を可視化専用とし、一括抽出を禁止しています。本ツールは Hugging Face 上の公式タイル配布から取得します。

---

## データ提供サービス・サイトの紹介

本ツールが利用する建物データの元は、ミュンヘン工科大学（TUM）Data Science in Earth Observation グループが公開している **GlobalBuildingAtlas（GBA）** です。

| 項目 | 内容 |
|------|------|
| 概要 | 全球の建物ポリゴン・高さ・LoD1 3D モデルを提供するオープンデータセット |
| 論文 | [Zhu et al., ESSD 2025](https://essd.copernicus.org/articles/17/6647/2025/)（DOI: [10.5194/essd-17-6647-2025](https://doi.org/10.5194/essd-17-6647-2025)） |
| GitHub（プロジェクト） | https://github.com/zhu-xlab/GlobalBuildingAtlas |
| Hugging Face（ODbL ポリゴン） | https://huggingface.co/datasets/zhu-xlab/GBA.ODbLPolygon |
| Hugging Face（その他ポリゴン / LoD1） | https://huggingface.co/datasets/zhu-xlab/GBA.LoD1 |
| mediaTUM（高さラスタ等） | https://mediatum.ub.tum.de/1782307 |
| Web Viewer（閲覧専用） | プロジェクト README 参照（一括抽出には使わない） |
| 利用条件ページ | https://tubvsig-so2sat-vm1.srv.mwn.de/terms_of_use.html |

行政境界マスクには [geoBoundaries](https://www.geoboundaries.org/)（Open license / CC BY 4.0）のフィリピン ADM0 を使用します。

---

## ライセンス（必ず確認）

### 本リポジトリのコード

本リポジトリのスクリプト・ドキュメントは **MIT License**（[LICENSE](LICENSE)）です。

### GlobalBuildingAtlas データ（本ツールがダウンロード・切り出す対象）

データはライセンスが分割されています。出力 GeoJSON の各フィーチャ `properties.source` で系統を区別します。

| `source` | データ内容 | 配布場所 | ライセンス | 商用利用 |
|----------|------------|----------|------------|----------|
| `odbl` | OSM / Microsoft 由来の建物ポリゴン | [GBA.ODbLPolygon](https://huggingface.co/datasets/zhu-xlab/GBA.ODbLPolygon) | [ODbL v1.0](https://opendatacommons.org/licenses/odbl/1-0/) | ODbL の条件に従う |
| `polygon` | Google Open Buildings 等由来の建物ポリゴン | [GBA.LoD1](https://huggingface.co/datasets/zhu-xlab/GBA.LoD1) の `Polygon/` | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | **不可（非商用のみ）** |

追加の注意:

- GlobalBuildingAtlas 本体ソフトウェア／一部配布物は **MIT with Commons Clause**（商用の「販売」制限）です。詳細は [公式 LICENSE](https://github.com/zhu-xlab/GlobalBuildingAtlas/blob/main/LICENSE) と [Terms of Use](https://tubvsig-so2sat-vm1.srv.mwn.de/terms_of_use.html) を確認してください。
- Part I と Part II を**結合した成果物**の利用可否は、データ提供元が利用者側でのライセンス確認を求めています。法的助言は本リポジトリでは提供しません。
- 本リポジトリは **建物データ本体（数 GB）を GitHub に含めません**。利用時は上記 Hugging Face から各自が取得します。

### 行政境界（geoBoundaries）

| 項目 | 内容 |
|------|------|
| サイト | https://www.geoboundaries.org/ |
| データ | Philippines ADM0（`gbOpen`） |
| ライセンス | CC BY 4.0（geoBoundaries Open） |

### 帰属・引用

GlobalBuildingAtlas を利用する場合は、データ提供元の要求に従い論文を引用してください（下記「引用」）。

---

## 対象範囲

- **ミンダナオ本島のみ**（ザンボアンガ半島を含む陸続きの本体）
- マスク: geoBoundaries フィリピン ADM0 のうち、内点 `(124.83, 7.66)` を含むポリゴン
- **含まない**: バシラン、カミギン、シアルガオ、ディナガット、スールー諸島など離島
- 概略範囲: 緯度 約 5.5–10.1°、経度 約 121.4–126.6°（日付変更線は跨がない）

---

## 再現手順

### 前提

- Python 3.11（Anaconda / Miniconda 推奨）
- ディスク空き: ダウンロード約 4 GB + 出力約 3 GB + HF キャッシュ分
- ネットワーク: Hugging Face へのアクセス

### 1. クローンと環境構築

```bash
git clone https://github.com/shirokawakita/mindanao_buildings_from_GlobalBuildingAtlas.git
cd mindanao_buildings_from_GlobalBuildingAtlas

conda create -n buildings_mindanao python=3.11 -y
conda activate buildings_mindanao
pip install -r requirements.txt
```

### 2. 抽出の実行

```bash
python extract_mindanao_buildings.py
```

処理内容:

1. geoBoundaries PHL ADM0 を取得し、本島ポリゴンを `data/mindanao_island.geojson` に保存
2. Hugging Face から該当 5°タイルを `data/raw/{odbl,polygon}/` へダウンロード
3. `ijson` でストリーム読み（タイル座標は **EPSG:3857**）
4. 本島マスクを EPSG:3857 に変換し、包絡矩形 → 交差判定でフィルタ
5. 通過ジオメトリを **EPSG:4326** に変換し `output/mindanao_buildings.geojson` へ書き出し

既存タイルだけで再クリップする場合:

```bash
python extract_mindanao_buildings.py --skip-download
```

### 3. 検証

```bash
python verify_output.py
```

本島マスク外・パディング付き bbox 外の件数が 0 であること、件数・系統別カウント・バウンディングボックスを確認します。結果は `output/verification_summary.json` に保存されます。

### ダウンロードするタイル

| 系統 | ファイル |
|------|----------|
| ODbL | `asiaeast/e120_n10_e125_n05.geojson`, `asiaeast/e125_n10_e130_n05.geojson` |
| Polygon | `Polygon/asiaeast/e120_n10_e125_n05.geojson`, `Polygon/asiaeast/e125_n10_e130_n05.geojson` |

マスク北端が緯度 10° を超える場合のみ、`e120_n15_e125_n10` / `e125_n15_e130_n10` を追加します（本再現では北端 約 9.82° のため不要）。

高さラスタと LoD1 JSON は取得しません（2D ポリゴンのみ）。

---

## 出力

| パス | 内容 | GitHub 同梱 |
|------|------|-------------|
| `data/mindanao_island.geojson` | クリップ用本島マスク | あり（参考） |
| `data/raw/` | ダウンロードした 5°タイル | **なし**（実行時取得） |
| `output/mindanao_buildings.geojson` | 本島の建物（EPSG:4326） | **なし**（実行時生成） |
| `output/verification_summary.json` | 検証サマリ | あり（参考） |

各フィーチャの主なプロパティ:

- `source`: `odbl` または `polygon`（本ツールが付与する系統ラベル）
- `gba_id` / 元タイルの属性: データセット側の ID 等

### 本リポジトリでの実行結果（参考）

| 項目 | 値 |
|------|-----|
| 建物数 | 7,941,088 |
| `odbl` | 2,098,114 |
| `polygon` | 5,842,974 |
| 出力サイズ | 約 3.2 GB |
| データ範囲 | 経度 121.90–126.60、緯度 5.56–9.82 |
| 本島外件数 | 0 |

```python
import geopandas as gpd

# ファイルが大きいため、必要なら空間フィルタや pyogrio の部分読み込みを推奨
gdf = gpd.read_file("output/mindanao_buildings.geojson")
print(len(gdf), gdf.crs, gdf.total_bounds)
print(gdf["source"].value_counts())
```

---

## リポジトリ構成

```
.
├── LICENSE                          # 本ツールの MIT
├── README.md
├── requirements.txt
├── extract_mindanao_buildings.py    # 抽出メイン
├── verify_output.py                 # 検証
├── data/
│   └── mindanao_island.geojson      # 本島マスク（参考同梱）
└── output/
    └── verification_summary.json    # 検証結果（参考同梱）
```

---

## 引用

```bibtex
@Article{essd-17-6647-2025,
AUTHOR = {Zhu, X. X. and Chen, S. and Zhang, F. and Shi, Y. and Wang, Y.},
TITLE = {GlobalBuildingAtlas: an open global and complete dataset of building polygons, heights and LoD1 3D models},
JOURNAL = {Earth System Science Data},
VOLUME = {17},
YEAR = {2025},
NUMBER = {12},
PAGES = {6647--6668},
URL = {https://essd.copernicus.org/articles/17/6647/2025/},
DOI = {10.5194/essd-17-6647-2025}
}
```

geoBoundaries を使う場合は、geoBoundaries の引用方針にも従ってください: https://www.geoboundaries.org/
