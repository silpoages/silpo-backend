"""Print the coverage.py totals as a Markdown table for the CI job summary."""

import json
from pathlib import Path


def main() -> None:
    totals = json.loads(Path("coverage/coverage.json").read_text(encoding="utf-8"))["totals"]
    lines = totals["covered_lines"], totals["num_statements"]
    branches = totals["covered_branches"], totals["num_branches"]
    metrics = {
        "Lines": lines,
        "Branches": branches,
        "Combined (coverage.py)": (lines[0] + branches[0], lines[1] + branches[1]),
    }

    print("## Backend test coverage\n")
    print("| Metric | Covered | Total | Coverage |")
    print("| --- | ---: | ---: | ---: |")
    for name, (covered, total) in metrics.items():
        percentage = f"{covered / total:.2%}" if total else "N/A"
        print(f"| {name} | {covered} | {total} | {percentage} |")
    print("\nScope: all Python application modules in app/, including untested files.")
    print("Coverage describes exercised code, not the test pass rate.")
    print("If tests failed, these figures are partial; check the Test job result.")


if __name__ == "__main__":
    main()
