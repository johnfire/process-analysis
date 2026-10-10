"""Server-side account commands, run inside the web container:

    docker compose -f docker-compose.prod.yml exec web python -m web.manage create-user you@example.com
    docker compose -f docker-compose.prod.yml exec web python -m web.manage set-password you@example.com
    docker compose -f docker-compose.prod.yml exec web python -m web.manage import-seed

The first administrator can only be created here; everyone after that arrives by invitation.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from web import clock
from web.audit_trail import record_audit
from web.database import create_database_engine
from web.email_addresses import is_plausible_email
from web.login_throttle import email_key
from web.passwords import hash_password, password_problem
from web.seed_import import import_seed_processes
from web.session_store import end_all_sessions
from web.settings import settings_from_environment
from web.user_store import change_password, create_user, find_user_by_email

OPERATOR_LABEL = "operator-cli"


def read_new_password(email: str) -> str:
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat: "):
        sys.exit("The two entries differ.")
    problem = password_problem(password, email)
    if problem:
        sys.exit(problem)
    return password


def create_administrator(email: str, is_admin: bool) -> None:
    address = email_key(email)
    if not is_plausible_email(address):
        sys.exit(f"{email!r} is not an email address. Nothing was created.")
    engine = create_database_engine(settings_from_environment().database_url)
    password_hash = hash_password(read_new_password(address))
    with engine.begin() as connection:
        user_id = create_user(connection, address, password_hash, is_admin=is_admin)
        if user_id is None:
            sys.exit(f"{address} already has an account.")
        record_audit(connection, None, OPERATOR_LABEL, "create_user", "success", "local", address)
    print(f"Created {'administrator' if is_admin else 'user'} {address}.")


def reset_password(email: str) -> None:
    engine = create_database_engine(settings_from_environment().database_url)
    address = email_key(email)
    with engine.begin() as connection:
        user = find_user_by_email(connection, address)
        if user is None:
            sys.exit(f"No account for {address}.")
        change_password(connection, user.id, hash_password(read_new_password(address)), clock.utcnow())
        end_all_sessions(connection, user.id)
        record_audit(connection, None, OPERATOR_LABEL, "set_password", "success", "local", address)
    print(f"Password changed for {address}; all sessions ended.")


def import_seed() -> None:
    engine = create_database_engine(settings_from_environment().database_url)
    report = import_seed_processes(engine)
    print(f"Imported or confirmed: {', '.join(report.imported) or 'none'}.")
    if report.failed:
        sys.exit(f"Failed: {', '.join(report.failed)} (see the log above).")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m web.manage")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="create an account (administrator by default)")
    create.add_argument("email")
    create.add_argument("--not-admin", action="store_true")
    commands.add_parser("set-password", help="set a new password and end all sessions").add_argument("email")
    commands.add_parser("import-seed", help="load the synthetic corpus (safe to repeat)")
    arguments = parser.parse_args()
    if arguments.command == "import-seed":
        import_seed()
    elif arguments.command == "create-user":
        create_administrator(arguments.email, is_admin=not arguments.not_admin)
    else:
        reset_password(arguments.email)


if __name__ == "__main__":
    main()
