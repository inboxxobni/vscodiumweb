# ── VSCodium Web Server — Multi-stage Docker Build ──────────────────────────
#
# This Dockerfile builds VSCodium's reh-web (Remote Extension Host web)
# component and packages it as a lightweight web server image.
#
# The reh-web build produces a standalone Node.js server that serves the
# full VSCodium editor in a browser — no Electron, no desktop GUI needed.
#
# Build:
#   docker build -t vscodium-web .
#
# Run:
#   docker run -p 8000:8000 vscodium-web
#   # Open http://localhost:8000 in your browser
#
# With token:
#   docker run -p 8000:8000 -e CONNECTION_TOKEN=mytoken vscodium-web
#   # Open http://localhost:8000/?tkn=mytoken
#
# With custom port:
#   docker run -p 8080:8080 -e PORT=8080 vscodium-web
#
# Persist config:
#   docker run -p 8000:8000 -v vscodium-config:/config vscodium-web
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build reh-web ───────────────────────────────────────────────────
FROM node:22-bookworm AS builder

LABEL stage=builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    jq \
    python3 \
    make \
    g++ \
    libkrb5-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy the VSCodium builder repo
COPY . .

# Build only the reh-web component
# This fetches VS Code source, applies VSCodium patches, and builds reh-web
RUN SHOULD_BUILD=yes \
    VSCODE_QUALITY=stable \
    VSCODE_ARCH=x64 \
    OS_NAME=linux \
    CI_BUILD=no \
    DISABLE_UPDATE=yes \
    MAX_OLD_SPACE_SIZE=8192 \
    bash build_web.sh

# ── Stage 2: Minimal runtime image ──────────────────────────────────────────
FROM node:22-bookworm-slim

LABEL description="VSCodium Web — Browser-based editor without Electron"
LABEL maintainer="inboxxobni/vscodiumweb"
LABEL org.opencontainers.image.source="https://github.com/inboxxobni/vscodiumweb"

# Install runtime dependencies for native Node.js modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Create vscodium user (non-root)
RUN groupadd -r vscodium && useradd -r -g vscodium -m -d /home/vscodium vscodium

# Copy the built reh-web server from the builder stage
COPY --from=builder /build/web-build/server /app

# Copy the run script
COPY --from=builder /build/web-build/run.sh /app/run.sh

# Create config directory
RUN mkdir -p /config && chown -R vscodium:vscodium /config /app

WORKDIR /app

USER vscodium

# Default environment
ENV PORT=8000 \
    HOST=0.0.0.0 \
    CONNECTION_TOKEN=""

EXPOSE 8000

ENTRYPOINT ["/app/run.sh"]
