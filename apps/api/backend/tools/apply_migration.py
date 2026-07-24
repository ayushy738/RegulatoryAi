import argparse
from pathlib import Path

from backend.core.db import get_engine
from backend.core.migrations import (
    LEGACY_BASELINE_MAX_VERSION,
    MigrationError,
    apply_pending_migrations,
    baseline_legacy_migrations,
    get_migration_status,
    mark_existing_migrations,
)
from backend.core.repository import seed_system_documents

DEFAULT_MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"
BASELINE_ACKNOWLEDGEMENT = "existing-schema-verified"
MARK_EXISTING_ACKNOWLEDGEMENT = "manually-applied-schema-verified"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply ordered, checksummed PostgreSQL migrations."
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIRECTORY,
        help="Directory containing versioned SQL migrations.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    apply_command = commands.add_parser("apply", help="Apply all pending migrations.")
    apply_command.add_argument(
        "--through",
        help="Stop after this migration version.",
    )
    apply_command.add_argument(
        "--seed-docs",
        action="store_true",
        help="Preserve the legacy post-migration system-document seed.",
    )

    status_command = commands.add_parser(
        "status",
        help="Verify migration history and list pending migrations.",
    )
    status_command.add_argument(
        "--through",
        help="Limit the pending list to this migration version.",
    )

    baseline_command = commands.add_parser(
        "baseline",
        help="Record verified legacy migrations without executing them.",
    )
    baseline_command.add_argument(
        "--through",
        required=True,
        help=f"Legacy version to record, at most {LEGACY_BASELINE_MAX_VERSION}.",
    )
    baseline_command.add_argument(
        "--acknowledge",
        required=True,
        help=(
            "Required safety acknowledgement. Pass "
            f"{BASELINE_ACKNOWLEDGEMENT!r} only after verifying the live schema."
        ),
    )
    mark_existing_command = commands.add_parser(
        "mark-existing",
        help=(
            "Verify supported manually applied migrations and record them without "
            "executing migration SQL."
        ),
    )
    mark_existing_command.add_argument(
        "--through",
        required=True,
        help="Last contiguous manually applied migration to verify and record.",
    )
    mark_existing_command.add_argument(
        "--acknowledge",
        required=True,
        help=(
            "Required safety acknowledgement. Pass "
            f"{MARK_EXISTING_ACKNOWLEDGEMENT!r} only for manually applied migrations."
        ),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    engine = get_engine()

    try:
        if args.command == "apply":
            applied = apply_pending_migrations(
                engine,
                args.directory,
                through=args.through,
            )
            if not applied:
                print("No pending migrations.")
            for migration in applied:
                print(
                    f"Applied {migration.version} {migration.filename} sha256:{migration.checksum}"
                )
            if args.seed_docs:
                seed_system_documents()
                print("Seeded system documents.")
            return

        if args.command == "status":
            status = get_migration_status(
                engine,
                args.directory,
                through=args.through,
            )
            print(f"Applied migrations: {len(status.applied)}")
            for migration in status.applied:
                print(
                    f"  applied {migration.version} {migration.filename} "
                    f"sha256:{migration.checksum}"
                )
            print(f"Pending migrations: {len(status.pending)}")
            for migration in status.pending:
                print(
                    f"  pending {migration.version} {migration.filename} "
                    f"sha256:{migration.checksum}"
                )
            return

        if args.command == "mark-existing":
            if args.acknowledge != MARK_EXISTING_ACKNOWLEDGEMENT:
                raise MigrationError(
                    "Refusing mark-existing: invalid safety acknowledgement"
                )
            marked = mark_existing_migrations(
                engine,
                args.directory,
                through=args.through,
            )
            if not marked:
                print("No missing migrations to mark.")
                return
            for migration in marked:
                print(
                    f"Marked existing {migration.version} {migration.filename} "
                    f"sha256:{migration.checksum}"
                )
            print("No migration SQL was executed.")
            return

        if args.acknowledge != BASELINE_ACKNOWLEDGEMENT:
            raise MigrationError("Refusing legacy baseline: invalid safety acknowledgement")
        baselined = baseline_legacy_migrations(
            engine,
            args.directory,
            through=args.through,
        )
        print(
            f"Baselined {len(baselined)} verified legacy migrations through "
            f"{args.through}. No migration SQL was executed."
        )
    except MigrationError as exc:
        raise SystemExit(f"Migration refused: {exc}") from exc


if __name__ == "__main__":
    main()
