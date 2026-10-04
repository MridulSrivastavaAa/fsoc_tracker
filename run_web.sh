#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR/web"
echo "====================================================================="
echo "   NETRA - AI-BASED VIRTUAL CAMERA TRACKING SYSTEM (PS 26169)"
echo "   Launching Interactive 3D Web Visualizer & Orbit Tracker..."
echo "====================================================================="
echo "Local URL: http://localhost:5173"
echo ""
pnpm dev --open
