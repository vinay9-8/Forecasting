from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.database.db import create_database_engine, create_schema, session_scope
from backend.generators.master_generator import (
    DEFAULT_SEED,
    export_dataset,
    generate_dataset,
    persist_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic course demand data."
    )
    parser.add_argument(
        "--mode",
        choices=("starter", "full"),
        default="starter",
        help="Dataset size (default: starter).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for CSV, JSON, and manifest files (defaults to data/generated/<mode>).",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Insert rows into DATABASE_URL; existing data is not overwritten.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or REPOSITORY_ROOT / "data" / "generated" / args.mode
    dataset = generate_dataset(mode=args.mode, seed=args.seed)
    manifest = export_dataset(dataset, output_dir)

    if args.persist:
        engine = create_database_engine()
        try:
            create_schema(engine)
            with session_scope(engine) as session:
                persist_dataset(session, dataset)
        finally:
            engine.dispose()

    print(
        json.dumps(
            {
                "mode": args.mode,
                "seed": args.seed,
                "output_dir": str(output_dir.resolve()),
                "database_persisted": args.persist,
                "entity_counts": {
                    name: details["row_count"]
                    for name, details in manifest["entities"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
