#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "[!] Virtual environment .venv not found. Running with system python3..."
fi

echo "====================================================================="
echo "   ISRO / SAC PS 26169 - FSOC VIRTUAL CAMERA TRACKING SYSTEM"
echo "   Launching Operator Workstation..."
echo "====================================================================="
echo ""
python main.py gui "$@"
