"""Bootstraps an API-key-holding Organization (an LMS tenant, e.g. Savefast).

There's deliberately no API endpoint for this — creating an Organization is
an operator action (issuing a new client their credentials), not something
reachable over the API itself. The raw key is only ever shown here, once;
only its hash is stored.

Usage:
    python scripts/create_organization.py "Savefast LMS" --origin https://learn.savefast.example.com
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from app.core.auth import generate_api_key, hash_api_key  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Organization  # noqa: E402


async def main(name: str, origin: str | None, webhook_url: str | None):
    raw_key = generate_api_key(name)
    async with SessionLocal() as db:
        org = Organization(
            name=name,
            api_key_hash=hash_api_key(raw_key),
            allowed_origin=origin,
            webhook_url=webhook_url,
        )
        db.add(org)
        await db.commit()
        await db.refresh(org)

    print(f"Organization created: {org.id} ({org.name})")
    print(f"API key (shown once, store it securely): {raw_key}")
    if origin:
        print(f"Remember to add this origin to CORS_ALLOWED_ORIGINS: {origin}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--origin", default=None, help="Browser origin to allow via CORS")
    parser.add_argument("--webhook-url", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.name, args.origin, args.webhook_url))
