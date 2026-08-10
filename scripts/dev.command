#!/usr/bin/env bash
# macOS Finder/Terminal launcher for LibraryForge development.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/dev.sh"
