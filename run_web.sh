#!/usr/bin/env bash
#
# run_web.sh — Run VSCodium Web Server from built artifacts
#
# This script expects the reh-web build to exist in the vscode-reh-web-*
# directory (as produced by build_web.sh or the existing build.sh).
#
# Usage:
#   ./run_web.sh                    # Run on default port 8000
#   ./run_web.sh --port 8080        # Run on port 8080
#   ./run_web.sh --token mytoken    # Secure with a token
#   ./run_web.sh --without-token    # No token (open access)
#
# Environment variables:
#   PORT              Server port (default: 8000)
#   HOST              Bind address (default: 0.0.0.0)
#   CONNECTION_TOKEN  Connection token for security
#
# Cross-platform: Works on Linux, macOS, and Windows (via WSL/Git Bash)

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# ── Configuration ───────────────────────────────────────────────────────────
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
TOKEN="${CONNECTION_TOKEN:-}"
ARGS=()

# ── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)           PORT="$2"; shift 2 ;;
    --host)           HOST="$2"; shift 2 ;;
    --token)          TOKEN="$2"; shift 2 ;;
    --without-token)  WITHOUT_TOKEN="yes"; shift ;;
    --help|-h)
      echo "VSCodium Web Server — Run Script"
      echo ""
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --port PORT         Server port (default: 8000)"
      echo "  --host HOST         Bind address (default: 0.0.0.0)"
      echo "  --token TOKEN       Connection token for security"
      echo "  --without-token     Disable connection token"
      echo "  --help              Show this help"
      echo ""
      echo "Environment variables:"
      echo "  PORT                Server port"
      echo "  HOST                Bind address"
      echo "  CONNECTION_TOKEN    Connection token"
      echo ""
      echo "Examples:"
      echo "  $0"
      echo "  $0 --port 8080 --token mysecret"
      echo "  PORT=9090 CONNECTION_TOKEN=abc123 $0"
      exit 0
      ;;
    *)                ARGS+=("$1"); shift ;;
  esac
done

# ── Find the reh-web build directory ────────────────────────────────────────
# Look for the built reh-web directory, trying several locations
REH_DIR=""
for candidate in \
  "${SCRIPT_DIR}/vscode-reh-web-"* \
  "${SCRIPT_DIR}/web-build/server" \
  "${SCRIPT_DIR}/_build/vscode-reh-web-"*; do
  if [[ -d "${candidate}" ]]; then
    REH_DIR="${candidate}"
    break
  fi
done

if [[ -z "${REH_DIR}" ]]; then
  echo "Error: No reh-web build found."
  echo ""
  echo "Please build the web version first:"
  echo "  ./build_web.sh"
  echo ""
  echo "Or download a pre-built release from:"
  echo "  https://github.com/inboxxobni/vscodiumweb/releases"
  echo ""
  echo "After downloading, extract the archive and point to it:"
  echo "  tar xzf vscodium-web-*.tar.gz"
  echo "  cd server && ../run.sh"
  exit 1
fi

# Try to get the server application name from product.json
SERVER_APP_NAME="codium-server"
if [[ -f "${REH_DIR}/product.json" ]]; then
  SERVER_APP_NAME=$(node -p "require('${REH_DIR}/product.json').serverApplicationName" 2>/dev/null || echo "codium-server")
fi

echo "══════════════════════════════════════════════"
echo "  VSCodium Web Server"
echo "══════════════════════════════════════════════"
echo "  Server:  ${REH_DIR}"
echo "  Host:    ${HOST}"
echo "  Port:    ${PORT}"
echo "──────────────────────────────────────────────"

if [[ -n "${TOKEN}" ]]; then
  echo "  Token:   ${TOKEN}"
  echo "  URL:     http://${HOST}:${PORT}/?tkn=${TOKEN}"
elif [[ -n "${WITHOUT_TOKEN}" ]]; then
  echo "  ⚠  No connection token (open access)"
  echo "  URL:     http://${HOST}:${PORT}/"
else
  echo "  URL:     http://${HOST}:${PORT}/"
  echo "  (set --token or CONNECTION_TOKEN for security)"
fi
echo "══════════════════════════════════════════════"
echo ""

cd "${REH_DIR}"

# ── Start the server ────────────────────────────────────────────────────────
# The server binary is named after serverApplicationName in product.json
# (e.g., codium-server for stable, codium-server-insiders for insider)
if [[ -f "./bin/${SERVER_APP_NAME}" ]]; then
  echo "Starting server binary: bin/${SERVER_APP_NAME}"
  exec ./bin/${SERVER_APP_NAME} \
    --port "${PORT}" \
    --host "${HOST}" \
    ${TOKEN:+--connection-token "${TOKEN}"} \
    ${WITHOUT_TOKEN:+--without-connection-token} \
    "${ARGS[@]}"
elif ls ./bin/codium-server* 1>/dev/null 2>&1; then
  SERVER_BIN=$(ls ./bin/codium-server* | head -1)
  echo "Starting server binary: ${SERVER_BIN}"
  exec "${SERVER_BIN}" \
    --port "${PORT}" \
    --host "${HOST}" \
    ${TOKEN:+--connection-token "${TOKEN}"} \
    ${WITHOUT_TOKEN:+--without-connection-token} \
    "${ARGS[@]}"
elif [[ -f "./out/server-web/server-main.js" ]]; then
  echo "Starting via server-main.js..."
  exec node ./out/server-web/server-main.js \
    --port "${PORT}" \
    --host "${HOST}" \
    ${TOKEN:+--connection-token "${TOKEN}"} \
    ${WITHOUT_TOKEN:+--without-connection-token} \
    "${ARGS[@]}"
else
  echo "Error: Could not find server executable."
  echo ""
  echo "Contents of ${REH_DIR}:"
  ls -la "${REH_DIR}/"
  echo ""
  echo "Contents of ${REH_DIR}/bin/ (if exists):"
  ls -la "${REH_DIR}/bin/" 2>/dev/null || echo "  (no bin/ directory)"
  exit 1
fi
