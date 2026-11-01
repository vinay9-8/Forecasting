from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.database.db import create_database_engine, create_schema, session_scope
from backend.database.models import Program
from backend.generators.master_generator import (
    DEFAULT_SEED,
    generate_dataset,
    persist_dataset,
)
from backend.validation.runner import run_validation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run database integrity validation.")
    parser.add_argument("--database-url", help="Override DATABASE_URL for this run.")
    parser.add_argument(
        "--seed-starter-if-empty",
        action="store_true",
        help="Create the starter dataset only when the selected database has no programs.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    engine = create_database_engine(args.database_url)
    try:
        create_schema(engine)
        with session_scope(engine) as session:
            program_count = session.scalar(select(func.count()).select_from(Program)) or 0
            if program_count == 0 and args.seed_starter_if_empty:
                persist_dataset(
                    session,
                    generate_dataset(mode="starter", seed=args.seed),
                )
            report = run_validation(session)
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["failed_checks"]:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()