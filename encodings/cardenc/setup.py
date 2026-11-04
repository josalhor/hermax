from pathlib import Path
import os
import platform
import sysconfig

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


ROOT = Path(__file__).resolve().parent


class CardBuildExt(build_ext):
    def build_extensions(self):
        if self.debug:
            for ext in self.extensions:
                ext.extra_compile_args = [flag for flag in ext.extra_compile_args
                                          if flag not in {"-O3", "-DNDEBUG", "-flto", "/O2", "/GL"}]
                ext.extra_compile_args += (["/Od", "/UNDEBUG"] if platform.system() == "Windows"
                                           else ["-O0", "-UNDEBUG"])
                ext.extra_link_args = []
        super().build_extensions()


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
    cmdclass={"build_ext": CardBuildExt},
    ext_modules=[
        Extension(
            "hermax_pycard",
            sources=[str(ROOT / "pycard.cc")],
            include_dirs=[
                str(ROOT),
                str(ROOT.parents[1] / "hermax" / "internal"),
                *(p for p in [sysconfig.get_paths().get("include"), sysconfig.get_paths().get("platinclude")] if p),
            ],
            language="c++",
            extra_compile_args=_compile_args(),
            extra_link_args=_link_args(),
        )
    ],
    zip_safe=False,
)
