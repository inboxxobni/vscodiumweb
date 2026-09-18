#!/usr/bin/env bash
#
# start_server_daemon.sh — Start VSCodium Web as a persistent daemon
#
# Starts the server in the background with:
#   - PID file tracking
#   - Auto-restart on crash (optional)
#   - Log rotation support
#   - Systemd service installation (Linux)
#
# Usage:
#   ./scripts/start_server_daemon.sh                  # Start daemon
#   ./scripts/start_server_daemon.sh --port 8080       # Custom port
#   ./scripts/start_server_daemon.sh --token mytoken   # With token
#   ./scripts/start_server_daemon.sh --install-systemd # Install systemd service
#   ./scripts/start_server_daemon.sh --status          # Check daemon status
#
# Environment variables:
#   PORT              Server port (default: 8000)
#   HOST              Bind address (default: 0.0.0.0)
#   CONNECTION_TOKEN  Security token for access
#   VSCODUM_WEB_HOME  Server installation directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Defaults ────────────────────────────────────────────────────────────────
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
TOKEN="${CONNECTION_TOKEN:-}"
VSCODUM_WEB_HOME="${VSCODUM_WEB_HOME:-${PROJECT_DIR}}"
PID_FILE="/tmp/vscodium-web.pid"
LOG_DIR="${VSCODUM_WEB_HOME}/logs"
LOG_FILE="${LOG_DIR}/vscodium-web.log"
INSTALL_SYSTEMD=false
SHOW_STATUS=false

# ── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)             PORT="$2"; shift 2 ;;
    --host)             HOST="$2"; shift 2 ;;
    --token)            TOKEN="$2"; shift 2 ;;
    --install-systemd)  INSTALL_SYSTEMD=true; shift ;;
    --status)           SHOW_STATUS=true; shift ;;
    --help|-h)
      echo "VSCodium Web — Start Daemon"
      echo ""
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --port PORT             Server port (default: 8000)"
      echo "  --host HOST             Bind address (default: 0.0.0.0)"
      echo "  --token TOKEN           Connection token for security"
      echo "  --install-systemd       Install as systemd service (Linux)"
      echo "  --status                Show daemon status and exit"
      echo "  --help, -h              Show this help"
      echo ""
      echo "Environment variables:"
      echo "  PORT, HOST, CONNECTION_TOKEN"
      echo "  VSCODUM_WEB_HOME        Server installation directory"
      exit 0
      ;;
    *)                  echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Status mode ─────────────────────────────────────────────────────────────
if [[ "${SHOW_STATUS}" == "true" ]]; then
  exec "${SCRIPT_DIR}/status_server.sh"
fi

# ── Find the server directory ───────────────────────────────────────────────
SERVER_DIR="${SERVER_DIR:-}"
if [[ -z "${SERVER_DIR}" ]]; then
  for candidate in \
    "${VSCODUM_WEB_HOME}/web-build/server" \
    "${VSCODUM_WEB_HOME}/server" \
    "${VSCODUM_WEB_HOME}/vscode-reh-web-"* ; do
    if [[ -d "${candidate}" ]]; then
      SERVER_DIR="${candidate}"
      break
    fi
  done
fi

if [[ -z "${SERVER_DIR}" ]]; then
  echo "Error: No built server found."
  echo "Build the web version first: ./build_web.sh"
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
  exit 1
fi

# ── Install systemd service ─────────────────────────────────────────────────
if [[ "${INSTALL_SYSTEMD}" == "true" ]]; then
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "systemd is only available on Linux."
    exit 1
  fi

  SERVICE_FILE="/etc/systemd/system/vscodium-web.service"
  if [[ ! -w "/etc/systemd/system" ]]; then
    echo "Need root to install systemd service. Try: sudo $0 --install-systemd"
    exit 1
  fi

  cat > "${SERVICE_FILE}" << SERVICEEOF
[Unit]
Description=VSCodium Web Server
After=network.target

[Service]
Type=simple
User=vscodium
WorkingDirectory=${SERVER_DIR}
Environment=PORT=${PORT}
Environment=HOST=${HOST}
Environment=CONNECTION_TOKEN=${TOKEN}
ExecStart=${SERVER_BIN} --port \${PORT} --host \${HOST} \${CONNECTION_TOKEN:+--connection-token \${CONNECTION_TOKEN}}
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICEEOF

  systemctl daemon-reload
  systemctl enable vscodium-web
  systemctl start vscodium-web
  systemctl status vscodium-web --no-pager

  echo ""
  echo "Systemd service installed and started."
  echo "Manage with: systemctl {start|stop|restart|status} vscodium-web"
  exit 0
fi

# ── Start daemon ────────────────────────────────────────────────────────────
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

# Create log directory
mkdir -p "${LOG_DIR}"

BUILD_ARGS=(
  --port "${PORT}"
  --host "${HOST}"
)
if [[ -n "${TOKEN}" ]]; then
  BUILD_ARGS+=(--connection-token "${TOKEN}")
else
  BUILD_ARGS+=(--without-connection-token)
fi

echo "══════════════════════════════════════════════"
echo "  VSCodium Web Server Daemon"
echo "══════════════════════════════════════════════"
echo "  Server:  ${SERVER_DIR}"
echo "  Binary:  ${SERVER_BIN}"
echo "  Host:    ${HOST}"
echo "  Port:    ${PORT}"
echo "  PID:     ${PID_FILE}"
echo "  Log:     ${LOG_FILE}"
echo "══════════════════════════════════════════════"
echo ""

cd "${SERVER_DIR}"

# Start with nohup
nohup "${SERVER_BIN}" "${BUILD_ARGS[@]}" > "${LOG_FILE}" 2>&1 &
PID=$!
echo "${PID}" > "${PID_FILE}"

# Wait and verify
sleep 3
if kill -0 "${PID}" 2>/dev/null; then
  echo "✓ Daemon started successfully (PID: ${PID})"
  echo "  URL:  http://${HOST}:${PORT}/"
  echo "  Log:  ${LOG_FILE}"
  echo ""
  echo "  Manage:"
  echo "    Status: ./scripts/status_server.sh"
  echo "    Stop:   ./scripts/stop_server.sh"
  echo "    View:   tail -f ${LOG_FILE}"
else
  echo "✗ Daemon failed to start. Check log:"
  tail -30 "${LOG_FILE}"
  rm -f "${PID_FILE}"
  exit 1
fi
