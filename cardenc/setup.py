from pathlib import Path
import os
import platform
import sysconfig

from setuptools import Extension, setup


ROOT = Path(__file__).resolve().parent


def _compile_args():
    use_native = os.environ.get("HERMAX_PYCARD_NATIVE", "0") == "1"
    use_lto = os.environ.get("HERMAX_PYCARD_LTO", "0") == "1"
    use_pyint_cache = os.environ.get("HERMAX_PYCARD_PYINT_CACHE", "1") == "1"

    if platform.system() == "Windows":
        # Conservative flags for MSVC.
        flags = ["/O2", "/std:c++17", f"/DHERMAX_PYCARD_ENABLE_PYINT_CACHE={1 if use_pyint_cache else 0}"]
        if use_lto:
            flags.append("/GL")
        return flags

    flags = ["-O3", "-Wall", "-std=c++17", "-DNDEBUG", f"-DHERMAX_PYCARD_ENABLE_PYINT_CACHE={1 if use_pyint_cache else 0}"]
    if use_native:
        flags.extend(["-march=native", "-mtune=native"])
    if use_lto:
        flags.append("-flto")
    return flags


def _link_args():
    use_lto = os.environ.get("HERMAX_PYCARD_LTO", "0") == "1"
    if not use_lto:
        return []
    if platform.system() == "Windows":
        return ["/LTCG"]
    return ["-flto"]


setup(
    name="hermax-pycard-standalone",
    version="0.0.1",
    description="Standalone build of hermax_pycard extension for local parity/perf testing",
    ext_modules=[
        Extension(
            "hermax_pycard",
            sources=[str(ROOT / "pycard.cc")],
            include_dirs=[
                str(ROOT),
                *(p for p in [sysconfig.get_paths().get("include"), sysconfig.get_paths().get("platinclude")] if p),
            ],
            language="c++",
            extra_compile_args=_compile_args(),
            extra_link_args=_link_args(),
        )
    ],
    zip_safe=False,
)
