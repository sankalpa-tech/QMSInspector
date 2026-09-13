#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8000}"
INSTALL_DEPS=0
PYTHON_BIN="${PYTHON_BIN:-python}"

usage() {
  cat <<'EOF'
Usage: ./start.sh [--install]

Deletes previous inspection job output and starts the offline server.

Options:
  --install   Install requirements.txt before starting

Environment:
  PORT        Server port (default: 8000)
  PYTHON_BIN  Python executable to use (default: python)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install)
      INSTALL_DEPS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "Python executable not found. Set PYTHON_BIN or install Python." >&2
    exit 1
  fi
fi

if [ "$INSTALL_DEPS" -eq 1 ]; then
  "$PYTHON_BIN" -m pip install -r requirements.txt
fi

mkdir -p inspection_jobs
find inspection_jobs -mindepth 1 -maxdepth 1 -exec rm -rf {} +

exec "$PYTHON_BIN" qms.py serve --port "$PORT"
