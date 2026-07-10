#!/usr/bin/env python3
"""Generate a static OpenAPI spec from the Freedom FastAPI application.

Usage:
    python scripts/generate_openapi.py

Output:
    docs/openapi.json
"""

from __future__ import annotations

import json
import os
import sys

# Make the backend app importable regardless of where this script is run from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "docs", "openapi.json")

sys.path.insert(0, BACKEND_DIR)

from app.main import app


def generate() -> None:
    spec = app.openapi()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    info = spec.get("info", {})
    print(f"Generated OpenAPI spec at {OUTPUT_PATH}")
    print(f"  Title:   {info.get('title')}")
    print(f"  Version: {info.get('version')}")
    print(f"  Paths:   {len(spec.get('paths', {}))}")
    print(f"  Schemas: {len(spec.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    generate()
