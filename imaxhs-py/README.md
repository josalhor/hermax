# iMaxHS Python Bindings for hermax

This directory contains the Python bindings and integration logic for the **iMaxHS** MaxSAT solver. iMaxHS is a hybrid solver that leverages both SAT (via CaDiCaL) and Integer Programming (via IBM CPLEX).

## Prerequisites

To build and use the iMaxHS extension, you must have:
1.  **IBM CPLEX Optimization Studio** installed on your system.
2.  **CMake** (>= 3.15) and a C++17 compatible compiler.
3.  **zlib** and **libdl** development headers.

## Installation

The extension is built automatically when you install `hermax`. You can control the build process using environment variables.

### Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `CPLEX_LIB_DIR` | Path to the directory containing shared CPLEX libraries (`.so`). | `$HOME/opt/cplex/cplex/bin/x86-64_linux` |
| `CPLEX_INC_DIR` | Path to the CPLEX `include` directory. | `$HOME/opt/cplex/cplex/include` |
| `SKIP_IMAXHS` | Set to `1` to bypass the iMaxHS build entirely. | (empty) |

### Example Install Command

```bash
# Standard install with custom CPLEX path
export CPLEX_LIB_DIR=$HOME/opt/cplex/cplex/bin/x86-64_linux
export CPLEX_INC_DIR=$HOME/opt/cplex/cplex/include
pip install .
```

## Usage in Python

The solver is accessible via the `IMaxHSSolver` class. The library is designed to be "import-safe"; it will not crash if the extension is missing, but will instead report availability.

**Note:** Since iMaxHS is dynamically linked, you must ensure CPLEX is in your library search path at runtime:
```bash
export LD_LIBRARY_PATH=$HOME/opt/cplex/cplex/bin/x86-64_linux:$LD_LIBRARY_PATH
python your_script.py
```

```python
from hermax.imaxhs_wrapper_py import IMaxHSSolver

if IMaxHSSolver.is_available():
    solver = IMaxHSSolver()
    solver.add_clause([1, 2])
    solver.add_soft_unit(-1, 10)
    if solver.solve():
        print(f"Optimal cost: {solver.get_cost()}")
else:
    print("IMaxHS is not available.")
```

## Troubleshooting

### "IMaxHSSolver is not available"
If `is_available()` returns `False` or the constructor raises a `RuntimeError`:
1.  **Build Phase:** Check your `pip install` logs. If CPLEX was not detected at the paths provided, the build will have skipped the extension ("soft crash").
2.  **Runtime Phase:** If you linked against CPLEX shared libraries (`.so`), ensure the path to those libraries is in your `LD_LIBRARY_PATH`.
3.  **Binary Mismatch:** Ensure the CPLEX version used during compilation is compatible with the one available at runtime.

## Distribution Notes

This extension is built as a dynamically linked Python module. 
- When building **Wheels**, note that `auditwheel` may attempt to vendor CPLEX. Due to licensing restrictions, you should be careful about redistributing wheels containing proprietary IBM code.
- For most users, building from source (sdist) with a local CPLEX installation is the recommended path.
