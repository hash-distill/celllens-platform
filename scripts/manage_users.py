"""Create accounts or reset passwords with a non-echoing local prompt."""

import argparse
import getpass

from backend.app.config import get_settings
from backend.app.core.storage import RunStore
from backend.app.user_data.store import UserDataStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CellLens account administration (run after Alembic migration)"
    )
    parser.add_argument("action", choices=["create", "reset-password"])
    parser.add_argument("username")
    parser.add_argument("--role", choices=["user", "admin"], default="user")
    args = parser.parse_args()
    password = getpass.getpass("Password (at least 12 characters): ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords differ")
    store = UserDataStore(RunStore(get_settings().database_url))
    try:
        if args.action == "create":
            user = store.create_user(args.username, password, args.role)
            print(f"Created {user['role']} account: {user['username']}")
        else:
            store.reset_password(args.username, password)
            print("Password changed and previous sessions revoked.")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
