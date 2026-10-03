"""Writes the OpenAPI spec (docs/openapi.yaml) for `make gen-api` without starting a server."""

import os
import sys
from pathlib import Path

import yaml


def main() -> None:
    # The spec only depends on routes and schemas; these placeholders satisfy required settings.
    for key, value in {
        "DATABASE_URL": "postgresql+asyncpg://spec:spec@localhost/spec",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "spec-only",
        "ENCRYPTION_KEY": "A" * 43 + "=",
        "ENGINE_API_TOKEN": "spec-only",
        "ENVIRONMENT": "development",
        "API_DOCS_ENABLED": "true",
    }.items():
        os.environ.setdefault(key, value)
    from app.main import create_app

    spec = create_app().openapi()
    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[3] / "docs" / "openapi.yaml"
    )
    target.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
