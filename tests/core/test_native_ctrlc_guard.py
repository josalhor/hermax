from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(os.name == "nt", reason="the native guard is POSIX-only")
def test_native_ctrlc_guard_escapes_and_restores_previous_handler(tmp_path: Path):
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("C++ compiler is unavailable")

    root = Path(__file__).resolve().parents[2]
    source = Path(__file__).with_name("ctrlc_guard_probe.cpp")
    executable = tmp_path / "ctrlc_guard_probe"
    compile_result = subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-I",
            str(root / "bindings" / "common"),
            str(source),
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    run_result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert run_result.returncode == 0, run_result.stderr
