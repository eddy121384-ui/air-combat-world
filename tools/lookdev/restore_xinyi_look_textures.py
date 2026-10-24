"""Restore missing derived PNGs in the isolated material-test worktree only.

Existing GLBs, terrain, tree/roof instances and source receipts stay byte-identical.
Does not call build_all, city generation, terrain generation, or GLB writers.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

REPO = Path(__file__).resolve().parents[2]
if REPO.name != 'xinyi-material-ue58-round1':
    raise RuntimeError('Recovery is restricted to the isolated test worktree')
LOOK = REPO / 'unreal/Saved/XinyiLook'
OUT = REPO / 'investigation'
sys.path.insert(0, str(Path(__file__).resolve().parent))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lamp_texture(np, Image, extent):
    e0, e1, _n0, n1 = extent
    lamps = json.loads((LOOK / 'ground/xinyi_lamps.json').read_text())['instances']
    res, radius = 1024, 26.0
    px = (e1 - e0) / res
    light = np.zeros((res, res), np.float64)
    kr = int(math.ceil(radius / px))
    ky, kx = np.mgrid[-kr:kr + 1, -kr:kr + 1]
    kd = np.hypot(kx, ky) * px
    for lm in lamps:
        yaw = math.radians(lm['yaw'])
        cx, cy = lm['e'] + math.cos(yaw) * 2.0, lm['n'] + math.sin(yaw) * 2.0
        ix, iy = int((cx - e0) / px), int((n1 - cy) / px)
        kernel = lm['s'] / (1.0 + (kd / (5.0 * lm['s'])) ** 2) ** 1.5 * (kd < radius)
        y0, y1 = max(0, iy - kr), min(res, iy + kr + 1)
        x0, x1 = max(0, ix - kr), min(res, ix + kr + 1)
        if y0 < y1 and x0 < x1:
            light[y0:y1, x0:x1] += kernel[y0 - (iy - kr):y1 - (iy - kr), x0 - (ix - kr):x1 - (ix - kr)]
    light = np.sqrt(1.0 - np.exp(-light * 0.9))
    Image.fromarray((light * 255 + 0.5).astype(np.uint8), 'L').save(
        LOOK / 'ground/xinyi_ground_light_1024.png', optimize=True)


def main():
    report = {'status': 'FAIL_TEXTURE_RECOVERY', 'geometry_generation': False,
              'clouds': 'off; cloud assets not rebuilt', 'textures': []}
    metadata = {}
    try:
        import numpy as np
        from PIL import Image
        import build_ground as ground
        import build_far_city as far
        import build_sign_atlas as signs
        import build_shop_atlas as shops
        import build_storefronts as storefronts
        import build_wall_ad_atlas as ads

        ledger = json.loads((OUT / 'staged-inputs.json').read_text(encoding='utf-8-sig'))
        # These builders also emit metadata. Preserve every staged non-PNG byte.
        metadata = {REPO / row['relative_path']: (REPO / row['relative_path']).read_bytes()
                    for row in ledger if row['relative_path'].endswith(('.json', '.gz'))}
        expected = {}
        for relative in ('street/sign_atlas.json', 'street/shop_atlas.json', 'wall_ads/wall_ad_atlas.json'):
            doc = json.loads((LOOK / relative).read_text(encoding='utf-8'))
            expected[relative.replace('.json', '.png')] = doc['sha256']
        expected['street/storefront_plan_2048.png'] = json.loads(
            (LOOK / 'street/storefronts.report.json').read_text())['plan_sha256']

        # Restore the locked projected source only for read-only footprint queries.
        raw = gzip.decompress((REPO / 'data/lookdev_cache/sample_buildings_epsg3826.geojson.gz').read_bytes())
        if hashlib.sha256(raw).hexdigest() != 'c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d':
            raise RuntimeError('Projected source hash mismatch')
        ground.SOURCE.parent.mkdir(parents=True, exist_ok=True)
        if ground.SOURCE.exists() and ground.SOURCE.read_bytes() != raw:
            raise RuntimeError('Refusing to overwrite a different projected source')
        ground.SOURCE.write_bytes(raw)

        # Road raster returns before any building/tree/terrain processing.
        ground.main(texture_only=True)
        extent = (ground.E0, ground.E1, ground.N0, ground.N1)
        lamp_texture(np, Image, extent)

        # Recompute the class raster only; no curb paint or tree generation.
        ways, *_ = ground.load_osm()
        for way in ways:
            way.update(ground.way_geometry(way))
        ways = [w for w in ways if not w['skip']]
        roles = json.loads(gzip.decompress((LOOK / 'urban_identity/frontage_roles.json.gz').read_bytes()))
        with gzip.open(LOOK / 'look_buildings.jsonl.gz', 'rt', encoding='utf-8') as fh:
            look = {r['building_id']: r for r in map(json.loads, fh)}
        lon0, lat0 = ground.enu_origin_from_city_yaml(ground.CITY)
        osm = json.loads(gzip.decompress(ground.OSM.read_bytes()))
        enu = lambda g: [ground.lonlat_to_enu(p['lon'], p['lat'], lon0, lat0) for p in g]
        sidewalks, _ = ground.curb_zone.load_osm_lines(osm, enu)
        contribs = ground.curb_zone.frontage_contribs(roles, look, {w['id']: w for w in ways})
        marks = {k: [(c['s0'] - 1.0, c['s1'] + 1.0) for c in v if c['arcade']] for k, v in contribs.items()}
        runs, _ = ground.curb_zone.side_classes(ways, sidewalks, marks)
        alpha = ground.curb_zone.rasterise_classes(ways, runs, extent, ground.RES)
        # Source footprints are read for campus masks. No extrusion/triangulation.
        wm = ground.build_worldmodel(ground.SOURCE, ground.CITY, source_crs='EPSG:3826')
        polygons = [ground.Polygon(p['footprint_enu']) for b in wm['buildings'] for p in b['polygons']]
        polygons = [p for p in polygons if p.is_valid and p.area > 1]
        ground.build_campus_layer(None, polygons, alpha, texture_only=True)
        far.main(texture_only=True)
        for builder in (signs, shops, storefronts, ads):
            builder.main()
        for path in sorted(LOOK.rglob('*.png')):
            relative = path.relative_to(LOOK).as_posix()
            actual = sha(path)
            with Image.open(path) as im:
                report['textures'].append({'path': relative, 'sha256': actual,
                    'size': list(im.size), 'mode': im.mode, 'historical_sha256': expected.get(relative),
                    'historical_hash_matches': actual == expected[relative] if relative in expected else None})
        if len(report['textures']) != 8:
            raise RuntimeError('Expected exactly 8 recovered PNGs')
        report['status'] = 'PASS_TEXTURE_RECOVERY'
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        for path, data in metadata.items():
            if path.read_bytes() != data:
                path.write_bytes(data)
        ledger = json.loads((OUT / 'staged-inputs.json').read_text(encoding='utf-8-sig'))
        changed = [r['relative_path'] for r in ledger if sha(REPO / r['relative_path']) != r['source_sha256']]
        report['changed_staged_inputs'] = changed
        if changed:
            report['status'] = 'FAIL_TEXTURE_RECOVERY'
        (OUT / 'texture-recovery.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(report['status'], len(report['textures']), 'textures; staged inputs changed:', len(changed), flush=True)
    if report['status'] != 'PASS_TEXTURE_RECOVERY':
        raise RuntimeError(report.get('error', 'Texture recovery failed'))


if __name__ == '__main__':
    main()
