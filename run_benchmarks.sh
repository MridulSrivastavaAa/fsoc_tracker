#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "====================================================================="
echo "   ISRO / SAC PS 26169 - FSOC VIRTUAL CAMERA TRACKING SYSTEM"
echo "   Running Automated Benchmark Evaluations..."
echo "====================================================================="
echo ""
python main.py benchmark --type all --duration 2.0 "$@"
