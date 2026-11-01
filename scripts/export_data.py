from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.database.db import create_database_engine, create_schema, session_scope
from backend.exports.data_export import export_database_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export database entities as CSV, JSON, SQL seed, and checksums."
    )
    parser.add_argument("--database-url", help="Override DATABASE_URL for this run.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "submission",
    )
    args = parser.parse_args()
    engine = create_database_engine(args.database_url)
    try:
        create_schema(engine)
        with session_scope(engine) as session:
            manifest = export_database_snapshot(session, args.output_dir)
        print(json.dumps(manifest, indent=2, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
