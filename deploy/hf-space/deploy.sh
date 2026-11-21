#!/usr/bin/env bash
# Upload the backend to the Hugging Face Space.
#
# Copies an explicit allowlist of files into a temp folder and uploads only
# that folder, so .env, venv/ or anything else local can never ride along.
#
# Usage:
#   deploy/hf-space/deploy.sh               code + data (run locally; data is gitignored)
#   CODE_ONLY=1 deploy/hf-space/deploy.sh   code only; data already on the Space is kept
#                                           (used by the GitHub Action)
#   SPACE=owner/name                        override the target Space

set -euo pipefail

SPACE="${SPACE:-jeffjeff20120112/partselect-agent}"
CODE_ONLY="${CODE_ONLY:-0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cd "$ROOT"
mkdir -p "$STAGE/deploy/hf-space"

cp deploy/hf-space/Dockerfile "$STAGE/Dockerfile"
cp deploy/hf-space/README.md "$STAGE/README.md"
cp deploy/hf-space/requirements-server.txt "$STAGE/deploy/hf-space/"
cp main.py "$STAGE/"
rsync -a --exclude '__pycache__' --exclude '.DS_Store' backend "$STAGE/"

if [ "$CODE_ONLY" != "1" ]; then
  mkdir -p "$STAGE/data"
  cp data/parts.db data/repair_guides.json data/blogs.json "$STAGE/data/"
  rsync -a --exclude '.DS_Store' data/chroma "$STAGE/data/"
fi

# Guardrails: refuse to upload env files or anything that looks like an OpenAI key
if find "$STAGE" -name '.env*' | grep -q .; then
  echo "Refusing to deploy: .env file in staged files" >&2; exit 1
fi
if grep -rIlE 'sk-(proj-|svcacct-)?[A-Za-z0-9_-]{20,}' "$STAGE"; then
  echo "Refusing to deploy: key-like string in the files above" >&2; exit 1
fi

echo "Uploading to $SPACE ($([ "$CODE_ONLY" = 1 ] && echo 'code only' || echo 'code + data')):"
(cd "$STAGE" && find . -type f -not -path './data/chroma/*' | sort)
[ -d "$STAGE/data/chroma" ] && echo "  + data/chroma/ ($(du -sh "$STAGE/data/chroma" | cut -f1))"

# --delete removes backend files that no longer exist locally; data/ is never touched
hf upload "$SPACE" "$STAGE" . --repo-type space \
  --delete "backend/**" \
  --commit-message "Deploy $(git rev-parse --short HEAD)"
