"""Dump the platform backend's OpenAPI schema as JSON.

Usage (from saas-platform/platform-backend/):

    uv run python scripts/export_openapi.py [output_path]

The default output path is the platform frontend's checked-in schema,
which `bun run generate:api-types` turns into src/lib/api.generated.ts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from main import app

DEFAULT_OUTPUT = Path(__file__).parents[2] / "platform-frontend" / "openapi.json"


def main() -> None:
    """Write the OpenAPI schema to the given (or default) path."""
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {output}")  # noqa: T201


if __name__ == "__main__":
    main()
