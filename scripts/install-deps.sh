#!/usr/bin/env bash
# Install qmd + marp-cli into CLAUDE_PLUGIN_DATA.
# Called by SessionStart hook. MUST NEVER exit non-zero — that blocks sessions.

set +e  # Do not exit on error

# Guard: if env var missing, nothing to do
if [ -z "${CLAUDE_PLUGIN_DATA}" ]; then
  exit 0
fi

if [ -z "${CLAUDE_PLUGIN_ROOT}" ]; then
  exit 0
fi

DATA_DIR="${CLAUDE_PLUGIN_DATA}"
ROOT_DIR="${CLAUDE_PLUGIN_ROOT}"
VERSION_SRC="${ROOT_DIR}/scripts/deps-version.txt"
VERSION_DST="${DATA_DIR}/deps-version.txt"
SENTINEL="${DATA_DIR}/.deps-ok"

# Ensure data directory exists
mkdir -p "${DATA_DIR}" 2>/dev/null || exit 0

# Check if deps are already installed and up to date
if [ -f "${SENTINEL}" ] && [ -f "${VERSION_DST}" ] && [ -f "${VERSION_SRC}" ]; then
  if diff -q "${VERSION_SRC}" "${VERSION_DST}" >/dev/null 2>&1; then
    # Deps already installed and version matches
    exit 0
  fi
fi

# Check for Node.js 18+
if ! command -v node >/dev/null 2>&1; then
  echo "academic-wiki: Node.js 18+ is required for qmd/marp-cli. Please install it." >&2
  exit 0  # don't block the session
fi

# Install dependencies
echo "[academic-wiki] Installing dependencies..." >&2

cd "${DATA_DIR}" || exit 0

# Create a minimal package.json if it doesn't exist
if [ ! -f "package.json" ]; then
  echo '{"private":true}' > package.json
fi

# Install pinned packages from deps-version.txt
while IFS= read -r line; do
  # Skip blank lines and comments
  [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
  npm install --silent "$line" 2>&1 | tail -5 >&2 || {
    echo "academic-wiki: failed to install $line" >&2
    rm -f "${SENTINEL}" "${VERSION_DST}" 2>/dev/null
    exit 0
  }
done < "${VERSION_SRC}"

# Success: copy version file and write sentinel
cp "${VERSION_SRC}" "${VERSION_DST}" 2>/dev/null
touch "${SENTINEL}"
echo "[academic-wiki] Dependencies installed successfully at ${DATA_DIR}." >&2

exit 0
