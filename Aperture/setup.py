"""Setup script for Aperture Python package."""

import os
import re
import subprocess
import sys
from pathlib import Path

from setuptools import setup

# Read version from the package VERSION file
version_file = Path(__file__).parent / "aperture" / "VERSION"
with open(version_file) as f:
    __version__ = f.read().strip()


def build_extension():
    """Build Python extension using Makefile."""
    print("Building Aperture Python bindings...")
    env = os.environ.copy()
    # Ensure the Makefile uses the same Python interpreter as the build process
    env["PYTHON3"] = sys.executable
    # Use parallelism if available
    jobs = os.environ.get("MAKEFLAGS", "-j$(nproc)")
    cmd = ["make", "lpy"]
    print("Running:", " ".join(cmd), "(cwd=", Path(__file__).parent, ")")
    result = subprocess.run(cmd, cwd=Path(__file__).parent, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to build Python bindings. "
            "Make sure you have: g++, make, python3-dev, nanobind"
        )
    print("Successfully built Python bindings!")


# Build the extension module before setup
build_extension()

setup(
    name="aperture-solver",
    version=__version__,
    description="A SAT-based optimization solver",
    long_description=open("aperture/docs/PYTHONAPI.md").read(),
    long_description_content_type="text/markdown",
    url="",
    author="Yam Slonimski",
    author_email="yamslonimski@campus.technion.ac.il",
    license="MIT",
    packages=["aperture"],
    package_data={
        "aperture": ["_aperture.so", "py.typed", "VERSION"],
    },
    include_package_data=True,
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: C++",
        "Operating System :: POSIX :: Linux",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Mathematics",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Information Technology",
    ],
    keywords=[
        "SAT",
        "MaxSAT",
        "OBV",
        "Black-Box",
        "solver",
        "optimization",
        "constraint",
        "satisfiability"
    ],
)
