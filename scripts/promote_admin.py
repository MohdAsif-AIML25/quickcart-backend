"""Give an existing user the admin role (development only).

Usage:
    python -m scripts.promote_admin you@example.com

There is no API endpoint for this on purpose: an endpoint that creates admins
is an attack target. In production the first admin is created with SQL on the
server (see docs/aws-deployment.md).
"""

import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.models import User, UserRole


def promote(email: str) -> int:
    if get_settings().environment == "production":
        print("Refusing to run with ENVIRONMENT=production. Use SQL on the server instead.")
        return 1

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            print(f"No user with email '{email}'. Sign up first, then run this again.")
            return 1
        user.role = UserRole.ADMIN.value
        db.commit()
        print(f"{user.email} is now an admin. Log out and log in again (or reload the page).")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.promote_admin you@example.com")
        raise SystemExit(2)
    raise SystemExit(promote(sys.argv[1]))
