#!/bin/sh
# usage: sh tools/run_country.sh <ISO3> <planet url>   cut one country, commit and push it, delete the local copy
set -e
ISO="$1"; PLANET="$2"; LOW=$(echo "$ISO" | tr 'A-Z' 'a-z')
export PATH=/tmp/maptest:$PATH
cd "$(dirname "$0")/.."
OUT=/tmp/maptest/$LOW; rm -rf "$OUT"
python3 tools/cut_country.py "$ISO" "$PLANET" "$OUT"
mkdir -p tiles/$LOW && mv "$OUT"/*.pmtiles "$OUT"/$LOW.json tiles/$LOW/
git add tiles/$LOW && git commit -q -m "tiles: $ISO" && git push -q
rm -rf tiles/$LOW "$OUT"
echo "DONE $ISO"
