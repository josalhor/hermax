#!/usr/bin/env python3
"""Capture transcript-style outputs for runnable documentation examples.

Each output file contains a single console-style transcript:

    $ python examples/<path>/<file>.py
    <stdout...>

This keeps the Sphinx docs maintainable by including generated output files
instead of hand-copying example output blocks.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def capture_example(repo_root: Path, example_path: Path, out_dir: Path) -> None:
    rel = example_path.relative_to(repo_root)
    stem = example_path.stem
    out_path = out_dir / f"{stem}.txt"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    proc = subprocess.run(
        [sys.executable, str(example_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    header = f"$ python {rel.as_posix()}\n"
    body = proc.stdout
    if proc.returncode != 0:
        body = body + ("\n" if body and not body.endswith("\n") else "")
        body += f"[exit code: {proc.returncode}]\n"
        if proc.stderr:
            body += proc.stderr
    if body and not body.endswith("\n"):
        body += "\n"

    out_path.write_text(header + body, encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError(f"Example failed: {rel} (exit {proc.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture docs outputs for runnable examples")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to auto-detected project root).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "_generated" / "example_outputs",
        help="Output directory for transcript files.",
    )
    parser.add_argument(
        "--pattern",
        default="*.py",
        help="Glob pattern under examples/model and examples/encoder (default: *.py).",
    )
    parser.add_argument(
        "--model-only",
        action="store_true",
        help="Only capture examples/model/*.py (skip top-level and encoder examples).",
    )
    parser.add_argument(
        "--encoder-only",
        action="store_true",
        help="Only capture examples/encoder/*.py.",
    )
    parser.add_argument(
        "--include-cvrp-flat",
        action="store_true",
        help="Also capture examples/cvrp_flat.py (skipped by default to avoid churn in rendered assets).",
    )
    parser.add_argument(
        "--include-cvrp",
        action="store_true",
        help="Also capture examples/cvrp.py (skipped by default because symmetric optimal routes create output churn).",
    )
    args = parser.parse_args()
    if args.model_only and args.encoder_only:
        parser.error("--model-only and --encoder-only cannot be used together")

    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir.resolve()
    examples_dir = repo_root / "examples" / "model"
    encoder_dir = repo_root / "examples" / "encoder"
    out_dir.mkdir(parents=True, exist_ok=True)

    model_paths = sorted(examples_dir.glob(args.pattern)) if not args.encoder_only else []
    encoder_paths = sorted(encoder_dir.glob(args.pattern)) if not args.model_only else []
    if not model_paths and not encoder_paths:
        raise SystemExit(f"No examples matched under {examples_dir} with pattern {args.pattern!r}")

    top_level_paths: list[Path] = []
    if not args.model_only and not args.encoder_only:
        for rel in [
            "examples/quickstart_model.py",
            "examples/incremental_assumptions.py",
            "examples/non_incremental_rc2_reentrant.py",
            "examples/evalmaxsat_incr_relaxation.py",
            "examples/load_wcnf_formula.py",
            "examples/optilog_formula_compat.py",
            "examples/portfolio_mixed.py",
            "examples/portfolio_presets.py",
            "examples/wifi_minimal.py",
        ]:
            p = repo_root / rel
            if p.exists():
                top_level_paths.append(p)
        if args.include_cvrp_flat:
            p = repo_root / "examples/cvrp_flat.py"
            if p.exists():
                top_level_paths.append(p)
        if args.include_cvrp:
            p = repo_root / "examples/cvrp.py"
            if p.exists():
                top_level_paths.append(p)

    example_paths = model_paths + encoder_paths + top_level_paths

    for path in example_paths:
        capture_example(repo_root, path.resolve(), out_dir)

    print(f"captured={len(example_paths)} outputs -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
