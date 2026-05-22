#!/usr/bin/env bash
# Builds proof-capture and installs it to ~/bin/
# Run from anywhere — paths are relative to this script's location.

set -euo pipefail

green() { printf '\033[0;32m  ✓ %s\033[0m\n' "$*"; }
warn()  { printf '\033[0;33m  ⚠ %s\033[0m\n' "$*"; }
info()  { printf '\033[0;34m  → %s\033[0m\n' "$*"; }

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${BIN_DIR:-$HOME/bin}"
mkdir -p "$BIN_DIR"

# Prerequisites
node_major=$(node --version 2>/dev/null | cut -d. -f1 | tr -d 'v' || echo 0)
if [[ "$node_major" -lt 20 ]]; then
  warn "Node ≥ 20 required (got: $(node --version 2>/dev/null || echo 'not found'))"
  exit 1
fi

# Build
info "Installing dependencies..."
cd "$TOOL_DIR"
npm install --silent
green "Dependencies installed"

info "Compiling TypeScript..."
npm run build
green "Compiled to dist/"

# Install Playwright Chromium (headless only)
info "Installing Playwright Chromium..."
npx playwright install chromium --with-deps 2>&1 | grep -E '(Downloading|✓|chromium)' || true
green "Playwright Chromium ready"

# Install wrapper to ~/bin
DIST="$TOOL_DIR/dist/index.js"
chmod +x "$DIST"

cat > "$BIN_DIR/proof-capture" << WRAPPER
#!/usr/bin/env bash
NODE_PATH="$TOOL_DIR/node_modules" exec node "$DIST" "\$@"
WRAPPER
chmod +x "$BIN_DIR/proof-capture"
green "proof-capture installed at $BIN_DIR/proof-capture"

# Smoke test
if "$BIN_DIR/proof-capture" --version &>/dev/null; then
  green "Smoke test passed: $("$BIN_DIR/proof-capture" --version)"
else
  warn "Installed but smoke test failed — check $BIN_DIR/proof-capture"
fi
