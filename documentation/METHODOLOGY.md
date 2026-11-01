# Forecasting, allocation, and validation methodology

## Forecasting

Registration records are grouped by course and term. `registered` and
`completed` records form the historical enrollment target; `interested` and
`waitlisted` records form the known interest signal. Withdrawn records are
excluded. `ground_truth.csv` is not loaded by the forecaster and is never a
model feature or target.

For each historical course/term observation, the feature vector contains:

- Previous-semester and trailing-three-term actual enrollment.
- Course interest known in that term (interested and waitlisted only).
- Course popularity, program-plan count, course credits, required/elective flag.
- Calendar year component and season.

The starter/full generators supply four fixed terms. Training data is split
80/20 using `train_test_split` with a fixed seed. A 160-tree
`RandomForestRegressor` and a trailing-three-term moving-average baseline are
evaluated on the same held-out observations. The Random Forest is selected only
when its MAE is no worse than the baseline MAE; otherwise the baseline is used.
The ensemble standard deviation is shown as a prediction spread, not a
calibrated confidence interval. Negative estimates are clipped to zero.

Metrics are MAE, RMSE, MAPE, and R². MAPE excludes zero-actual rows from its
denominator and returns zero when every held-out actual is zero. R² returns zero
when fewer than two test observations are available. Each run and course result
is append-only and stores the seed, selected algorithm, metrics, and feature
explanation.

Section recommendations use `ceil(prediction / course.max_section_size)`.
Uncertainty is the standard deviation of tree-level predictions.
High/medium/low demand thresholds are respectively at least 70%, at least 30%,
or below 30% of the course's maximum section size.

## Allocation

Demand is rounded up to whole students. Courses are scheduled in descending
demand order into standard weekday time slots. Section capacity is the lesser
of room capacity and the course section limit. Room/time conflicts are checked
before every placement; existing sections and their planned enrollment are
subtracted before additional sections are proposed.

Faculty candidates must be active for the requested term, have a skill record
for the section's course, have an availability interval covering the entire
meeting, not be on leave during it, have no timetable overlap, and remain below
their weekly workload ceiling. The scoring weights skill 35%, availability
15%, experience 20%, and remaining workload balance 30%. When a feasible
candidate does not exist, the section stays unassigned and an exception is
created. Unplaced students are returned as unmet demand.

Allocation stages all new records in one transaction. Historical forecasts,
sections, assignments, validation runs, and audit events are retained.

## Validation and ground truth

Validation checks required dataset presence, primary/foreign-key consistency,
ID patterns, lifecycle/effective dates, prerequisites, faculty workload and
schedule, room/course capacity and schedule conflicts, faculty skill and
availability, and section assignment/enrollment. Failed checks are retained in
validation history; issues create exception records.

The five required negative cases are fixture objects created separately from
baseline rows. Scenario detectors verify an out-of-skill assignment, excess
workload, insufficient capacity, prerequisite term inversion, and duplicate
section assignment. The scenarios and labels are exported to
`ground_truth.csv`/`.json`; they do not corrupt valid records. Synthetic data is
the only data source, so no external dataset provenance or license applies.