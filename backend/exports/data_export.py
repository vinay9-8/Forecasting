from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import Base, ValidationRun


def _serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    return value


def _canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_serializable)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("SQL seed values must be finite.")
        return str(value)
    if isinstance(value, datetime):
        value = value.strftime("%Y-%m-%d %H:%M:%S.%f")
    elif isinstance(value, (date, time)):
        value = value.isoformat()
    elif isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def export_database_snapshot(session: Session, output_dir: Path) -> dict[str, Any]:
    """Write per-table CSV/JSON, a separate ground-truth file, SQL inserts, and checksums."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"entities": {}, "generated_at": datetime.now().astimezone().isoformat()}
    seed_lines = [
        "-- Synthetic academic planning database snapshot.",
        "-- Apply schema.sql to an empty database before executing this file.",
        "SET FOREIGN_KEY_CHECKS=0;",
    ]
    models_by_table = {
        mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers
    }

    for table in Base.metadata.sorted_tables:
        model = models_by_table[table.name]
        rows = list(session.scalars(select(model).order_by(model.id)))
        serialized = [
            {column.name: _serializable(getattr(row, column.name)) for column in table.columns}
            for row in rows
        ]
        csv_path = output_dir / f"{table.name}.csv"
        json_path = output_dir / f"{table.name}.json"
        columns = [column.name for column in table.columns]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(serialized)
        json_path.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        checksum = hashlib.sha256(
            "\n".join(_canonical(row) for row in serialized).encode("utf-8")
        ).hexdigest()
        manifest["entities"][table.name] = {
            "row_count": len(serialized),
            "sha256": checksum,
            "csv_file": csv_path.name,
            "json_file": json_path.name,
        }

        if serialized:
            column_names = ", ".join(f"`{name}`" for name in columns)
            for row in rows:
                values = ", ".join(
                    _sql_literal(getattr(row, column.name)) for column in table.columns
                )
                seed_lines.append(
                    f"INSERT INTO `{table.name}` ({column_names}) VALUES ({values});"
                )

    validation = session.scalar(
        select(ValidationRun).order_by(ValidationRun.created_at.desc()).limit(1)
    )
    truth_rows = (
        validation.details.get("ground_truth", []) if validation else []
    )
    truth_columns = [
        "id", "entity_id", "issue_type", "description", "severity", "ground_truth_label"
    ]
    with (output_dir / "ground_truth.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=truth_columns)
        writer.writeheader()
        writer.writerows(truth_rows)
    (output_dir / "ground_truth.json").write_text(
        json.dumps(truth_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    truth_checksum = hashlib.sha256(
        "\n".join(_canonical(row) for row in truth_rows).encode("utf-8")
    ).hexdigest()
    manifest["ground_truth"] = {
        "row_count": len(truth_rows),
        "sha256": truth_checksum,
        "csv_file": "ground_truth.csv",
        "json_file": "ground_truth.json",
    }

    seed_lines.extend(("SET FOREIGN_KEY_CHECKS=1;", ""))
    (output_dir / "seed.sql").write_text("\n".join(seed_lines), encoding="utf-8")
    manifest["sql_seed"] = "seed.sql"
    (output_dir / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
