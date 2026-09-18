#!/usr/bin/env bash
#
# stop_server.sh — Stop the VSCodium Web Server
#
# Usage:
#   ./scripts/stop_server.sh              # Stop the running server
#   ./scripts/stop_server.sh --force      # Force kill (-9)
#   ./scripts/stop_server.sh --pid FILE   # Use custom PID file
#
# Environment variables:
#   PID_FILE          Path to PID file (default: /tmp/vscodium-web.pid)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Defaults ────────────────────────────────────────────────────────────────
PID_FILE="${PID_FILE:-/tmp/vscodium-web.pid}"
FORCE=false

# ── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force|-f)       FORCE=true; shift ;;
    --pid)            PID_FILE="$2"; shift 2 ;;
    --help|-h)
      echo "VSCodium Web — Stop Server"
      echo ""
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --force, -f       Force kill with SIGKILL (-9)"
      echo "  --pid FILE        Custom PID file path"
      echo "  --help, -h        Show this help"
      echo ""
      echo "Also attempts to find and kill the server by process name."
      exit 0
      ;;
    *)                  echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Stop by PID file ────────────────────────────────────────────────────────
STOPPED=false

if [[ -f "${PID_FILE}" ]]; then
  PID=$(cat "${PID_FILE}")
  if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
    echo "Stopping VSCodium Web Server (PID: ${PID})..."

    if [[ "${FORCE}" == "true" ]]; then
      kill -9 "${PID}" 2>/dev/null || true
    else
      # Graceful shutdown: send SIGTERM, wait, then SIGKILL if needed
      kill "${PID}" 2>/dev/null || true
      for i in $(seq 1 10); do
        if ! kill -0 "${PID}" 2>/dev/null; then
          break
        fi
        sleep 1
      done
      # Force kill if still running after 10 seconds
      if kill -0 "${PID}" 2>/dev/null; then
        echo "Server did not stop gracefully, force killing..."
        kill -9 "${PID}" 2>/dev/null || true
      fi
    fi

    rm -f "${PID_FILE}"
    echo "Server stopped."
    STOPPED=true
  else
    echo "No process found with PID from ${PID_FILE}"
    rm -f "${PID_FILE}"
  fi
fi

# ── Also try to find and kill by process name ───────────────────────────────
# This catches servers started without the daemon script
if [[ "${STOPPED}" == "false" ]]; then
  # Look for codium-server processes
  PIDS=$(pgrep -f "codium-server" 2>/dev/null || true)
  if [[ -n "${PIDS}" ]]; then
    echo "Found running codium-server processes: ${PIDS}"
    for PID in ${PIDS}; do
      echo "  Stopping PID: ${PID}..."
      if [[ "${FORCE}" == "true" ]]; then
        kill -9 "${PID}" 2>/dev/null || true
      else
        kill "${PID}" 2>/dev/null || true
      fi
    done
    STOPPED=true
  fi

  # Also look for server-main.js
  PIDS=$(pgrep -f "server-main.js" 2>/dev/null || true)
  if [[ -n "${PIDS}" ]]; then
    echo "Found running server-main.js processes: ${PIDS}"
    for PID in ${PIDS}; do
      echo "  Stopping PID: ${PID}..."
      kill "${PID}" 2>/dev/null || true
    done
    STOPPED=true
  fi
fi

if [[ "${STOPPED}" == "false" ]]; then
  echo "No running VSCodium Web Server found."
  exit 0
fi

# Clean up log file on force stop
if [[ "${FORCE}" == "true" ]]; then
  rm -f "${PROJECT_DIR}/vscodium-web.log" 2>/dev/null || true
fi
