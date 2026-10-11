#!/usr/bin/env bash
# Deploy YimmParking from this checkout (run inside WSL, where the services live):
# build the web client, stamp it with the commit it was built from, then restart the services so
# the new backend code is the one answering. SpriteFlow's deploy button runs exactly this, then
# polls /api/v1/health until `version` and `frontend_version` equal the commit it just synced.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== 1. web client"
cd "$ROOT/web"
pnpm install --frozen-lockfile
pnpm build
# `vite build` empties dist first, so the stamp is written after it.
git -C "$ROOT" rev-parse HEAD > "$ROOT/web/dist/version.txt"
echo "built $(cut -c1-7 "$ROOT/web/dist/version.txt")"

echo "== 2. restart services (backend code is only loaded at start)"
systemctl --user restart yimmparking-api yimmparking-worker
sleep 3
systemctl --user is-active yimmparking-api yimmparking-worker
