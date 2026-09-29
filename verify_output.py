#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verify mindanao_buildings.geojson without loading the whole file."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
import ijson
from shapely.geometry import box, shape
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "mindanao_buildings.geojson"
MASK = ROOT / "data" / "mindanao_island.geojson"

mask = gpd.read_file(MASK).geometry.iloc[0]
prepared = prep(mask)
mask_bounds = mask.bounds  # minx,miny,maxx,maxy
# slightly padded envelope for "clearly outside" check
pad = 0.05
outside_box = box(
    mask_bounds[0] - pad,
    mask_bounds[1] - pad,
    mask_bounds[2] + pad,
    mask_bounds[3] + pad,
)

count = 0
sources = Counter()
outside_mask = 0
outside_bbox = 0
minx = miny = float("inf")
maxx = maxy = float("-inf")
samples_outside = []

print("mask bounds", mask_bounds)
print("file size MB", OUTPUT.stat().st_size / 1e6)

with OUTPUT.open("rb") as fh:
    for feat in ijson.items(fh, "features.item", use_float=True):
        count += 1
        props = feat.get("properties") or {}
        sources[props.get("source", "?")] += 1
        geom = shape(feat["geometry"])
        b = geom.bounds
        minx = min(minx, b[0])
        miny = min(miny, b[1])
        maxx = max(maxx, b[2])
        maxy = max(maxy, b[3])

        if not outside_box.intersects(geom):
            outside_bbox += 1
            if len(samples_outside) < 5:
                samples_outside.append(("bbox", b, props.get("id")))
        elif not prepared.intersects(geom):
            outside_mask += 1
            if len(samples_outside) < 5:
                samples_outside.append(("mask", b, props.get("id")))

        if count % 500_000 == 0:
            print(f"progress {count:,} outside_mask={outside_mask} outside_bbox={outside_bbox}")

print("=" * 60)
print(f"features: {count:,}")
print(f"sources: {dict(sources)}")
print(f"data bounds: ({minx:.6f}, {miny:.6f}, {maxx:.6f}, {maxy:.6f})")
print(f"outside padded bbox: {outside_bbox}")
print(f"inside bbox but outside island polygon: {outside_mask}")
print("sample outliers:", samples_outside)

# Write a tiny summary JSON
summary = {
    "feature_count": count,
    "sources": dict(sources),
    "data_bounds": [minx, miny, maxx, maxy],
    "mask_bounds": list(mask_bounds),
    "outside_padded_bbox": outside_bbox,
    "outside_island_polygon": outside_mask,
    "file_size_mb": round(OUTPUT.stat().st_size / 1e6, 1),
}
(ROOT / "output" / "verification_summary.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print("wrote output/verification_summary.json")
