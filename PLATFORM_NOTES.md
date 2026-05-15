# Cross-Platform Docker Notes — Agent Factory

## Tested Environments

| Platform | Architecture | Docker Version | Status |
|----------|-------------|----------------|--------|
| Windows 11 (WSL2) | AMD64 | Docker Desktop | ✅ Build OK |
| Linux (Debian/Ubuntu) | AMD64 | Docker Engine | ✅ Expected OK |
| macOS Intel | AMD64 | Docker Desktop | ✅ Expected OK |
| macOS M-series | ARM64 | Docker Desktop | ⚠️ See note below |

## ARM64 (Apple M-series) Notes

The base image `python:3.11-slim` has an official ARM64 variant, so `docker build`
works natively on M-series Macs without emulation.

The system Chromium package (`chromium`) from Debian apt is available for ARM64
on Debian Bookworm (the base for `python:3.11-slim`), so browser automation via
Playwright works without changes.

No `--platform` flag is required. Docker Desktop on macOS will select the correct
image variant automatically.

## AMD64 Emulation on ARM64

If you need to force AMD64 on an M-series Mac (e.g. to match a Linux CI target):

```bash
docker build --platform linux/amd64 -t agent-factory .
```

Performance will be slower due to QEMU emulation. Use only when testing AMD64-specific behaviour.

## Build & Run Commands

```bash
# Build image
docker build -t agent-factory .

# Run interactively
docker compose up

# Single query (non-interactive)
docker compose run --rm agent python main.py -q "RAG architecture"
```

## Known Issues

- **Interactive mode**: `main.py` uses `input()` for the REPL. Ensure `stdin_open: true`
  and `tty: true` are set in `docker-compose.yml` (already configured).
- **Playwright on ARM64**: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` points to the system
  Chromium binary at `/usr/bin/chromium`. If Playwright reports a binary not found
  error, verify the path with `docker run --rm agent-factory which chromium`.
- **Output files**: Saved query results are written to `/app/outputs` inside the
  container, which is bind-mounted to `./outputs` on the host.
