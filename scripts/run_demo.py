from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.allocation.section_allocator import allocate_sections
from backend.database.db import create_database_engine, create_schema, session_scope
from backend.exports.data_export import export_database_snapshot
from backend.database.models import Program
from backend.forecasting.demand_forecast import run_forecast
from backend.generators.master_generator import (
    DEFAULT_SEED,
    generate_dataset,
    persist_dataset,
)
from backend.validation.runner import run_validation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run starter data generation, forecasting, allocation, and validation."
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
            program_count = session.scalar(select(func.count()).select_from(Program)) or 0
            if program_count == 0:
                dataset = generate_dataset("starter", DEFAULT_SEED)
                persist_dataset(session, dataset)

            forecast = run_forecast(session, term_code="2027-Fall")
            allocation = allocate_sections(
                session,
                {
                    item["course_id"]: item["predicted_enrollment"]
                    for item in forecast["results"]
                },
                term_code="2027-Fall",
            )
            validation = run_validation(session)
            summary = {
                "forecast_run_id": forecast["run_id"],
                "forecast_algorithm": forecast["algorithm"],
                "forecast_metrics": forecast["metrics"],
                "forecast_course_count": len(forecast["results"]),
                "allocation_metrics": allocation.metrics,
                "unmet_demand": allocation.unmet_demand,
                "validation_run_id": validation["run_id"],
                "validation_status": validation["validation_status"],
                "validation_checks": validation["total_checks"],
                "validation_failures": validation["failed_checks"],
                "validation_warnings": validation["warning_count"],
            }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with session_scope(engine) as session:
            manifest = export_database_snapshot(session, args.output_dir)
        summary["exported_entity_count"] = len(manifest["entities"])
        summary["export_directory"] = str(args.output_dir.resolve())
        report_path = args.output_dir / "workflow_summary.json"
        report_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        if summary["validation_failures"]:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
