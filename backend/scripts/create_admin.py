"""Bootstraps the first admin/reviewer user. Same reasoning as
create_organization.py: no API endpoint for this on purpose.

Usage:
    python scripts/create_admin.py you@example.com "Full Name" --role admin
"""
import argparse
import asyncio
import getpass
import sys

sys.path.insert(0, ".")

from app.core.auth import hash_password
from app.database import SessionLocal
from app.models import Admin


async def main(email: str, full_name: str, role: str, password: str):
    async with SessionLocal() as db:
        admin = Admin(email=email, full_name=full_name, role=role, password_hash=hash_password(password))
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    print(f"Admin created: {admin.id} ({admin.email}, role={admin.role})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("full_name")
    parser.add_argument("--role", default="reviewer", choices=["reviewer", "compliance_officer", "admin"])
    args = parser.parse_args()
    pw = getpass.getpass("Password: ")
    asyncio.run(main(args.email, args.full_name, args.role, pw))
