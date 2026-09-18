# VSCodium Web — Browser-Based Editor

VSCodium Web is the **web server component** of VSCodium (also known as `reh-web` or Remote Extension Host web). It serves the full VSCodium editor in a browser — **no Electron, no desktop GUI required**.

You access it at `http://your-server:8000` and get the complete VSCodium editing experience: file browser, editor, terminal, extensions, settings, Git integration, and more.

## How It Works

VSCode/VSCodium includes a built-in `reh-web` (Remote Extension Host web) component. This is the same technology that powers:

- **vscode.dev** — Microsoft's browser-based VS Code
- **GitHub Codespaces** — browser-based development environments
- **code-server** — community browser-based VS Code

The `reh-web` build produces a standalone Node.js server package that:

1. Serves the VSCodium web UI (HTML, CSS, JavaScript)
2. Runs extensions on the server side
3. Provides a terminal, file system access, and Git integration
4. Listens on a configurable HTTP port

No Electron binaries, no X11/Wayland display, no desktop environment needed.

## Quick Start

### Prerequisites

- **Node.js** 22.x or later
- **npm**
- **git**
- **jq**
- **Python 3** (for native module builds)
- 8GB+ RAM (recommended)
- 10GB+ free disk space (for the build)

### Build

```bash
# Clone the repo
git clone https://github.com/inboxxobni/vscodiumweb.git
cd vscodiumweb

# Build the web version (this fetches VS Code source + applies patches + builds)
./build_web.sh
```

The build will:
1. Fetch the upstream Microsoft VS Code source code
2. Apply VSCodium patches (branding, telemetry removal, marketplace config)
3. Install dependencies
4. Build only the `reh-web` component (skips Electron entirely)
5. Package everything into `web-build/`

**Build time:** 15–45 minutes depending on your machine and internet speed.

### Run

After building:

```bash
# Run without a security token (open access)
./web-build/run.sh

# Run with a security token
./web-build/run.sh --token mysecrettoken

# Run on a different port
./web-build/run.sh --port 8080

# Run without any token (not recommended for production)
./web-build/run.sh --without-token
```

Then open your browser to:
- `http://localhost:8000/` (without token)
- `http://localhost:8000/?tkn=mysecrettoken` (with token)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server HTTP port |
| `HOST` | `0.0.0.0` | Bind address |
| `CONNECTION_TOKEN` | (empty) | Security token for access |

## Docker

### Build and Run

```bash
# Build the Docker image
docker build -t vscodium-web .

# Run the container
docker run -d \
  --name vscodium-web \
  -p 8000:8000 \
  -e CONNECTION_TOKEN=mysecrettoken \
  -v vscodium-web-config:/config \
  vscodium-web
```

### Docker Compose

```bash
# Start
docker compose up -d

# With security token
CONNECTION_TOKEN=mysecret docker compose up -d

# Build from source
docker compose build
docker compose up -d

# Stop
docker compose down
```

### Docker Environment Variables

| Variable | Description |
|----------|-------------|
| `CONNECTION_TOKEN` | Security token for web access |
| `CONNECTION_TOKEN_FILE` | Path to a file containing the token |
| `SUDO_PASSWORD` | Password for sudo access in the terminal |
| `SUDO_PASSWORD_HASH` | Hashed sudo password |

## Advanced Usage

### Using with a Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name vscodium.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

### With Let's Encrypt (Caddy)

```caddyfile
vscodium.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

### Persisting Configuration

The web server stores configuration, extensions, and user data. Mount a volume:

```bash
# Docker
docker run -v vscodium-data:/home/vscodium/.vscodium-server vscodium-web

# Local
# Configuration is stored in ~/.vscodium-server/ by default
```

### Using with GitHub Integration

1. Drop your SSH key into the config directory
2. Configure Git:

```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

## Build Options

### Build for Different Architectures

```bash
# Build for ARM64
VSCODE_ARCH=arm64 ./build_web.sh

# Build for x64 (default)
VSCODE_ARCH=x64 ./build_web.sh

# Build insider quality
VSCODE_QUALITY=insider ./build_web.sh
```

### Environment Variables for Build

| Variable | Default | Description |
|----------|---------|-------------|
| `VSCODE_QUALITY` | `stable` | Build quality: `stable` or `insider` |
| `VSCODE_ARCH` | `x64` | Target architecture: `x64`, `arm64`, `armhf`, `riscv64` |
| `OS_NAME` | auto | Target OS: `linux`, `osx`, `windows` |
| `DISABLE_UPDATE` | `yes` | Disable update checks |
| `MAX_OLD_SPACE_SIZE` | `8192` | Node.js max heap size (MB) |

## CI / Automated Builds

The repository includes a GitHub Actions workflow (`.github/workflows/build-web.yml`) that:

1. Builds the reh-web component on every push
2. Uploads the built server as a deployable artifact
3. Optionally builds and pushes a Docker image to GitHub Container Registry

### Triggering a Build

- Push to `master`, `insider`, or `web-version` branches
- Open a pull request
- Manually via `workflow_dispatch` with configurable quality and architecture

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   Browser                         │
│  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ Editor UI    │  │ Terminal   │  │ Settings │  │
│  │ (Monaco)     │  │ (xterm.js) │  │          │  │
│  └──────────────┘  └────────────┘  └──────────┘  │
└──────────────────────┬───────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼───────────────────────────┐
│              VSCodium Web Server                   │
│  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ Server.js    │  │ Extensions │  │ File     │  │
│  │ (Node.js)    │  │ Host       │  │ System   │  │
│  └──────────────┘  └────────────┘  └──────────┘  │
│  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ Terminal    │  │ Git        │  │ Debug    │  │
│  │ PTY         │  │ Integration│  │ Adapters │  │
│  └──────────────┘  └────────────┘  └──────────┘  │
└──────────────────────────────────────────────────┘
```

## Differences from Desktop VSCodium

| Feature | Desktop VSCodium | VSCodium Web |
|---------|-----------------|--------------|
| **Runtime** | Electron + Node.js | Node.js only |
| **GUI** | Native window | Browser |
| **Installation** | `.dmg`, `.deb`, `.exe` | Docker or `node server.js` |
| **Remote access** | SSH extension | Built-in web server |
| **Local file access** | Full OS access | Sandboxed (configurable) |
| **Extensions** | UI + workspace | Workspace + web |
| **Resource usage** | ~500MB RAM | ~200MB RAM |
| **Cross-platform** | Per-platform binary | Single Docker image |

## Troubleshooting

### Build fails with out of memory

Increase Node.js memory:
```bash
MAX_OLD_SPACE_SIZE=16384 ./build_web.sh
```

### Build fails with "npm install failed"

Ensure you have:
- Node.js 22.x (check `.nvmrc`)
- Python 3 installed
- Build tools (build-essential on Linux, Xcode CLI on macOS)

### Server won't start

Check:
- Port 8000 is not in use
- Node.js version matches the build
- The server binary exists in the expected location

### Extensions don't work

Some extensions are UI-only and don't work in web mode. VSCodium uses the [Open VSX](https://open-vsx.org/) marketplace by default. To install extensions:
1. Use the Extensions view in the browser
2. Or install from VSIX files

## References

- [VSCodium GitHub](https://github.com/VSCodium/vscodium)
- [VS Code Server Docs](https://code.visualstudio.com/docs/remote/vscode-server)
- [LinuxServer.io VSCodium Web Docker](https://docs.linuxserver.io/images/docker-vscodium-web/)
- [Open VSX Registry](https://open-vsx.org/)
