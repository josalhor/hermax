from __future__ import annotations

import os
import pickle
import struct
import sys
import traceback
from typing import Any, Dict, Iterable

from hermax.internal.subprocess_oneshot import _HEADER_STRUCT, resolve_object


def _read_exact(stream, n: int) -> bytes:
    out = bytearray()
    while len(out) < n:
        chunk = stream.read(n - len(out))
        if not chunk:
            break
        out.extend(chunk)
    return bytes(out)


def _read_frame(stream) -> Any:
    header = _read_exact(stream, _HEADER_STRUCT.size)
    if len(header) != _HEADER_STRUCT.size:
        raise EOFError("Missing frame header")
    (nbytes,) = _HEADER_STRUCT.unpack(header)
    payload = _read_exact(stream, nbytes)
    if len(payload) != nbytes:
        raise EOFError("Truncated frame payload")
    return pickle.loads(payload)


def _write_frame(stream, obj: Any) -> None:
    payload = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(_HEADER_STRUCT.pack(len(payload)))
    stream.write(payload)
    stream.flush()


def _snapshot_replay_to_solver(solver, snap: Dict[str, Any]) -> None:
    nvars = int(snap.get("num_vars", 0))
    for _ in range(nvars):
        try:
            solver.new_var()
        except AttributeError:
            # Some wrappers size vars on demand only.
            break

    for cl in snap.get("hard_clauses", []):
        solver.add_clause([int(x) for x in cl])

    for lit, w in snap.get("soft_units", []):
        solver.set_soft(int(lit), int(w))

    for cl, w in snap.get("soft_nonunit", []):
        solver.add_clause([int(x) for x in cl], int(w))


def _ops_replay_to_solver(solver, ops: Iterable[Any]) -> None:
    for raw in ops:
        if not isinstance(raw, (tuple, list)) or not raw:
            raise TypeError(f"Invalid op record: {raw!r}")
        op = str(raw[0])
        if op == "new_var":
            try:
                solver.new_var()
            except (AttributeError, NotImplementedError):
                # Some wrappers size variables lazily/on-demand.
                pass
        elif op == "add_clause":
            _, clause = raw
            solver.add_clause([int(x) for x in clause])
        elif op == "set_soft":
            _, lit, w = raw
            solver.set_soft(int(lit), int(w))
        elif op == "add_soft_unit":
            _, lit, w = raw
            solver.add_soft_unit(int(lit), int(w))
        elif op == "add_soft_relaxed":
            _, clause, w, relax_var = raw
            solver.add_soft_relaxed([int(x) for x in clause], int(w), None if relax_var is None else int(relax_var))
        else:
            raise ValueError(f"Unknown op: {op!r}")


def _run_request(req: Dict[str, Any]) -> Dict[str, Any]:
    cls_path = req["solver_class_path"]
    assumptions = [int(x) for x in req.get("assumptions") or []]
    snapshot = dict(req.get("snapshot") or {})
    ops = req.get("ops")
    solver_cls = resolve_object(cls_path)
    solver = solver_cls()
    try:
        if ops is not None:
            _ops_replay_to_solver(solver, ops)
        else:
            _snapshot_replay_to_solver(solver, snapshot)
        is_sat = bool(solver.solve(assumptions=assumptions, raise_on_abnormal=False))

        status = solver.get_status()
        response: Dict[str, Any] = {
            "ok": True,
            "is_sat": is_sat,
            "status": int(status),
            "status_name": getattr(status, "name", str(status)),
            "signature": None,
            "cost": None,
            "model": None,
        }
        try:
            response["signature"] = solver.signature()
        except Exception:
            pass
        try:
            response["cost"] = int(solver.get_cost())
        except Exception:
            pass
        try:
            model = solver.get_model()
            response["model"] = list(model) if model is not None else None
        except Exception:
            pass
        return response
    finally:
        try:
            solver.close()
        except Exception:
            pass


def main() -> int:
    try:
        req = _read_frame(sys.stdin.buffer)
        if not isinstance(req, dict):
            raise TypeError("Worker request must be a dict")
        resp = _run_request(req)
        _write_frame(sys.stderr.buffer, resp)
        return 0
    except BaseException as e:
        err = {
            "ok": False,
            "error_type": type(e).__name__,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        try:
            _write_frame(sys.stderr.buffer, err)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
