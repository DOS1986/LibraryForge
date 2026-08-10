#!/usr/bin/env bash
# LibraryForge development supervisor for Linux and macOS.
# Bash 3.2+ compatible (including the Bash version shipped with macOS).

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_ROOT="$REPO_ROOT/backend"
FRONTEND_ROOT="$REPO_ROOT/frontend"
RUNTIME_ROOT="$REPO_ROOT/runtime"
RESTART_FILE="$RUNTIME_ROOT/restart.request"

BACKEND_PID=""
FRONTEND_PID=""
WORKER_PID=""
SHUTTING_DOWN=0

mkdir -p "$RUNTIME_ROOT"
rm -f "$RESTART_FILE"

export LIBRARYFORGE_RESTART_ENABLED="true"
export LIBRARYFORGE_RESTART_FILE="$RESTART_FILE"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "[LibraryForge] Required command not found: $1" >&2
        exit 1
    fi
}

require_command uv
require_command npm
require_command pgrep

start_backend() {
    echo "[LibraryForge] Starting Django..."
    (
        cd "$BACKEND_ROOT" || exit 1
        exec uv run python manage.py runserver 127.0.0.1:8000
    ) &
    BACKEND_PID=$!
}

start_worker() {
    echo "[LibraryForge] Starting scan worker..."
    (
        cd "$BACKEND_ROOT" || exit 1
        exec uv run python manage.py run_scan_worker
    ) &
    WORKER_PID=$!
}

start_frontend() {
    echo "[LibraryForge] Starting Vite..."
    (
        cd "$FRONTEND_ROOT" || exit 1
        exec npm run dev
    ) &
    FRONTEND_PID=$!
}

child_pids() {
    pgrep -P "$1" 2>/dev/null || true
}

stop_process_tree() {
    pid="$1"
    name="$2"

    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        return
    fi

    echo "[LibraryForge] Stopping $name..."

    for child in $(child_pids "$pid"); do
        stop_process_tree "$child" "$name child"
    done

    kill -TERM "$pid" 2>/dev/null || true

    attempts=0
    while kill -0 "$pid" 2>/dev/null && [ "$attempts" -lt 20 ]; do
        sleep 0.1
        attempts=$((attempts + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
    fi

    wait "$pid" 2>/dev/null || true
}

wait_for_worker_restart_exit() {
    if [ -z "$WORKER_PID" ] || ! kill -0 "$WORKER_PID" 2>/dev/null; then
        return
    fi

    echo "[LibraryForge] Waiting for the scan worker to finish its current scan..."
    while kill -0 "$WORKER_PID" 2>/dev/null; do
        sleep 0.25
    done
    wait "$WORKER_PID" 2>/dev/null || true
}

restart_libraryforge() {
    # Keep restart.request present so the worker sees it. If a scan is active,
    # the worker finishes that scan and exits at the next safe loop boundary.
    wait_for_worker_restart_exit

    stop_process_tree "$FRONTEND_PID" "Vite"
    stop_process_tree "$BACKEND_PID" "Django"

    BACKEND_PID=""
    FRONTEND_PID=""
    WORKER_PID=""

    rm -f "$RESTART_FILE"
    sleep 0.75

    start_backend
    start_worker
    start_frontend
}

cleanup() {
    if [ "$SHUTTING_DOWN" -eq 1 ]; then
        return
    fi

    SHUTTING_DOWN=1
    echo
    echo "[LibraryForge] Shutting down development supervisor..."

    stop_process_tree "$FRONTEND_PID" "Vite"
    stop_process_tree "$BACKEND_PID" "Django"
    stop_process_tree "$WORKER_PID" "Scan worker"
    rm -f "$RESTART_FILE"
}

trap cleanup EXIT INT TERM HUP

start_backend
start_worker
start_frontend

echo
echo "LibraryForge development supervisor is running."
echo "Backend:     http://127.0.0.1:8000"
echo "Frontend:    http://127.0.0.1:5173"
echo "Scan worker: supervised"
echo "Restart requests: $RESTART_FILE"
echo "Press Ctrl+C here to stop the development stack."
echo

while [ "$SHUTTING_DOWN" -eq 0 ]; do
    if [ -f "$RESTART_FILE" ]; then
        echo "[LibraryForge] Restart requested from the web UI."
        restart_libraryforge
        continue
    fi

    if [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        wait "$BACKEND_PID" 2>/dev/null || true
        echo "[LibraryForge] Django exited; starting it again."
        start_backend
    fi

    if [ -n "$FRONTEND_PID" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        wait "$FRONTEND_PID" 2>/dev/null || true
        echo "[LibraryForge] Vite exited; starting it again."
        start_frontend
    fi

    if [ -n "$WORKER_PID" ] && ! kill -0 "$WORKER_PID" 2>/dev/null; then
        wait "$WORKER_PID" 2>/dev/null || true
        echo "[LibraryForge] Scan worker exited; starting it again."
        start_worker
    fi

    sleep 0.5
done
