#!/usr/bin/env bash
# Sync the Nexo SDK mirror from the source repo.
#
# Source: ../luzia-nexo/apps/nexo-sdk/
# Target: sdk/nexo-sdk/
#
# This copies the entire SDK package so consumers in this repo can
# import TypeScript sources directly via Vite without needing the
# source repo checked out at runtime.
#
# Run from the luzia-nexo-api repo root:
#   ./scripts/sync-nexo-sdk.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_SDK="${REPO_ROOT}/../luzia-nexo/apps/nexo-sdk"
TARGET_SDK="${REPO_ROOT}/sdk/nexo-sdk"

if [ ! -d "$SOURCE_SDK" ]; then
  echo "Error: Source SDK not found at $SOURCE_SDK"
  echo "Make sure luzia-nexo is checked out as a sibling directory."
  exit 1
fi

echo "Syncing Nexo SDK..."
echo "  Source: $SOURCE_SDK"
echo "  Target: $TARGET_SDK"

# Clean target (keep README)
find "$TARGET_SDK" -mindepth 1 -not -name README.md -delete 2>/dev/null || true

# Copy source files
cp -R "$SOURCE_SDK/src" "$TARGET_SDK/src"
cp "$SOURCE_SDK/package.json" "$TARGET_SDK/package.json"
cp "$SOURCE_SDK/tsconfig.json" "$TARGET_SDK/tsconfig.json"

# Copy vitest config and setup if present (for consumers that want to test)
[ -f "$SOURCE_SDK/vitest.config.ts" ] && cp "$SOURCE_SDK/vitest.config.ts" "$TARGET_SDK/"
[ -f "$SOURCE_SDK/vitest.setup.ts" ] && cp "$SOURCE_SDK/vitest.setup.ts" "$TARGET_SDK/"

echo "Sync complete."
echo "Files synced:"
find "$TARGET_SDK/src" -type f | wc -l | xargs echo "  source files:"
