#!/usr/bin/env bash
# =============================================================================
# build_dmg.sh
# ============
# Standalone macOS application bundle (.app) and DMG packager for NETRA.
#
# Usage:
#   ./build_dmg.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "====================================================================="
echo " NETRA FSOC PAT Workstation - Standalone macOS Release Builder"
echo "====================================================================="
echo

# 0. Locate Python & PyInstaller environment
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
    PYINSTALLER="${VIRTUAL_ENV}/bin/pyinstaller"
elif [ -x "../.venv/bin/python" ]; then
    PYTHON="$(cd .. && pwd)/.venv/bin/python"
    PYINSTALLER="$(cd .. && pwd)/.venv/bin/pyinstaller"
elif [ -x ".venv/bin/python" ]; then
    PYTHON="${SCRIPT_DIR}/.venv/bin/python"
    PYINSTALLER="${SCRIPT_DIR}/.venv/bin/pyinstaller"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
    PYINSTALLER="pyinstaller"
else
    PYTHON="python"
    PYINSTALLER="pyinstaller"
fi

echo "Using Python:      $PYTHON ($("$PYTHON" --version 2>&1))"
echo "Using PyInstaller: $("$PYINSTALLER" --version 2>&1 || echo 'unknown')"
echo

# Step 1: Branding artwork & .icns generation
echo "[1/5] Generating branding assets & macOS .icns..."
"$PYTHON" make_icon.py

if [ ! -f "assets/netra.icns" ]; then
    echo "ERROR: assets/netra.icns was not generated." >&2
    exit 1
fi

# Step 2: PyInstaller Onedir + BUNDLE (.app) build
echo
echo "[2/5] Freezing standalone application bundle with PyInstaller..."
"$PYINSTALLER" NETRA.spec --noconfirm --clean

APP_PATH="dist/NETRA.app"
BINARY_PATH="${APP_PATH}/Contents/MacOS/NETRA"

if [ ! -d "$APP_PATH" ] || [ ! -x "$BINARY_PATH" ]; then
    echo "ERROR: ${APP_PATH} was not created or main binary is missing." >&2
    exit 1
fi
echo "Application bundle created at: $APP_PATH"

# Step 3: Headless smoke test verification (--selftest)
echo
echo "[3/5] Verifying frozen application bundle via --selftest..."
"$BINARY_PATH" --selftest

SELFTEST_EXIT=$?
if [ $SELFTEST_EXIT -ne 0 ]; then
    echo "ERROR: Selftest failed with exit code $SELFTEST_EXIT" >&2
    exit $SELFTEST_EXIT
fi
echo "Selftest passed successfully."

# Step 4: Package into release/NETRA-macOS.dmg
echo
echo "[4/5] Packaging disk image (release/NETRA-macOS.dmg)..."
mkdir -p release
DMG_PATH="release/NETRA-macOS.dmg"
rm -f "$DMG_PATH"

DMG_CREATED=0

if command -v create-dmg >/dev/null 2>&1; then
    echo "Building DMG using create-dmg..."
    STAGING_DIR="$(mktemp -d /tmp/netra_dmg_staging.XXXXXX)"
    cp -R "$APP_PATH" "$STAGING_DIR/"

    set +e
    create-dmg \
        --volname "NETRA" \
        --volicon "assets/netra.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "NETRA.app" 175 140 \
        --hide-extension "NETRA.app" \
        --app-drop-link 425 140 \
        "$DMG_PATH" \
        "$STAGING_DIR"
    CREATE_DMG_STATUS=$?
    set -e

    rm -rf "$STAGING_DIR"

    if [ $CREATE_DMG_STATUS -eq 0 ] && [ -f "$DMG_PATH" ]; then
        DMG_CREATED=1
    else
        echo "create-dmg exited with code $CREATE_DMG_STATUS (common in headless CI without Finder GUI). Falling back to native hdiutil..."
        rm -f "$DMG_PATH"
    fi
fi

if [ $DMG_CREATED -eq 0 ]; then
    echo "Packaging DMG using native macOS hdiutil with Applications drop link..."
    STAGING_DIR="$(mktemp -d /tmp/netra_dmg_staging.XXXXXX)"
    cp -R "$APP_PATH" "$STAGING_DIR/"
    ln -s /Applications "$STAGING_DIR/Applications"
    
    # Copy volume icon if available
    if [ -f "assets/netra.icns" ]; then
        cp "assets/netra.icns" "$STAGING_DIR/.VolumeIcon.icns"
    fi

    hdiutil create \
        -volname "NETRA" \
        -srcfolder "$STAGING_DIR" \
        -ov \
        -format UDZO \
        "$DMG_PATH"

    rm -rf "$STAGING_DIR"
fi

if [ ! -f "$DMG_PATH" ]; then
    echo "ERROR: Failed to create $DMG_PATH" >&2
    exit 1
fi

DMG_SIZE=$(du -h "$DMG_PATH" | cut -f1)
echo "DMG successfully created: $DMG_PATH ($DMG_SIZE)"

# Step 5: Checksum calculation
echo
echo "[5/5] Generating SHA-256 release checksum..."
CHECKSUM_FILE="release/checksums-macos.txt"
shasum -a 256 "$DMG_PATH" | awk '{print $1 "  " "'$(basename "$DMG_PATH")'"}' > "$CHECKSUM_FILE"

echo "Checksum recorded in $CHECKSUM_FILE:"
cat "$CHECKSUM_FILE"

echo
echo "====================================================================="
echo " BUILD SUCCESSFUL!"
echo " Output: $DMG_PATH ($DMG_SIZE)"
echo " Checksum: $(cat "$CHECKSUM_FILE")"
echo "====================================================================="
