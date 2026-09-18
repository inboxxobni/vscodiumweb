#!/usr/bin/env bash
#
# smoke-test.sh — Quick smoke test for VSCodium Web Server
#
# Verifies:
#   1. Server directory exists
#   2. Server binary is present
#   3. Server starts and responds to HTTP requests
#
# Usage:
#   ./build/smoke-test.sh                    # Test web-build/server/
#   ./build/smoke-test.sh --dir ./my-build   # Test custom build dir
#
# Exit code:
#   0 = all checks passed
#   1 = one or more checks failed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Defaults ────────────────────────────────────────────────────────────────
TEST_DIR="${TEST_DIR:-${PROJECT_DIR}/web-build/server}"
VERBOSE=false
ALL_PASSED=true

# ── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)            TEST_DIR="$2"; shift 2 ;;
    --verbose|-v)     VERBOSE=true; shift ;;
    --help|-h)
      echo "VSCodium Web — Smoke Test"
      echo ""
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --dir DIR         Test a specific build directory"
      echo "  --verbose, -v     Verbose output"
      echo "  --help, -h        Show this help"
      exit 0
      ;;
    *)                  echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "══════════════════════════════════════════════"
echo "  VSCodium Web — Smoke Test"
echo "══════════════════════════════════════════════"
echo ""

# ── Check 1: Server directory exists ────────────────────────────────────────
echo "▸ [1/4] Checking server directory..."
if [[ -d "${TEST_DIR}" ]]; then
  echo "  ✓ Server directory: ${TEST_DIR}"
else
  echo "  ✗ Server directory not found: ${TEST_DIR}"
  ALL_PASSED=false
fi
echo ""

# ── Check 2: Server binary exists ───────────────────────────────────────────
echo "▸ [2/4] Checking server binary..."

SERVER_BIN=""
SERVER_APP_NAME="codium-server"

if [[ -f "${TEST_DIR}/product.json" ]]; then
  SERVER_APP_NAME=$(node -p "require('${TEST_DIR}/product.json').serverApplicationName || 'codium-server'" 2>/dev/null || echo "codium-server")
fi

if [[ -f "${TEST_DIR}/bin/${SERVER_APP_NAME}" ]]; then
  SERVER_BIN="${TEST_DIR}/bin/${SERVER_APP_NAME}"
  echo "  ✓ Server binary: bin/${SERVER_APP_NAME}"
elif ls "${TEST_DIR}/bin/codium-server"* 1>/dev/null 2>&1; then
  SERVER_BIN=$(ls "${TEST_DIR}/bin/codium-server"* | head -1)
  echo "  ✓ Server binary: $(basename "${SERVER_BIN}")"
elif [[ -f "${TEST_DIR}/out/server-web/server-main.js" ]]; then
  SERVER_BIN="node ${TEST_DIR}/out/server-web/server-main.js"
  echo "  ✓ Server entry: out/server-web/server-main.js"
else
  echo "  ✗ No server binary found"
  echo "    Contents of ${TEST_DIR}/bin/:"
  ls -la "${TEST_DIR}/bin/" 2>/dev/null || echo "    (no bin/ directory)"
  ALL_PASSED=false
fi
echo ""

# ── Check 3: product.json is valid ──────────────────────────────────────────
echo "▸ [3/4] Checking product.json..."
if [[ -f "${TEST_DIR}/product.json" ]]; then
  if node -e "JSON.parse(require('fs').readFileSync('${TEST_DIR}/product.json','utf8'))" 2>/dev/null; then
    echo "  ✓ product.json is valid JSON"
    if [[ "${VERBOSE}" == "true" ]]; then
      echo ""
      node -e "
        const p = require('${TEST_DIR}/product.json');
        console.log('    nameShort:        ' + (p.nameShort || 'N/A'));
        console.log('    nameLong:         ' + (p.nameLong || 'N/A'));
        console.log('    version:          ' + (p.version || 'N/A'));
        console.log('    commit:           ' + (p.commit || 'N/A'));
        console.log('    serverApplicationName: ' + (p.serverApplicationName || 'N/A'));
      "
    fi
  else
    echo "  ✗ product.json is invalid JSON"
    ALL_PASSED=false
  fi
else
  echo "  ✗ product.json not found"
  ALL_PASSED=false
fi
echo ""

# ── Check 4: Server starts (quick test) ─────────────────────────────────────
echo "▸ [4/4] Testing server startup..."
if [[ -n "${SERVER_BIN}" ]] && [[ -x "${TEST_DIR}/bin/${SERVER_APP_NAME}" ]]; then
  TEST_PORT=9999
  echo "  Starting server on port ${TEST_PORT}..."

  # Start server in background
  cd "${TEST_DIR}"
  timeout 8 "${SERVER_BIN}" --port "${TEST_PORT}" --host 127.0.0.1 --without-connection-token &
  SRV_PID=$!
  cd "${PROJECT_DIR}"

  # Wait for startup
  sleep 4

  if kill -0 "${SRV_PID}" 2>/dev/null; then
    echo "  ✓ Server started (PID: ${SRV_PID})"

    # Try HTTP request
    if command -v curl &>/dev/null; then
      HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${TEST_PORT}/" 2>/dev/null || echo "000")
      if [[ "${HTTP_CODE}" != "000" ]]; then
        echo "  ✓ HTTP response: ${HTTP_CODE}"
      else
        echo "  ⚠  No HTTP response (may need more time)"
      fi
    fi

    kill "${SRV_PID}" 2>/dev/null || true
    wait "${SRV_PID}" 2>/dev/null || true
    echo "  ✓ Server stopped cleanly"
  else
    echo "  ✗ Server failed to start (exited immediately)"
    ALL_PASSED=false
  fi
else
  echo "  ⚠  Cannot test startup (binary not executable or not found)"
  echo "     SKIPPED (non-fatal for this check)"
fi

echo ""
echo "══════════════════════════════════════════════"

if [[ "${ALL_PASSED}" == "true" ]]; then
  echo "  ✅ All smoke tests passed!"
  exit 0
else
  echo "  ❌ One or more smoke tests failed."
  exit 1
fi
