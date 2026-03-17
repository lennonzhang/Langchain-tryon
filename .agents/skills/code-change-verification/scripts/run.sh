#!/usr/bin/env bash
# Fail fast on any error or undefined variable.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v git >/dev/null 2>&1; then
  REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || true)"
fi
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../../../.." && pwd)}"

cd "${REPO_ROOT}"

echo "Running backend tests..."
python -m unittest discover -s tests -v

echo "Running frontend tests..."
cd frontend-react
pnpm test

echo "Running frontend e2e tests..."
pnpm test:e2e

echo "Running frontend build..."
pnpm run build

echo "code-change-verification: all commands passed."
