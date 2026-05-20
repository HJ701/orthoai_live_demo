#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def metric(payload: Dict[str, Any], split: str, key: str) -> Any:
    return (payload.get(f"{split}_metrics_best_model") or {}).get(key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate Exp 1.7 OrthoPatientFusion final_results.json files.")
    parser.add_argument("run_root", type=str, help="Run root, e.g. models/exp1_7_orthopatientfusion_runs/<run_tag>")
    parser.add_argument("--output", type=str, default="", help="Optional output CSV path.")
    args = parser.parse_args()

    run_root = Path(args.run_root)
    rows: List[Dict[str, Any]] = []
    for path in sorted(run_root.glob("*/final_results.json")):
        with path.open() as f:
            payload = json.load(f)
        rows.append(
            {
                "experiment": payload.get("fusion_experiment") or path.parent.name,
                "test_macro_f1": metric(payload, "test", "macro_f1"),
                "val_macro_f1": metric(payload, "val", "macro_f1"),
                "test_macro_auc": metric(payload, "test", "macro_auc"),
                "val_macro_auc": metric(payload, "val", "macro_auc"),
                "test_accuracy": metric(payload, "test", "accuracy"),
                "val_accuracy": metric(payload, "val", "accuracy"),
                "best_checkpoint": payload.get("best_checkpoint"),
                "deliverable_checkpoint": payload.get("deliverable_checkpoint"),
                "final_results": str(path),
            }
        )

    rows.sort(key=lambda r: (r["test_macro_f1"] is not None, r["test_macro_f1"] or -1), reverse=True)
    if not rows:
        raise SystemExit(f"No final_results.json files found under {run_root}")

    output = Path(args.output) if args.output else run_root / "exp1_7_summary.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"[done] Wrote {output}")
    print("[best]", rows[0])


if __name__ == "__main__":
    main()
