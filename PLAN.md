# VSCodium Web — Plan

## Objective

Transform the VSCodium builder repository into a web-first distribution that serves VSCodium through a browser — removing the Electron dependency and making it run as a standalone web server.

## Approach

VSCode/VSCodium already has a built-in web server component called **reh-web** (Remote Extension Host web). This is the same technology that powers vscode.dev and GitHub Codespaces. We don't need to fork VS Code itself — we just need to:

1. Build only the `reh-web` component (skip Electron desktop builds)
2. Package it as a deployable web server
3. Provide Docker, Docker Compose, and local run scripts
4. Document everything

## Files Created

| File | Purpose |
|------|---------|
| `build_web.sh` | Web-only build script — fetches VS Code source, applies VSCodium patches, builds only reh-web |
| `run_web.sh` | Convenience script to find and run the built web server |
| `Dockerfile` | Multi-stage Docker build (build reh-web → package minimal runtime) |
| `docker-compose.yml` | Easy Docker deployment with config |
| `.github/workflows/build-web.yml` | CI workflow to build reh-web and publish artifacts |
| `docs/web-version.md` | Comprehensive documentation for the web version |
| `README.md` (updated) | Added web version section to main readme |

## How reh-web Works

The `reh-web` build target in VS Code's gulp build system produces a standalone Node.js package containing:

- `bin/<serverApplicationName>` (e.g., `bin/codium-server`) — server startup script
- `out/server-web/` — compiled server code
- `extensions/` — built-in extensions (workspace extensions only)
- `node_modules/` — dependencies
- `product.json` — with commit, version info
- Bundled `node` binary

This package runs entirely in Node.js — no Electron, no desktop GUI.

## Key Decisions

1. **Keep the builder repo structure** — Don't fork VS Code source directly. Keep the VSCodium builder repo approach (scripts that fetch and patch VS Code).
2. **Add a dedicated web build script** — `build_web.sh` instead of modifying `build.sh` to keep backward compatibility.
3. **Skip Electron builds** — The web build script sets `ELECTRON_SKIP_BINARY_DOWNLOAD=1` and only runs the reh-web gulp targets.
4. **Docker multi-stage build** — Build in a full Node.js image, deploy in a slim image.
5. **Open VSX marketplace** — Use the existing Open VSX marketplace configuration from VSCodium.

## Build Pipeline

```
get_repo.sh → prepare_vscode.sh → npm ci → gulp minify-vscode-reh-web → gulp vscode-reh-web-*-min-ci → package
```

The web build produces:
```
web-build/
├── server/          # The reh-web server package
│   ├── bin/
│   │   └── codium-server  # Server binary
│   ├── out/
│   ├── extensions/
│   ├── node_modules/
│   └── product.json
├── run.sh           # Convenience run script
└── vscodium-web-*.tar.gz  # Deployable archive
```

## Security

- Connection token support via `--token` or `CONNECTION_TOKEN` env var
- Optional `--without-token` for development/open access
- Reverse proxy support (Nginx, Caddy) for HTTPS
- Non-root user in Docker image

## Future Work

- [ ] Pre-built releases on GitHub
- [ ] ARM64 build support in CI
- [ ] Health check endpoint
- [ ] Automatic extension sync from Open VSX
- [ ] WebSocket-based terminal improvements
- [ ] Multi-user support
- [ ] Session persistence
