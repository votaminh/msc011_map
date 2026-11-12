#!/usr/bin/env python3
"""Cut one country out of the Protomaps planet build into PMTiles files of at most MAX_MB each, and write <ISO3>.json (the index of the pieces).

usage: python3 tools/cut_country.py <ISO3> <planet url> <out dir> [--maxzoom 15] [--max-mb 90] [--dry-run]
needs: the `pmtiles` CLI (go-pmtiles) on PATH, python3 with shapely, /tmp/countries.geojson (datasets/geo-countries).
A piece = the country polygon clipped to a box; a box is halved along its longer side until its archive is small enough (sizes come from `pmtiles extract --dry-run`).
"""
import json, re, subprocess, sys, os
from shapely.geometry import shape, box, mapping

iso, planet, out = sys.argv[1], sys.argv[2], sys.argv[3]
opt = lambda n, d: sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
maxzoom, max_mb, dry = int(opt('--maxzoom', 15)), float(opt('--max-mb', 90)), '--dry-run' in sys.argv
countries = json.load(open(opt('--countries', '/tmp/maptest/countries.geojson')))
feat = [f for f in countries['features'] if f['properties'].get('ISO3166-1-Alpha-3') == iso]
if not feat: sys.exit('no country ' + iso)
land = shape(feat[0]['geometry']).buffer(0)
os.makedirs(out, exist_ok=True)

def size_mb(geom):
    p = f'{out}/_region.geojson'
    json.dump(mapping(geom), open(p, 'w'))
    r = subprocess.run(['pmtiles', 'extract', planet, f'{out}/_x.pmtiles', f'--region={p}', f'--maxzoom={maxzoom}', '--dry-run'], capture_output=True, text=True)
    m = re.search(r'archive size of ([\d.]+) (\w+)', r.stderr + r.stdout)
    if not m: sys.exit('dry run failed: ' + r.stderr[-300:])
    return float(m.group(1)) * {'B': 1e-6, 'kB': 1e-3, 'MB': 1, 'GB': 1e3}[m.group(2)]

pieces = []
def split(b, depth=0):
    g = land.intersection(b)
    if g.is_empty or g.area < 1e-6: return
    mb = size_mb(g)
    x0, y0, x1, y1 = b.bounds
    if mb <= max_mb or depth >= 12:
        pieces.append((g, mb, b.bounds)); print(f'  piece {len(pieces)}: {mb:.0f} MB {tuple(round(v, 2) for v in g.bounds)}', flush=True); return
    if (x1 - x0) >= (y1 - y0): m = (x0 + x1) / 2; split(box(x0, y0, m, y1), depth + 1); split(box(m, y0, x1, y1), depth + 1)
    else: m = (y0 + y1) / 2; split(box(x0, y0, x1, m), depth + 1); split(box(x0, m, x1, y1), depth + 1)

split(box(*land.bounds))
print(f'{iso}: {len(pieces)} pieces, about {sum(p[1] for p in pieces):.0f} MB')
if dry: sys.exit(0)
index = []
for i, (g, mb, b) in enumerate(pieces, 1):
    name = f'{iso.lower()}-{i:02d}.pmtiles'
    json.dump(mapping(g), open(f'{out}/_region.geojson', 'w'))
    subprocess.run(['pmtiles', 'extract', planet, f'{out}/{name}', f'--region={out}/_region.geojson', f'--maxzoom={maxzoom}'], check=True, capture_output=True)
    size = os.path.getsize(f'{out}/{name}')
    index.append({'file': name, 'bbox': [round(v, 5) for v in g.bounds], 'bytes': size})
    print('  wrote', name, round(size / 1e6), 'MB', flush=True)
json.dump({'iso': iso, 'maxzoom': maxzoom, 'files': index}, open(f'{out}/{iso.lower()}.json', 'w'), indent=1)
for f in (f'{out}/_region.geojson', f'{out}/_x.pmtiles'):
    if os.path.exists(f): os.remove(f)
