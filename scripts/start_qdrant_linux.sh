#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Qdrant Locally (Linux)"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
BIN_DIR="$ROOT_DIR/bin"
DATA_DIR="$ROOT_DIR/docker/qdrant_storage"

mkdir -p "$BIN_DIR" "$DATA_DIR"

# Download Qdrant binary for Linux if not present
if ! command -v qdrant &> /dev/null && [ ! -x "$BIN_DIR/qdrant" ]; then
  echo "📦 Qdrant not found. Downloading Linux binary..."
  TMP_TGZ="$(mktemp -u).tar.gz"
  # Latest known stable compatible with client in repo (can adjust as needed)
  VERSION="v1.8.2"
  URL="https://github.com/qdrant/qdrant/releases/download/${VERSION}/qdrant-x86_64-unknown-linux-gnu.tar.gz"
  echo "⬇️  $URL"
  curl -L "$URL" -o "$TMP_TGZ"
  tar -xzf "$TMP_TGZ" -C "$BIN_DIR" --strip-components=0
  rm -f "$TMP_TGZ"
  # Ensure executable
  chmod +x "$BIN_DIR/qdrant"
  echo "✅ Qdrant downloaded to $BIN_DIR/qdrant"
fi

# Choose binary: system qdrant or local one
QDRANT_BIN="qdrant"
if ! command -v qdrant &> /dev/null; then
  QDRANT_BIN="$BIN_DIR/qdrant"
fi

echo "Starting Qdrant server..."
"$QDRANT_BIN" --storage-dir "$DATA_DIR" > "$ROOT_DIR/qdrant.log" 2>&1 &
PID=$!
echo $PID > "$ROOT_DIR/qdrant.pid"

echo "Waiting for Qdrant to be ready..."
for i in {1..40}; do
  if curl -fsS http://localhost:6333/health >/dev/null 2>&1; then
    echo "✅ Qdrant is ready!"
    echo "PID: $(cat "$ROOT_DIR/qdrant.pid")"
    echo "Logs: $ROOT_DIR/qdrant.log"
    echo "To stop: kill \$(cat $ROOT_DIR/qdrant.pid)"
    exit 0
  fi
  sleep 1
done

echo "❌ Qdrant failed to start in time"
echo "Check logs at: $ROOT_DIR/qdrant.log"
exit 1

