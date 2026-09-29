#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GlobalBuildingAtlas からミンダナオ本島の建物ポリゴンを抽出し GeoJSON で出力する。

公式 5°×5° タイルを Hugging Face から取得し、本島ポリゴンでクリップする。
WFS 一括取得は公式が禁止しているため使わない。

使用例:
  python extract_mindanao_buildings.py
  python extract_mindanao_buildings.py --skip-download
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import geopandas as gpd
import ijson
import requests
from huggingface_hub import hf_hub_download
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union
from shapely.prepared import prep

# GBA タイルは Web Mercator（EPSG:3857）。出力は WGS84（EPSG:4326）。
TILE_CRS = "EPSG:3857"
OUTPUT_CRS = "EPSG:4326"
TO_WGS84 = Transformer.from_crs(TILE_CRS, OUTPUT_CRS, always_xy=True).transform
TO_MERCATOR = Transformer.from_crs(OUTPUT_CRS, TILE_CRS, always_xy=True).transform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = ROOT / "output"
MASK_PATH = DATA_DIR / "mindanao_island.geojson"
OUTPUT_PATH = OUTPUT_DIR / "mindanao_buildings.geojson"

# ミンダナオ本島の内点（島の中央付近）
MINDANAO_SEED = Point(124.83, 7.66)

# geoBoundaries フィリピン ADM0
GEOBOUNDARIES_PHL_ADM0 = (
    "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/"
    "gbOpen/PHL/ADM0/geoBoundaries-PHL-ADM0.geojson"
)

# GBA 5° タイル（本島の概略範囲 5.5–10.1N, 121.4–126.6E を覆う）
BASE_TILES: List[Dict[str, Any]] = [
    {
        "name": "e120_n10_e125_n05.geojson",
        "repo": "zhu-xlab/GBA.ODbLPolygon",
        "repo_path": "asiaeast/e120_n10_e125_n05.geojson",
        "source": "odbl",
        "subdir": "odbl",
    },
    {
        "name": "e125_n10_e130_n05.geojson",
        "repo": "zhu-xlab/GBA.ODbLPolygon",
        "repo_path": "asiaeast/e125_n10_e130_n05.geojson",
        "source": "odbl",
        "subdir": "odbl",
    },
    {
        "name": "e120_n10_e125_n05.geojson",
        "repo": "zhu-xlab/GBA.LoD1",
        "repo_path": "Polygon/asiaeast/e120_n10_e125_n05.geojson",
        "source": "polygon",
        "subdir": "polygon",
    },
    {
        "name": "e125_n10_e130_n05.geojson",
        "repo": "zhu-xlab/GBA.LoD1",
        "repo_path": "Polygon/asiaeast/e125_n10_e130_n05.geojson",
        "source": "polygon",
        "subdir": "polygon",
    },
]

# 北端が 10° を超える場合のみ追加
NORTH_TILES: List[Dict[str, Any]] = [
    {
        "name": "e120_n15_e125_n10.geojson",
        "repo": "zhu-xlab/GBA.ODbLPolygon",
        "repo_path": "asiaeast/e120_n15_e125_n10.geojson",
        "source": "odbl",
        "subdir": "odbl",
    },
    {
        "name": "e125_n15_e130_n10.geojson",
        "repo": "zhu-xlab/GBA.ODbLPolygon",
        "repo_path": "asiaeast/e125_n15_e130_n10.geojson",
        "source": "odbl",
        "subdir": "odbl",
    },
    {
        "name": "e120_n15_e125_n10.geojson",
        "repo": "zhu-xlab/GBA.LoD1",
        "repo_path": "Polygon/asiaeast/e120_n15_e125_n10.geojson",
        "source": "polygon",
        "subdir": "polygon",
    },
    {
        "name": "e125_n15_e130_n10.geojson",
        "repo": "zhu-xlab/GBA.LoD1",
        "repo_path": "Polygon/asiaeast/e125_n15_e130_n10.geojson",
        "source": "polygon",
        "subdir": "polygon",
    },
]

PROGRESS_INTERVAL = 100_000


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "odbl").mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "polygon").mkdir(parents=True, exist_ok=True)


def download_geoboundaries(dest: Path) -> Path:
    """フィリピン ADM0 を取得する。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("ADM0 キャッシュを使用: %s", dest)
        return dest

    logger.info("geoBoundaries PHL ADM0 をダウンロード中...")
    response = requests.get(GEOBOUNDARIES_PHL_ADM0, timeout=120)
    response.raise_for_status()
    dest.write_bytes(response.content)
    logger.info("保存: %s (%.1f KB)", dest, dest.stat().st_size / 1024)
    return dest


def extract_mindanao_island(adm0_path: Path, output_path: Path) -> BaseGeometry:
    """
    ADM0 MultiPolygon から、ミンダナオ本島の内点を含むポリゴンを抽出する。
    """
    logger.info("ミンダナオ本島マスクを作成中...")
    gdf = gpd.read_file(adm0_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    geom = unary_union(gdf.geometry.values)
    if geom.geom_type == "Polygon":
        parts = [geom]
    elif geom.geom_type == "MultiPolygon":
        parts = list(geom.geoms)
    else:
        raise ValueError(f"想定外のジオメトリ型: {geom.geom_type}")

    mindanao = None
    for part in parts:
        if part.contains(MINDANAO_SEED) or part.intersects(MINDANAO_SEED):
            mindanao = part
            break

    if mindanao is None:
        # フォールバック: シードに最も近いポリゴン
        mindanao = min(parts, key=lambda g: g.distance(MINDANAO_SEED))
        logger.warning(
            "シード点がどのポリゴンにも含まれませんでした。"
            "最近傍ポリゴンを使用します (距離=%.6f°)",
            mindanao.distance(MINDANAO_SEED),
        )

    mask_gdf = gpd.GeoDataFrame(
        {"name": ["Mindanao"], "geometry": [mindanao]},
        crs="EPSG:4326",
    )
    mask_gdf.to_file(output_path, driver="GeoJSON")
    bounds = mindanao.bounds
    logger.info(
        "本島マスク保存: %s | bounds=(%.4f, %.4f, %.4f, %.4f) | area≈%.2f deg²",
        output_path,
        bounds[0],
        bounds[1],
        bounds[2],
        bounds[3],
        mindanao.area,
    )
    return mindanao


def select_tiles(mask_bounds: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    """マスク範囲に応じてダウンロード対象タイルを選ぶ。"""
    tiles = list(BASE_TILES)
    max_lat = mask_bounds[3]
    if max_lat > 10.0:
        logger.info("マスク北端が %.4f° > 10° のため、北タイルを追加します", max_lat)
        tiles.extend(NORTH_TILES)
    else:
        logger.info("マスク北端が %.4f° ≤ 10° のため、北タイルは不要です", max_lat)
    return tiles


def download_tile(tile: Dict[str, Any]) -> Path:
    """Hugging Face から 1 タイルを取得し data/raw に置く。"""
    dest_dir = RAW_DIR / tile["subdir"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / tile["name"]

    if dest.exists() and dest.stat().st_size > 0:
        logger.info("既存タイルを使用: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
        return dest

    logger.info(
        "ダウンロード中: %s / %s ...",
        tile["repo"],
        tile["repo_path"],
    )
    # HF キャッシュへ取得し、最終パスへコピー（巨大ファイルのため read_bytes は使わない）
    downloaded = hf_hub_download(
        repo_id=tile["repo"],
        filename=tile["repo_path"],
        repo_type="dataset",
    )
    downloaded_path = Path(downloaded)
    if downloaded_path.resolve() != dest.resolve():
        shutil.copyfile(downloaded_path, dest)
    logger.info("保存: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def bboxes_disjoint(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
) -> bool:
    return a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3]


def stream_clip_tile(
    tile_path: Path,
    source: str,
    mask_mercator: BaseGeometry,
    mask_bounds_mercator: Tuple[float, float, float, float],
    out_fh,
    seen_ids: Set[str],
    first_feature: List[bool],
) -> Tuple[int, int, int]:
    """
    タイル（EPSG:3857）をストリーム読みし、本島と交差する建物だけを
    EPSG:4326 で出力へ追記する。

    Returns:
        (読込件数, 包絡矩形通過件数, 出力件数)
    """
    prepared = prep(mask_mercator)
    read_count = 0
    bbox_pass = 0
    written = 0

    logger.info("処理中: %s (source=%s)", tile_path.name, source)
    with tile_path.open("rb") as fh:
        # use_float=True: Decimal を避け、数値を float として読む
        for feature in ijson.items(fh, "features.item", use_float=True):
            read_count += 1
            if read_count % PROGRESS_INTERVAL == 0:
                logger.info(
                    "  進捗 %s: read=%d bbox_pass=%d written=%d",
                    tile_path.name,
                    read_count,
                    bbox_pass,
                    written,
                )

            geometry = feature.get("geometry")
            if not geometry:
                continue

            try:
                geom_3857 = shape(geometry)
            except Exception:
                continue
            if geom_3857.is_empty:
                continue

            fb = geom_3857.bounds
            if bboxes_disjoint(fb, mask_bounds_mercator):
                continue
            bbox_pass += 1

            if not prepared.intersects(geom_3857):
                continue

            geom_4326 = shapely_transform(TO_WGS84, geom_3857)

            props = dict(feature.get("properties") or {})
            # タイル元の source プロパティを上書きし、系統を明示する
            props["gba_tile_source"] = props.get("source")
            props["source"] = source
            fid = feature.get("id")
            if fid is None:
                fid = props.get("id")
            if fid is not None:
                dedupe_key = f"{source}:{fid}"
                if dedupe_key in seen_ids:
                    continue
                seen_ids.add(dedupe_key)
                props.setdefault("gba_id", fid)

            out_feature = {
                "type": "Feature",
                "geometry": mapping(geom_4326),
                "properties": props,
            }
            if not first_feature[0]:
                out_fh.write(",\n")
            else:
                first_feature[0] = False
            json.dump(out_feature, out_fh, ensure_ascii=False)
            written += 1

    logger.info(
        "完了 %s: read=%d bbox_pass=%d written=%d",
        tile_path.name,
        read_count,
        bbox_pass,
        written,
    )
    return read_count, bbox_pass, written


def run(skip_download: bool = False) -> None:
    ensure_dirs()

    adm0_path = DATA_DIR / "geoBoundaries-PHL-ADM0.geojson"
    download_geoboundaries(adm0_path)
    mask_wgs = extract_mindanao_island(adm0_path, MASK_PATH)
    mask_bounds_wgs = mask_wgs.bounds  # タイル選択用（度）

    # クリップ判定はタイルと同じ EPSG:3857 で行う
    mask_mercator = shapely_transform(TO_MERCATOR, mask_wgs)
    mask_bounds_mercator = mask_mercator.bounds
    logger.info("マスク EPSG:3857 bounds: %s", mask_bounds_mercator)

    tiles = select_tiles(mask_bounds_wgs)
    local_tiles: List[Tuple[Path, str]] = []

    for tile in tiles:
        dest = RAW_DIR / tile["subdir"] / tile["name"]
        if skip_download:
            if not dest.exists():
                raise FileNotFoundError(
                    f"--skip-download 指定ですがタイルがありません: {dest}"
                )
            local_tiles.append((dest, tile["source"]))
        else:
            path = download_tile(tile)
            local_tiles.append((path, tile["source"]))

    seen_ids: Set[str] = set()
    first_feature = [True]
    total_read = total_bbox = total_written = 0

    logger.info("出力開始: %s", OUTPUT_PATH)
    with OUTPUT_PATH.open("w", encoding="utf-8") as out_fh:
        out_fh.write(
            '{"type":"FeatureCollection","crs":{"type":"name","properties":'
            '{"name":"urn:ogc:def:crs:OGC:1.3:CRS84"}},"features":[\n'
        )
        for path, source in local_tiles:
            r, b, w = stream_clip_tile(
                path,
                source,
                mask_mercator,
                mask_bounds_mercator,
                out_fh,
                seen_ids,
                first_feature,
            )
            total_read += r
            total_bbox += b
            total_written += w
        out_fh.write("\n]}\n")

    logger.info("=" * 60)
    logger.info("合計 read=%d / bbox_pass=%d / written=%d", total_read, total_bbox, total_written)
    logger.info("出力: %s (%.1f MB)", OUTPUT_PATH, OUTPUT_PATH.stat().st_size / 1e6)
    logger.info("マスク WGS84 bounds: %s", mask_bounds_wgs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GlobalBuildingAtlas からミンダナオ本島の建物ポリゴンを抽出"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="既存の data/raw タイルのみ使う（再ダウンロードしない）",
    )
    args = parser.parse_args()
    try:
        run(skip_download=args.skip_download)
    except Exception as exc:
        logger.error("エラー: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
