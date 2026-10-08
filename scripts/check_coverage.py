"""Enforce distinct line and branch thresholds; do not hide untested native code."""

import json
from pathlib import Path


def verify(path: Path) -> None:
    """Require all application lines, 90% branches and every grading/scoring branch."""
    report = json.loads(path.read_text())
    totals = report["totals"]
    if totals["missing_lines"]:
        raise SystemExit("Application line coverage must be 100%")
    if totals["covered_branches"] < 0.9 * totals["num_branches"]:
        raise SystemExit("Application branch coverage must be at least 90%")
    for name in (
        "quiz_app/grading.py",
        "quiz_app/jev.py",
        "quiz_app/normalization.py",
        "quiz_app/numeric.py",
        "quiz_app/scoring.py",
    ):
        if report["files"][name]["summary"]["missing_branches"]:
            raise SystemExit(f"{name}: branch coverage must be 100%")
    print("Coverage gates passed: all lines, ≥90% branches, full correction/scoring branches.")


if __name__ == "__main__":
    verify(Path("coverage.json"))
