from __future__ import annotations

import importlib
import io
import os
import pickle
import signal
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


_HEADER_STRUCT = struct.Struct(">Q")


def _dumps_frame(obj: Any) -> bytes:
    payload = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    return _HEADER_STRUCT.pack(len(payload)) + payload


def _loads_frame_from_bytes(data: bytes) -> Any:
    bio = io.BytesIO(data)
    header = bio.read(_HEADER_STRUCT.size)
    if len(header) != _HEADER_STRUCT.size:
        raise ValueError("Missing frame header")
    (nbytes,) = _HEADER_STRUCT.unpack(header)
    payload = bio.read(nbytes)
    if len(payload) != nbytes:
        raise ValueError("Truncated frame payload")
    return pickle.loads(payload)


@dataclass
class OneShotRunResult:
    ok: bool
    response: Optional[Dict[str, Any]]
    exit_code: Optional[int]
    timed_out: bool
    interrupted: bool
    killed: bool
    elapsed_s: float
    stdout_raw: bytes
    stderr_raw: bytes
    protocol_error: Optional[str] = None


def _worker_cmd() -> list[str]:
    return [sys.executable, "-m", "hermax.internal.solver_worker_main"]


def _popen_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _interrupt_process(proc: subprocess.Popen[bytes]) -> bool:
    try:
        if os.name == "nt":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                return True
            except Exception:
                proc.terminate()
                return True
        os.killpg(proc.pid, signal.SIGINT)
        return True
    except Exception:
        return False


def _kill_process(proc: subprocess.Popen[bytes]) -> bool:
    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        return True
    except Exception:
        try:
            proc.kill()
            return True
        except Exception:
            return False


def run_oneshot_worker(
    request: Dict[str, Any],
    timeout_s: float,
    grace_s: float = 1.0,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> OneShotRunResult:
    t0 = time.monotonic()
    req_bytes = _dumps_frame(request)
    proc = subprocess.Popen(_worker_cmd(), cwd=cwd, env=env, **_popen_kwargs())
    timed_out = False
    interrupted = False
    killed = False

    try:
        stdout_b, stderr_b = proc.communicate(input=req_bytes, timeout=max(0.0, float(timeout_s)))
    except subprocess.TimeoutExpired:
        timed_out = True
        interrupted = _interrupt_process(proc)
        try:
            stdout_b, stderr_b = proc.communicate(timeout=max(0.0, float(grace_s)))
        except subprocess.TimeoutExpired:
            killed = _kill_process(proc)
            stdout_b, stderr_b = proc.communicate()

    elapsed = time.monotonic() - t0
    code = proc.returncode

    response = None
    protocol_error = None
    if stderr_b:
        try:
            response = _loads_frame_from_bytes(stderr_b)
        except Exception as e:
            protocol_error = f"{type(e).__name__}: {e}"

    ok = bool(response and response.get("ok") is True and code == 0 and protocol_error is None and not timed_out)
    return OneShotRunResult(
        ok=ok,
        response=response if isinstance(response, dict) else None,
        exit_code=code,
        timed_out=timed_out,
        interrupted=interrupted,
        killed=killed,
        elapsed_s=elapsed,
        stdout_raw=stdout_b or b"",
        stderr_raw=stderr_b or b"",
        protocol_error=protocol_error,
    )


def resolve_object(dotted_path: str) -> Any:
    mod_name, _, attr = dotted_path.rpartition(".")
    if not mod_name or not attr:
        raise ValueError(f"Invalid dotted path: {dotted_path!r}")
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)
