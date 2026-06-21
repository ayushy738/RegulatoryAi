import argparse
from pathlib import Path

from sqlalchemy import text

from backend.core.db import session_scope
from backend.core.repository import seed_system_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a SQL migration file.")
    parser.add_argument("migration", help="Path to a SQL migration file.")
    parser.add_argument("--seed-docs", action="store_true", help="Seed app_documents after SQL.")
    args = parser.parse_args()

    sql = Path(args.migration).read_text(encoding="utf-8")
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    with session_scope() as session:
        for statement in statements:
            session.execute(text(statement))

    if args.seed_docs:
        seed_system_documents()

    print(f"Applied {args.migration} ({len(statements)} statements).")


if __name__ == "__main__":
    main()
