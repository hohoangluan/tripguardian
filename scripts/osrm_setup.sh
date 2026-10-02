#!/usr/bin/env bash
# One-time OSRM setup for Planning's travel matrices (docs/specs/PLANNING_SPEC.md, Live Context).
# Needs docker. Data lands in ./osrm-data, which .gitignore excludes.
set -euo pipefail

DIR="${1:-osrm-data}"
PBF_URL="https://download.geofabrik.de/asia/vietnam-latest.osm.pbf"
IMAGE="ghcr.io/project-osrm/osrm-backend:latest"

mkdir -p "$DIR"
cd "$DIR"

if [ ! -f vietnam-latest.osm.pbf ]; then
  echo "downloading $PBF_URL"
  curl -L -o vietnam-latest.osm.pbf "$PBF_URL"
fi

if [ ! -f vietnam-latest.osrm.mldgr ]; then
  docker run --rm -t -v "$PWD:/data" "$IMAGE" \
    osrm-extract -p /opt/car.lua /data/vietnam-latest.osm.pbf
  docker run --rm -t -v "$PWD:/data" "$IMAGE" \
    osrm-partition /data/vietnam-latest.osrm
  docker run --rm -t -v "$PWD:/data" "$IMAGE" \
    osrm-customize /data/vietnam-latest.osrm
fi

echo "starting osrm-routed on 127.0.0.1:5000 (ctrl-c to stop)"
docker run --rm -t -p 127.0.0.1:5000:5000 -v "$PWD:/data" "$IMAGE" \
  osrm-routed --algorithm mld --max-table-size 300 /data/vietnam-latest.osrm
