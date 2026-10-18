#!/usr/bin/env python3
"""
Midcap Swing Scanner - Trading Logic & Gating Audit Runner
Enforces the regression safety net across all 6 critical layers.
Run: python audit.py
Regen Golden: python audit.py --regen-golden
Live Network Smoke: python audit.py --live
"""

import json
import os
import sys
import subprocess


TEST_LAYERS = [
    ("tests/test_rules_golden.py", "RULES GOLDEN"),
    ("tests/test_risk_math.py", "RISK MATH"),
    ("tests/test_notification_gating.py", "NOTIFY GATING"),
    ("tests/test_offset_state.py", "OFFSET STATE"),
    ("tests/test_hermetic_scan.py", "HERMETIC SCAN"),
    ("tests/test_schema_drift.py", "SCHEMA DRIFT"),
    ("tests/test_thresholds_locked.py", "THRESHOLDS LOCKED"),
]


def regenerate_golden():
    print("=" * 60)
    print("REGENERATING GOLDEN RULES SNAPSHOT (tests/GOLDEN_RULES.json)")
    print("=" * 60)

    from tests.test_rules_golden import compute_all_scenarios, GOLDEN_FILE

    golden_data = compute_all_scenarios()
    with open(GOLDEN_FILE, "w", encoding="utf-8") as f:
        json.dump(golden_data, f, indent=2)

    print(f"Successfully generated {GOLDEN_FILE}:")
    print(json.dumps(golden_data, indent=2))
    print("\nGolden rules file locked. Commit this file deliberately.")
    sys.exit(0)


def run_audit(live: bool = False):
    print("=" * 60)
    print("MIDCAP SWING TRADING SCANNER - LOGIC & GATING AUDIT")
    print("=" * 60)

    pytest_args = [sys.executable, "-m", "pytest", "-v"]

    if not live:
        # Exclude tests marked 'live' so default run is 100% offline and finishes in seconds
        pytest_args.extend(["-m", "not live"])

    print(f"Executing: {' '.join(pytest_args)}\n")
    proc = subprocess.run(pytest_args, capture_output=True, text=True)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)

    print("=" * 60)
    print("AUDIT SCOREBOARD")
    print("=" * 60)

    all_passed = True
    output_lines = proc.stdout.splitlines()

    for test_file, label in TEST_LAYERS:
        # Check matching lines for this test layer
        layer_lines = [l for l in output_lines if test_file.replace("/", os.sep) in l or test_file in l]
        has_failed = any("FAILED" in l for l in layer_lines)
        has_passed = any("PASSED" in l for l in layer_lines)

        if has_passed and not has_failed:
            status = "PASS"
        else:
            status = "FAIL"
            all_passed = False

        dots = "." * (25 - len(label))
        print(f"{label} {dots} {status}")

    print("=" * 60)
    if all_passed and proc.returncode == 0:
        print("All trading-logic invariants intact.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("⚠️ A rule moved — see failing test above; do NOT deploy until fixed.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    if "--regen-golden" in sys.argv:
        regenerate_golden()
    else:
        is_live = "--live" in sys.argv
        run_audit(live=is_live)
