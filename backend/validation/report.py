from __future__ import annotations

from typing import Any


def build_report(checks: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
    failed_checks = sum(not check["passed"] for check in checks)
    warning_count = sum(
        issue["severity"] in {"medium", "low"}
        and issue["ground_truth_label"] == "false"
        for issue in issues
    )
    status = (
        "failed"
        if failed_checks
        else "warning"
        if warning_count
        else "passed"
    )
    return {
        "total_checks": len(checks),
        "passed_checks": len(checks) - failed_checks,
        "failed_checks": failed_checks,
        "warning_count": warning_count,
        "validation_status": status,
        "checks": checks,
        "issues": issues,
    }