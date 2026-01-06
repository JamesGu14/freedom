#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose not available"
  exit 1
fi

if [ ! -f .env ]; then
  echo "No .env found, using env from shell if set."
fi

docker compose up -d --build
