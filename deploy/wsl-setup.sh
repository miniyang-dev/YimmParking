#!/usr/bin/env bash
# Run YimmParking inside WSL so the (WSL-hosted) cloudflared tunnel can reach it on localhost:5173.
set -euo pipefail

SRC=/mnt/d/Projects/YimmParking
BASE="$HOME/yimmparking"
VENV="$BASE/venv"
DATA="$BASE/data"
PORT=5173

mkdir -p "$BASE" "$DATA" "$HOME/.config/systemd/user"

echo "== 1. python venv (no system packages touched)"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv --without-pip "$VENV"
fi
if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$BASE/get-pip.py"
  "$VENV/bin/python" "$BASE/get-pip.py" --quiet
fi
"$VENV/bin/python" -m pip install --quiet "fastapi>=0.110" "uvicorn>=0.29" "httpx>=0.27" "pydantic>=2.6"
"$VENV/bin/python" - <<'PY'
import fastapi, httpx, pydantic, uvicorn, sys
print("python", sys.version.split()[0], "| fastapi", fastapi.__version__, "| pydantic", pydantic.__version__)
PY

echo "== 2. database (copied once from the Windows side so caches and quota counters carry over)"
if [ ! -f "$DATA/yimmparking.db" ]; then
  cp "$SRC/backend/data/yimmparking.db" "$DATA/yimmparking.db"
  echo "copied"
else
  echo "already present, left untouched"
fi

echo "== 3. systemd user units"
cat > "$HOME/.config/systemd/user/yimmparking-api.service" <<UNIT
[Unit]
Description=YimmParking API + web client (served on 127.0.0.1:$PORT for the cloudflared tunnel)
After=network-online.target

[Service]
Environment=PYTHONPATH=$SRC/backend/src
Environment=YIMM_DB_PATH=$DATA/yimmparking.db
Environment=YIMM_WEB_DIST=$SRC/web/dist
ExecStart=$VENV/bin/python -m yimmparking.interface.cli serve --host 127.0.0.1 --port $PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

cat > "$HOME/.config/systemd/user/yimmparking-worker.service" <<UNIT
[Unit]
Description=YimmParking ingestion worker (parking lots and real-time availability)
After=network-online.target

[Service]
Environment=PYTHONPATH=$SRC/backend/src
Environment=YIMM_DB_PATH=$DATA/yimmparking.db
ExecStart=$VENV/bin/python -m yimmparking.interface.cli worker
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now yimmparking-api.service yimmparking-worker.service
sleep 5

echo "== 4. status"
systemctl --user is-active yimmparking-api.service yimmparking-worker.service
echo "-- listening:"; ss -ltn | grep ":$PORT " || echo "NOT LISTENING"
echo "-- health:"; curl -s --max-time 10 "http://127.0.0.1:$PORT/api/v1/health" | head -c 400; echo
echo "-- index:"; curl -s --max-time 10 "http://127.0.0.1:$PORT/" | head -c 160; echo
