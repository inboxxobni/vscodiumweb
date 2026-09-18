#!/usr/bin/env bash
#
# start_server.sh — Start the VSCodium Web Server
#
# Usage:
#   ./scripts/start_server.sh                    # Start with defaults
#   ./scripts/start_server.sh --port 8080        # Custom port
#   ./scripts/start_server.sh --token mytoken    # With security token
#   ./scripts/start_server.sh --daemon           # Start as background daemon
#
# Environment variables:
#   PORT              Server port (default: 8000)
#   HOST              Bind address (default: 0.0.0.0)
#   CONNECTION_TOKEN  Security token for access
#   SERVER_DIR        Path to built server (auto-detected)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Defaults ────────────────────────────────────────────────────────────────
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
TOKEN="${CONNECTION_TOKEN:-}"
DAEMON_MODE=false
ARGS=()

# ── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)           PORT="$2"; shift 2 ;;
    --host)           HOST="$2"; shift 2 ;;
    --token)          TOKEN="$2"; shift 2 ;;
    --daemon|-d)      DAEMON_MODE=true; shift ;;
    --help|-h)
      echo "VSCodium Web — Start Server"
      echo ""
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --port PORT         Server port (default: 8000)"
      echo "  --host HOST         Bind address (default: 0.0.0.0)"
      echo "  --token TOKEN       Connection token for security"
      echo "  --daemon, -d        Start as background daemon"
      echo "  --help, -h          Show this help"
      echo ""
      echo "Environment variables:"
      echo "  PORT                Server port"
      echo "  HOST                Bind address"
      echo "  CONNECTION_TOKEN    Connection token"
      echo "  SERVER_DIR          Path to built server"
      echo ""
      echo "Examples:"
      echo "  $0                  # Start in foreground"
      echo "  $0 -d               # Start as daemon"
      echo "  $0 --port 8080 --token mysecret"
      exit 0
      ;;
    *)                  ARGS+=("$1"); shift ;;
  esac
done

# ── Find the server directory ───────────────────────────────────────────────
SERVER_DIR="${SERVER_DIR:-}"
if [[ -z "${SERVER_DIR}" ]]; then
  for candidate in \
    "${PROJECT_DIR}/web-build/server" \
    "${PROJECT_DIR}/vscode-reh-web-"* ; do
    if [[ -d "${candidate}" ]]; then
      SERVER_DIR="${candidate}"
      break
    fi
  done
fi

if [[ -z "${SERVER_DIR}" ]]; then
  echo "Error: No built server found."
  echo ""
  echo "Build the web version first:"
  echo "  ./build_web.sh"
  echo ""
  echo "Or set SERVER_DIR to the path of your built server."
  exit 1
fi

# ── Find the server binary ──────────────────────────────────────────────────
SERVER_APP_NAME="codium-server"
if [[ -f "${SERVER_DIR}/product.json" ]]; then
  SERVER_APP_NAME=$(node -p "require('${SERVER_DIR}/product.json').serverApplicationName || 'codium-server'" 2>/dev/null || echo "codium-server")
fi

if [[ -f "${SERVER_DIR}/bin/${SERVER_APP_NAME}" ]]; then
  SERVER_BIN="${SERVER_DIR}/bin/${SERVER_APP_NAME}"
elif ls "${SERVER_DIR}/bin/codium-server"* 1>/dev/null 2>&1; then
  SERVER_BIN=$(ls "${SERVER_DIR}/bin/codium-server"* | head -1)
elif [[ -f "${SERVER_DIR}/out/server-web/server-main.js" ]]; then
  SERVER_BIN="node ${SERVER_DIR}/out/server-web/server-main.js"
else
  echo "Error: Could not find server binary in ${SERVER_DIR}"
  ls -la "${SERVER_DIR}/bin/" 2>/dev/null || echo "  (no bin/ directory)"
  exit 1
fi

# ── Build the command ───────────────────────────────────────────────────────
BUILD_ARGS=(
  --port "${PORT}"
  --host "${HOST}"
)
if [[ -n "${TOKEN}" ]]; then
  BUILD_ARGS+=(--connection-token "${TOKEN}")
else
  BUILD_ARGS+=(--without-connection-token)
fi
BUILD_ARGS+=("${ARGS[@]}")

echo "══════════════════════════════════════════════"
echo "  VSCodium Web Server"
echo "══════════════════════════════════════════════"
echo "  Server:  ${SERVER_DIR}"
echo "  Binary:  ${SERVER_BIN}"
echo "  Host:    ${HOST}"
echo "  Port:    ${PORT}"
if [[ -n "${TOKEN}" ]]; then
  echo "  Token:   ${TOKEN}"
  echo "  URL:     http://${HOST}:${PORT}/?tkn=${TOKEN}"
else
  echo "  Token:   (none)"
  echo "  URL:     http://${HOST}:${PORT}/"
fi
echo "  Mode:    $([[ "${DAEMON_MODE}" == "true" ]] && echo "daemon" || echo "foreground")"
echo "══════════════════════════════════════════════"
echo ""

cd "${SERVER_DIR}"

# ── Start the server ────────────────────────────────────────────────────────
if [[ "${DAEMON_MODE}" == "true" ]]; then
  PID_FILE="/tmp/vscodium-web.pid"
  LOG_FILE="${PROJECT_DIR}/vscodium-web.log"

  # Check if already running
  if [[ -f "${PID_FILE}" ]]; then
    EXISTING_PID=$(cat "${PID_FILE}")
    if kill -0 "${EXISTING_PID}" 2>/dev/null; then
      echo "Server is already running (PID: ${EXISTING_PID})"
      echo "Stop it first: ./scripts/stop_server.sh"
      exit 1
    fi
    rm -f "${PID_FILE}"
  fi

  echo "Starting daemon... (log: ${LOG_FILE})"
  nohup "${SERVER_BIN}" "${BUILD_ARGS[@]}" > "${LOG_FILE}" 2>&1 &
  PID=$!
  echo "${PID}" > "${PID_FILE}"

  # Wait briefly and check
  sleep 2
  if kill -0 "${PID}" 2>/dev/null; then
    echo "Server started successfully (PID: ${PID})"
    echo "Log: ${LOG_FILE}"
    echo "URL: http://${HOST}:${PORT}/"
  else
    echo "Server failed to start. Check log:"
    tail -20 "${LOG_FILE}"
    rm -f "${PID_FILE}"
    exit 1
  fi
else
  echo "Starting server in foreground... (Ctrl+C to stop)"
  echo ""
  exec "${SERVER_BIN}" "${BUILD_ARGS[@]}"
fi
