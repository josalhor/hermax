from __future__ import annotations

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
scripts = sorted(
    p for p in root.glob("*.py") if p.name not in {Path(__file__).name, "wifi_lib.py"}
)

failures = 0
for script in scripts:
    print(f"== {script.name} ==")
    result = subprocess.run([sys.executable, str(script)], check=False)
    if result.returncode != 0:
        failures += 1
        print(f"FAILED: {script.name} (exit {result.returncode})")
    print()

if failures:
    print(f"{failures} example(s) failed")
    raise SystemExit(1)

print("All examples passed")
