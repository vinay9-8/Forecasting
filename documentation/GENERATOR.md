# Synthetic data generator

The default seed is `20261022`. The generator uses Python's isolated
`random.Random(seed)` instance and fixed reference timestamps, so it does not
depend on global random state or the time at which it runs. Child rows are
created only after their parent identifiers exist.

```powershell
python scripts/generate_data.py --mode starter --seed 20261022
python scripts/generate_data.py --mode full --seed 20261022 --output-dir data/generated/full
python scripts/reproduce_dataset.py --mode starter --seed 20261022
```

Each generation writes one CSV and one JSON file per core entity,
`ground_truth.csv`, `ground_truth.json`, and `source_manifest.json`. The
manifest records row counts and a SHA-256 checksum of each entity's canonical
rows and the separate labelled anomaly fixtures. A single dataset-generation
audit event records the mode, seed, and row counts.

To insert records into the configured database, add `--persist`. Insertion is
transactional and intentionally fails on existing IDs rather than replacing
historical rows. Use a fresh database for a clean repeat run.

The full mode creates the required 100 programs, 1,000 courses, 500 faculty,
and 20,000 student plans. It also generates course prerequisites, historical and
current registration interests, faculty skills and availability (including
leave), rooms with varied capacity, and scheduled sections with baseline
workload assignments when a compatible faculty member is available.

Five negative cases cover faculty skill mismatch, exceeded faculty workload,
insufficient room capacity, prerequisite term ordering, and duplicate section
assignment. They are built as separate fixtures and never mutate generated
baseline rows. Validation writes detected examples to exception history with
`ground_truth_label=true`.
