#!/usr/bin/env bash
#
# status_server.sh — Check VSCodium Web Server Status
#
# Usage:
#   ./scripts/status_server.sh              # Quick status check
#   ./scripts/status_server.sh --verbose    # Detailed status
#   ./scripts/status_server.sh --url        # Just print the URL
#   ./scripts/status_server.sh --watch      # Watch mode (refresh every 2s)
#
# Environment variables:
#   PORT              Server port (default: 8000)
#   HOST              Bind address (default: 0.0.0.0)
#   PID_FILE          Path to PID file (default: /tmp/vscodium-web.pid)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Defaults ────────────────────────────────────────────────────────────────
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
PID_FILE="${PID_FILE:-/tmp/vscodium-web.pid}"
VERBOSE=false
URL_ONLY=false
WATCH_MODE=false

# ── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --verbose|-v)     VERBOSE=true; shift ;;
    --url|-u)         URL_ONLY=true; shift ;;
    --watch|-w)       WATCH_MODE=true; shift ;;
    --help|-h)
      echo "VSCodium Web — Server Status"
      echo ""
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --verbose, -v     Show detailed status"
      echo "  --url, -u         Just print the URL"
      echo "  --watch, -w       Watch mode (refresh every 2s)"
      echo "  --help, -h        Show this help"
      exit 0
      ;;
    *)                  echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Watch mode ──────────────────────────────────────────────────────────────
if [[ "${WATCH_MODE}" == "true" ]]; then
  while true; do
    clear 2>/dev/null || true
    echo "=== VSCodium Web Server Status (refreshing every 2s) ==="
    echo ""
    # Re-run self without --watch to get one snapshot
    bash "$0" --verbose
    echo ""
    echo "Press Ctrl+C to stop."
    sleep 2
  done
  exit 0
fi

# ── Check by PID file ───────────────────────────────────────────────────────
RUNNING=false
PID=""

if [[ -f "${PID_FILE}" ]]; then
  PID=$(cat "${PID_FILE}")
  if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
    RUNNING=true
  fi
fi

# ── Also check by process name ──────────────────────────────────────────────
if [[ "${RUNNING}" != "true" ]]; then
  CANDIDATE_PIDS=$(pgrep -f "codium-server" 2>/dev/null || true)
  if [[ -z "${CANDIDATE_PIDS}" ]]; then
    CANDIDATE_PIDS=$(pgrep -f "server-main.js" 2>/dev/null || true)
  fi
  if [[ -n "${CANDIDATE_PIDS}" ]]; then
    RUNNING=true
    PID=$(echo "${CANDIDATE_PIDS}" | head -1)
  fi
fi

# ── Check HTTP health ───────────────────────────────────────────────────────
HTTP_OK=false
HTTP_STATUS=""

if command -v curl &>/dev/null; then
  HTTP_RESULT=$(curl -s -o /dev/null -w "%{http_code}" "http://${HOST}:${PORT}/" 2>/dev/null || true)
  if [[ -n "${HTTP_RESULT}" ]] && [[ "${HTTP_RESULT}" != "000" ]]; then
    HTTP_OK=true
    HTTP_STATUS="${HTTP_RESULT}"
  fi
fi

# ── URL-only mode ───────────────────────────────────────────────────────────
if [[ "${URL_ONLY}" == "true" ]]; then
  if [[ "${RUNNING}" == "true" ]]; then
    echo "http://${HOST}:${PORT}/"
  else
    echo "Server not running"
    exit 1
  fi
  exit 0
fi

# ── Display status ──────────────────────────────────────────────────────────
if [[ "${RUNNING}" == "true" ]]; then
  echo "● VSCodium Web Server is RUNNING"
  echo ""
  echo "  PID:     ${PID}"

  # Get process info
  if command -v ps &>/dev/null; then
    PS_INFO=$(ps -p "${PID}" -o pid,ppid,%cpu,%mem,rss,etime,comm= 2>/dev/null || true)
    if [[ -n "${PS_INFO}" ]]; then
      echo "  CPU:     $(echo "${PS_INFO}" | awk 'NR>1{print $3}')%"
      echo "  Memory:  $(echo "${PS_INFO}" | awk 'NR>1{print $4}')% ($(echo "${PS_INFO}" | awk 'NR>1{print $5}') RSS)"
      echo "  Uptime:  $(echo "${PS_INFO}" | awk 'NR>1{print $6}')"
    fi
  fi

  echo "  Port:    ${PORT}"
  echo "  URL:     http://${HOST}:${PORT}/"

  if [[ "${HTTP_OK}" == "true" ]]; then
    echo "  Health:  ✓ HTTP ${HTTP_STATUS}"
  else
    echo "  Health:  ✗ Not responding (might still be starting)"
  fi

  echo ""

  if [[ "${VERBOSE}" == "true" ]]; then
    echo "  ── Process Tree ──"
    if command -v pstree &>/dev/null; then
      pstree -p "${PID}" 2>/dev/null || true
    elif command -v ps &>/dev/null; then
      ps -ef 2>/dev/null | grep -E "(codium-server|server-main)" | grep -v grep || true
    fi
    echo ""

    # Show log tail
    LOG_FILE="${PROJECT_DIR}/vscodium-web.log"
    if [[ -f "${LOG_FILE}" ]]; then
      echo "  ── Recent Log (tail -10) ──"
      tail -10 "${LOG_FILE}" 2>/dev/null || echo "    (cannot read log)"
    fi
    echo ""

    # Show PID file
    echo "  ── PID File ──"
    echo "    ${PID_FILE}: $(cat "${PID_FILE}" 2>/dev/null || echo 'not found')"
  fi
else
  echo "○ VSCodium Web Server is STOPPED"
  echo ""
  echo "  Start it:"
  echo "    ./scripts/start_server.sh"
  echo "    ./scripts/start_server_daemon.sh"
  exit 1
fi
