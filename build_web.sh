#!/usr/bin/env bash
# shellcheck disable=SC1091
#
# build_web.sh — Web-only VSCodium build script
#
# Builds only the reh-web (Remote Extension Host web) component of VSCodium,
# producing a standalone web server package that runs VSCodium in a browser
# without requiring Electron or any desktop GUI.
#
# Usage:
#   ./build_web.sh                    # Build for current platform (x64)
#   VSCODE_ARCH=arm64 ./build_web.sh  # Build for ARM64
#   OS_NAME=linux ./build_web.sh      # Build for Linux
#   OS_NAME=osx ./build_web.sh        # Build for macOS
#   OS_NAME=windows ./build_web.sh    # Build for Windows
#
# Platform auto-detection (overridable via OS_NAME):
#   Linux   → linux
#   macOS   → osx
#   Windows → windows (Git Bash / MSYS2 / Cygwin detected automatically)
#
# Environment variables:
#   VSCODE_QUALITY    - "stable" (default) or "insider"
#   VSCODE_ARCH       - Architecture: x64, arm64, armhf, etc.
#   OS_NAME           - linux, osx, windows (auto-detected)
#   CI_BUILD          - "yes" for CI, "no" for local (default: "no")
#   SHOULD_BUILD      - Must be "yes" to actually build
#   DISABLE_UPDATE    - "yes" to disable update checks
#   MAX_OLD_SPACE_SIZE - Node.js max old space size (default: 8192)

set -e

# ── Defaults ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "${SCRIPT_DIR}"

VSCODE_QUALITY="${VSCODE_QUALITY:-stable}"
VSCODE_ARCH="${VSCODE_ARCH:-x64}"
OS_NAME="${OS_NAME:-}"

# Auto-detect OS if not set
if [[ -z "${OS_NAME}" ]]; then
  UNAME_S="$(uname -s)"
  case "${UNAME_S}" in
    MINGW*|MSYS*|CYGWIN*) OS_NAME="windows"  ;;
    Linux*)               OS_NAME="linux"    ;;
    Darwin*)              OS_NAME="osx"      ;;
    *)                    echo "Unknown OS: ${UNAME_S}"; exit 1 ;;
  esac
fi

CI_BUILD="${CI_BUILD:-no}"
SHOULD_BUILD="${SHOULD_BUILD:-yes}"
DISABLE_UPDATE="${DISABLE_UPDATE:-yes}"
MAX_OLD_SPACE_SIZE="${MAX_OLD_SPACE_SIZE:-8192}"

# Map OS_NAME to VSCODE_PLATFORM
case "${OS_NAME}" in
  linux*)  VSCODE_PLATFORM="linux"  ;;
  osx*)    VSCODE_PLATFORM="darwin" ;;
  win*)    VSCODE_PLATFORM="win32"  ;;
  *)       echo "Unknown OS: ${OS_NAME}"; exit 1 ;;
esac

echo "═══════════════════════════════════════════════════════════════"
echo "  VSCodium Web Build"
echo "═══════════════════════════════════════════════════════════════"
echo "  Quality:       ${VSCODE_QUALITY}"
echo "  Architecture:  ${VSCODE_ARCH}"
echo "  Platform:      ${VSCODE_PLATFORM} (${OS_NAME})"
echo "  CI Mode:       ${CI_BUILD}"
echo "───────────────────────────────────────────────────────────────"

# ── Check prerequisites ─────────────────────────────────────────────────────
command -v node >/dev/null 2>&1 || { echo "Error: Node.js is required"; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "Error: npm is required"; exit 1; }
command -v jq   >/dev/null 2>&1 || { echo "Error: jq is required"; exit 1; }
command -v git  >/dev/null 2>&1 || { echo "Error: git is required"; exit 1; }

NODE_VERSION=$(node -v)
echo "  Node:          ${NODE_VERSION}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Get the upstream VS Code source ─────────────────────────────────
echo "▸ Step 1/4: Fetching upstream VS Code source..."

export VSCODE_QUALITY
export CI_BUILD

# The vscode/ directory should not exist yet, but clean up if it does
if [[ -d "vscode" ]]; then
  echo "  Cleaning existing vscode/ directory..."
  rm -rf vscode
fi

# Temporarily set SHOULD_BUILD so get_repo.sh works properly
SHOULD_BUILD="yes" bash get_repo.sh

echo "  ✓ Source fetched"
echo ""

# ── Step 2: Apply VSCodium patches and branding ────────────────────────────
echo "▸ Step 2/4: Applying VSCodium patches and branding..."

export SHOULD_BUILD="yes"
export VSCODE_ARCH
export OS_NAME
export VSCODE_PLATFORM
export DISABLE_UPDATE
export MAX_OLD_SPACE_SIZE
export APP_NAME="VSCodium"
export BINARY_NAME="codium"
export GH_REPO_PATH="inboxxobni/vscodiumweb"
export ORG_NAME="inboxxobni"

# Source version.sh to set BUILD_SOURCEVERSION
source version.sh

export RELEASE_VERSION
export MS_TAG
export MS_COMMIT
export BUILD_SOURCEVERSION

# Run prepare_vscode.sh to apply patches and branding
bash prepare_vscode.sh

echo "  ✓ Patches applied"
echo ""

# ── Step 3: Build reh-web ───────────────────────────────────────────────────
# Note: prepare_vscode.sh already installed dependencies via npm ci
# inside the vscode/ directory, so we just need to run the build.
echo "▸ Step 3/4: Building reh-web (web server)..."
echo "  (This is the main build step and may take several minutes)"
echo ""

cd vscode

export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export NODE_OPTIONS="--max-old-space-size=${MAX_OLD_SPACE_SIZE}"
export VSCODE_PUBLISH_COUNTER=1

if [[ "${VSCODE_PLATFORM}" == "linux" ]]; then
  export VSCODE_SKIP_NODE_VERSION_CHECK=1
fi

npm run gulp minify-vscode-reh-web
npm run gulp "vscode-reh-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}-min-ci"

echo ""
echo "  ✓ reh-web built successfully"
echo ""

cd ..

# ── Step 4: Package the web server ──────────────────────────────────────────
echo "▸ Step 4/4: Packaging web server..."

OUTPUT_DIR="web-build"
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

# The built reh-web should be in vscode-reh-web-{platform}-{arch}/
REH_DIR="vscode-reh-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}"

if [[ -d "${REH_DIR}" ]]; then
  echo "  Packaging from ${REH_DIR}/..."

  # Copy the entire reh-web build
  cp -r "${REH_DIR}/" "${OUTPUT_DIR}/server/"

    # Get the server application name from the built product.json
  SERVER_APP_NAME=$(node -p "require('./${REH_DIR}/product.json').serverApplicationName // 'codium-server'" 2>/dev/null || echo "codium-server")

  # Create convenience run script inside the package
  cat > "${OUTPUT_DIR}/run.sh" << RUNEOF
#!/usr/bin/env bash
# run.sh — Start VSCodium Web Server
#
# Usage: ./run.sh [options]
#
# Options:
#   --port PORT       Server port (default: 8000)
#   --host HOST       Bind address (default: 0.0.0.0)
#   --token TOKEN     Connection token for security
#   --without-token   Disable connection token (not recommended for production)
#   --help            Show this help

set -e

SCRIPT_DIR="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" && pwd )"
SERVER_DIR="\${SCRIPT_DIR}/server"

PORT="\${PORT:-8000}"
HOST="\${HOST:-0.0.0.0}"
TOKEN="\${CONNECTION_TOKEN:-}"
SERVER_APP_NAME="${SERVER_APP_NAME}"
ARGS=()

while [[ \$# -gt 0 ]]; do
  case "\$1" in
    --port)           PORT="\$2"; shift 2 ;;
    --host)           HOST="\$2"; shift 2 ;;
    --token)          TOKEN="\$2"; shift 2 ;;
    --without-token)  WITHOUT_TOKEN="yes"; shift ;;
    --help)           echo "Usage: \$0 [--port PORT] [--host HOST] [--token TOKEN] [--without-token]"
                      exit 0 ;;
    *)                ARGS+=("\$1"); shift ;;
  esac
done

echo "══════════════════════════════════════════════"
echo "  VSCodium Web Server"
echo "══════════════════════════════════════════════"
echo "  Host: \${HOST}"
echo "  Port: \${PORT}"
echo "──────────────────────────────────────────────"

if [[ -n "\${TOKEN}" ]]; then
  echo "  Token: \${TOKEN}"
  echo "  URL:   http://\${HOST}:\${PORT}/?tkn=\${TOKEN}"
elif [[ -n "\${WITHOUT_TOKEN}" ]]; then
  echo "  \u26a0  No connection token (not recommended)"
  echo "  URL:   http://\${HOST}:\${PORT}/"
else
  echo "  URL:   http://\${HOST}:\${PORT}/"
  echo "  (set CONNECTION_TOKEN or --token for security)"
fi
echo "══════════════════════════════════════════════"
echo ""

cd "\${SERVER_DIR}"

# The server binary is named after serverApplicationName in product.json
# (e.g., codium-server for stable, codium-server-insiders for insider)
if [[ -f "./bin/\${SERVER_APP_NAME}" ]]; then
  exec ./bin/\${SERVER_APP_NAME} \\
    --port "\${PORT}" \\
    --host "\${HOST}" \\
    \${TOKEN:+--connection-token "\${TOKEN}"} \\
    \${WITHOUT_TOKEN:+--without-connection-token} \\
    "\${ARGS[@]}"
elif ls ./bin/codium-server* 1>/dev/null 2>&1; then
  SERVER_BIN=\$(ls ./bin/codium-server* | head -1)
  exec "\${SERVER_BIN}" \\
    --port "\${PORT}" \\
    --host "\${HOST}" \\
    \${TOKEN:+--connection-token "\${TOKEN}"} \\
    \${WITHOUT_TOKEN:+--without-connection-token} \\
    "\${ARGS[@]}"
elif [[ -f "./out/server-web/server-main.js" ]]; then
  exec node ./out/server-web/server-main.js \\
    --port "\${PORT}" \\
    --host "\${HOST}" \\
    \${TOKEN:+--connection-token "\${TOKEN}"} \\
    \${WITHOUT_TOKEN:+--without-connection-token} \\
    "\${ARGS[@]}"
else
  echo "Error: Could not find server binary."
  echo "Contents of \${SERVER_DIR}:"
  ls -la "\${SERVER_DIR}/"
  echo ""
  echo "Contents of \${SERVER_DIR}/bin/:"
  ls -la "\${SERVER_DIR}/bin/" 2>/dev/null || echo "  (no bin/ directory)"
  exit 1
fi
RUNEOF
  chmod +x "${OUTPUT_DIR}/run.sh"

  # Create the archive
  if [[ "${OS_NAME}" == "windows" ]]; then
    ARCHIVE_EXT="zip"
    echo "  Creating archive: ${OUTPUT_DIR}/vscodium-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}-${RELEASE_VERSION}.zip"
    if command -v 7z &>/dev/null; then
      cd "${OUTPUT_DIR}" && 7z a "vscodium-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}-${RELEASE_VERSION}.zip" server run.sh && cd ..
    else
      cd "${OUTPUT_DIR}" && zip -r "vscodium-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}-${RELEASE_VERSION}.zip" server run.sh && cd ..
    fi
  else
    ARCHIVE_EXT="tar.gz"
    echo "  Creating archive: ${OUTPUT_DIR}/vscodium-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}-${RELEASE_VERSION}.tar.gz"
    tar czf "${OUTPUT_DIR}/vscodium-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}-${RELEASE_VERSION}.tar.gz" \
      -C "${OUTPUT_DIR}" server run.sh
  fi

  echo ""
  echo "═══════════════════════════════════════════════════════════════"
  echo "  Build Complete!"
  echo "═══════════════════════════════════════════════════════════════"
  echo ""
  echo "  Web server package: web-build/"
  echo "    Server:     web-build/server/"
  echo "    Run script: web-build/run.sh"
  echo "    Archive:    web-build/vscodium-web-${VSCODE_PLATFORM}-${VSCODE_ARCH}-${RELEASE_VERSION}.${ARCHIVE_EXT}"
  echo ""
  echo "  Quick start:"
  echo "    cd web-build && ./run.sh"
  echo ""
  echo "  Or with a token:"
  echo "    cd web-build && ./run.sh --port 8000 --token mysecrettoken"
  echo ""
  echo "  Then open http://localhost:8000 in your browser."
  echo "═══════════════════════════════════════════════════════════════"
else
  echo "Error: reh-web build directory not found: ${REH_DIR}"
  echo "  Looked in: ${SCRIPT_DIR}/${REH_DIR}"
  ls -la "${SCRIPT_DIR}/" | grep reh-web || true
  exit 1
fi
