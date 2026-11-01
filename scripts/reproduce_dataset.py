from __future__ import annotations

import argparse
import gc
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.generators.master_generator import (
    DEFAULT_SEED,
    _canonical_row,
    generate_dataset,
)
from backend.validation.anomaly_scenarios import (
    build_anomaly_scenarios,
    ground_truth_rows,
)


def signature(mode: str, seed: int) -> dict[str, dict[str, str | int]]:
    dataset = generate_dataset(mode=mode, seed=seed)
    result: dict[str, dict[str, str | int]] = {}
    for table, rows in dataset.items():
        digest = hashlib.sha256()
        for row in rows:
            digest.update(_canonical_row(row).encode("utf-8"))
            digest.update(b"\n")
        result[table] = {"row_count": len(rows), "sha256": digest.hexdigest()}
    scenarios = build_anomaly_scenarios(
        courses=dataset["courses"],
        faculty=dataset["faculty"],
        faculty_skills=dataset["faculty_skills"],
        rooms=dataset["rooms"],
        sections=dataset["sections"],
        prerequisites=dataset["prerequisites"],
    )
    truth = ground_truth_rows(scenarios)
    truth_digest = hashlib.sha256()
    for row in truth:
        truth_digest.update(_canonical_row(row).encode("utf-8"))
        truth_digest.update(b"\n")
    result["ground_truth"] = {
        "row_count": len(truth),
        "sha256": truth_digest.hexdigest(),
    }
    del dataset
    gc.collect()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a dataset twice and compare stable entity checksums."
    )
    parser.add_argument("--mode", choices=("starter", "full"), default="starter")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    first = signature(args.mode, args.seed)
    second = signature(args.mode, args.seed)
    matched = first == second
    print(
        json.dumps(
            {
                "mode": args.mode,
                "seed": args.seed,
                "reproducible": matched,
                "entities": first,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not matched:
        raise SystemExit("Generated datasets differ for the same mode and seed.")


if __name__ == "__main__":
    main()
