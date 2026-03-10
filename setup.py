import os
import stat
import re
import sys
import platform
import subprocess
import shutil
from pathlib import Path
import pybind11
import sysconfig
import glob
import tempfile

from setuptools import setup, Extension, find_packages
from setuptools.command.build_ext import build_ext

class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)

import subprocess, os, re

def _run_logged(cmd, *, cwd, env, log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8", errors="replace") as f:
        p = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        # print tail, sanitized (strip ANSI + convert CR to NL)
        with open(log_path, "r", encoding="utf-8", errors="replace") as r:
            s = r.read()
        s = s.replace("\r", "\n")
        s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)
        tail = "\n".join(s.splitlines()[-200:])
        print(f"\n=== command failed: {' '.join(cmd)} ===")
        print(f"=== log: {log_path} (last 200 lines) ===\n{tail}\n")
        raise RuntimeError(f"Command failed: {cmd} (see log {log_path})")


class CMakeBuild(build_ext):
    def _ensure_linux_compiler_wrappers(self, real_cc: str, real_cxx: str):
        """
        Create stable compiler wrapper scripts that opportunistically use ccache.
        If ccache is unavailable, wrappers fall back to the real compiler.
        """
        wrap_dir = "/tmp/hermax-toolchain"
        os.makedirs(wrap_dir, exist_ok=True)

        cc_path = os.path.join(wrap_dir, "gcc")
        cxx_path = os.path.join(wrap_dir, "g++")

        cc_script = f"""#!/usr/bin/env bash
set -e
REAL="{real_cc}"
if command -v ccache >/dev/null 2>&1; then
  exec ccache "$REAL" "$@"
fi
exec "$REAL" "$@"
"""

        cxx_script = f"""#!/usr/bin/env bash
set -e
REAL="{real_cxx}"
if command -v ccache >/dev/null 2>&1; then
  exec ccache "$REAL" "$@"
fi
exec "$REAL" "$@"
"""

        for path, script in ((cc_path, cc_script), (cxx_path, cxx_script)):
            with open(path, "w", encoding="utf-8") as f:
                f.write(script)
            os.chmod(path, 0o755)

        return cc_path, cxx_path

    def _ensure_windows_compiler_wrappers(self, real_cc: str, real_cxx: str):
        """
        Create stable compiler wrapper scripts for Windows that opportunistically
        use ccache and otherwise fall back to the real compiler.
        """
        wrap_dir = os.path.join(tempfile.gettempdir(), "hermax-toolchain-win")
        os.makedirs(wrap_dir, exist_ok=True)

        cc_path = os.path.join(wrap_dir, "gcc-wrapper.cmd")
        cxx_path = os.path.join(wrap_dir, "gxx-wrapper.cmd")

        cc_script = f"""@echo off
set REAL={real_cc}
where ccache >nul 2>nul
if %errorlevel%==0 (
  ccache "%REAL%" %*
) else (
  "%REAL%" %*
)
"""

        cxx_script = f"""@echo off
set REAL={real_cxx}
where ccache >nul 2>nul
if %errorlevel%==0 (
  ccache "%REAL%" %*
) else (
  "%REAL%" %*
)
"""

        for path, script in ((cc_path, cc_script), (cxx_path, cxx_script)):
            with open(path, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(script)

        return cc_path, cxx_path

    def _scrub_prebuilt_native_artifacts(self):
        # Prevent host-built binaries from being reused inside containerized wheel builds.
        patterns = [
            "hermax_pycard*.so",
            "hermax_pycard*.pyd",
            "hermax_pycard*.dylib",
            "hermax/**/*.so",
            "hermax/**/*.pyd",
            "hermax/**/*.dylib",
            "*.so",
            "*.pyd",
            "*.dylib",
            "fast_wcnf_loader_capi*.so",
            "fast_wcnf_loader_capi*.pyd",
            "fast_wcnf_loader_capi*.dylib",
            os.path.join("loading", "fast_wcnf_loader_capi*.so"),
            os.path.join("loading", "fast_wcnf_loader_capi*.pyd"),
            os.path.join("loading", "fast_wcnf_loader_capi*.dylib"),
            os.path.join("build", "lib*", "hermax_pycard*.so"),
            os.path.join("build", "lib*", "hermax_pycard*.pyd"),
            os.path.join("build", "lib*", "hermax_pycard*.dylib"),
            os.path.join("build", "lib*", "fast_wcnf_loader_capi*.so"),
            os.path.join("build", "lib*", "fast_wcnf_loader_capi*.pyd"),
            os.path.join("build", "lib*", "fast_wcnf_loader_capi*.dylib"),
        ]
        removed = 0
        for pattern in patterns:
            for path in glob.glob(pattern, recursive=True):
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                        removed += 1
                    except OSError:
                        pass
        # Do not remove build/lib*: setuptools may have already copied Python
        # package files there (build_py runs before build_ext in wheel builds).
        # Removing build/lib* causes wheels with only .so artifacts.
        for pattern in [os.path.join("build", "temp*")]:
            for path in glob.glob(pattern):
                if os.path.isdir(path):
                    try:
                        shutil.rmtree(path)
                    except OSError:
                        pass
        if removed:
            print(f"Removed {removed} prebuilt native artifact(s) before build.")

        # Prevent stale bytecode from getting packaged into wheels.
        # Old .pyc files can reference removed modules (e.g. legacy imports).
        pyc_removed = 0
        for root in ("hermax", os.path.join("build", "lib")):
            if not os.path.exists(root):
                continue
            for pyc in glob.glob(os.path.join(root, "**", "*.pyc"), recursive=True):
                try:
                    os.remove(pyc)
                    pyc_removed += 1
                except OSError:
                    pass
            for pydir in glob.glob(os.path.join(root, "**", "__pycache__"), recursive=True):
                if os.path.isdir(pydir):
                    try:
                        shutil.rmtree(pydir)
                    except OSError:
                        pass
        if pyc_removed:
            print(f"Removed {pyc_removed} stale bytecode file(s) before build.")

    def run(self):
        self._scrub_prebuilt_native_artifacts()
        try:
            subprocess.check_call(['cmake', '--version'])
        except OSError:
            raise RuntimeError("CMake must be installed.")

        os.makedirs(self.build_lib, exist_ok=True)
        # Let setuptools initialize the compiler toolchain for regular C/C++
        # extensions, while our overridden build_extension handles CMake ones.
        build_ext.run(self)

    def build_extension(self, ext):
        # Support regular setuptools Extension modules alongside CMake ones.
        if not isinstance(ext, CMakeExtension):
            return build_ext.build_extension(self, ext)

        abi_tag = sysconfig.get_config_var("SOABI") or f"cp{sys.version_info.major}{sys.version_info.minor}"
        ext_fullpath = self.get_ext_fullpath(ext.name)
        extdir = os.path.abspath(os.path.dirname(ext_fullpath)).replace("\\", "/")

        os.makedirs(extdir, exist_ok=True)

        
        build_temp_path = os.path.join(self.build_temp, f"build_{ext.name}_{abi_tag}")
        if os.path.exists(build_temp_path):
            shutil.rmtree(build_temp_path)
        os.makedirs(build_temp_path, exist_ok=True)
        
        cfg = "Debug" if self.debug else "Release"
        env = self.get_base_env()

        if platform.system() == "Windows" and "openwbo" in ext.name and not self._is_mingw_toolchain(env):
            raise RuntimeError(
                f"{ext.name} must be built with MSYS2 MinGW on Windows. "
                "Set MSYSTEM=MINGW64 and MINGW_PREFIX=C:\\msys64\\mingw64 in cibuildwheel environment."
            )

        # open-wbo subprojects set their own standards in CMakeLists.
        # We default to 17 for others.
        cxx_std = "17"
        if "openwbo" in ext.name:
            cxx_std = "" 

        cmake_args = [
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}",
            f"-DPython3_EXECUTABLE={sys.executable}",
            f"-DPython3_ROOT_DIR={sys.exec_prefix}",
            f"-Dpybind11_DIR={pybind11.get_cmake_dir()}",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
            "-DPYBIND11_FINDPYTHON=ON",
            f"-DCMAKE_BUILD_TYPE={cfg}",
            "-DCMAKE_C_STANDARD=11",
            f"-DCMAKE_CXX_FLAGS={env.get('CXXFLAGS', '')}",
            f"-DCMAKE_C_FLAGS={env.get('CFLAGS', '')}",
        ]
        if cxx_std:
            cmake_args.append(f"-DCMAKE_CXX_STANDARD={cxx_std}")

        if platform.system() == "Darwin":
            homebrew_prefix = None
            if os.path.exists("/opt/homebrew"): 
                homebrew_prefix = "/opt/homebrew"
            elif os.path.exists("/usr/local"): 
                homebrew_prefix = "/usr/local"
            if homebrew_prefix:
                cmake_args.append(f"-DCMAKE_PREFIX_PATH={homebrew_prefix}")

        if platform.system() == "Windows" and self._is_mingw_toolchain(env):
            # Fail early if 32/64 bit mismatch between Python and compiler prefix
            exe_is_32 = (sys.maxsize <= 2**32)
            cxx = env.get("CXX", "").lower()
            if exe_is_32 and ("mingw64" in cxx or "x86_64" in cxx):
                raise RuntimeError("You are building cp*-win32 (32-bit Python) but using a 64-bit MinGW compiler. Use MINGW32.")
            if (not exe_is_32) and ("mingw32" in cxx or "i686" in cxx):
                raise RuntimeError("You are building 64-bit Python but using a 32-bit MinGW compiler. Use MINGW64/UCRT64.")

            imp_lib = self._ensure_mingw_python_import_lib(build_temp_path, env)

            # Tell FindPython3 / link step to use MinGW import lib, not pythonXY.lib
            cmake_python_inc = sysconfig.get_path("include")
            cmake_args += [
                f"-DPython3_INCLUDE_DIR={cmake_python_inc}",
                f"-DPython3_LIBRARY={imp_lib}",
                f"-DPython3_LIBRARY_RELEASE={imp_lib}",
                f"-DPython3_LIBRARY_DEBUG={imp_lib}",
            ]

            strip_exe = self._which_mingw_tool("strip", env)
            ranlib_exe = self._which_mingw_tool("ranlib", env)
            ar_exe = self._which_mingw_tool("ar", env)
            dlltool_exe = self._which_mingw_tool("dlltool", env)
            objcopy_exe = self._which_mingw_tool("objcopy", env)

            # If any of these are None, you'll keep seeing WinError 2.
            # Passing them makes CMake/Ninja deterministic.
            if strip_exe:
                cmake_args.append(f"-DCMAKE_STRIP={strip_exe}")
            if ranlib_exe:
                cmake_args.append(f"-DCMAKE_RANLIB={ranlib_exe}")
            if ar_exe:
                cmake_args.append(f"-DCMAKE_AR={ar_exe}")
            if dlltool_exe:
                cmake_args.append(f"-DCMAKE_DLLTOOL={dlltool_exe}")
            if objcopy_exe:
                cmake_args.append(f"-DCMAKE_OBJCOPY={objcopy_exe}")
            cmake_args += [
                "-DCMAKE_VERBOSE_MAKEFILE=ON",
            ]


        subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=build_temp_path, env=env)
        subprocess.check_call(["cmake", "--build", ".", "--config", cfg], cwd=build_temp_path, env=env)
        
        self.verify_abi(ext, extdir, abi_tag)


    def _is_mingw_toolchain(self, env):
        if platform.system() != "Windows":
            return False
        if (env.get("HERMAX_WINDOWS_MINGW", "") or "").strip() == "1":
            return True

        cxx = (env.get("CXX") or "").lower()
        cxx_base = os.path.basename(cxx)
        if (
            "g++.exe" in cxx
            or cxx.endswith("g++")
            or "gxx-wrapper.cmd" in cxx_base
            or "g++" in cxx_base
        ):
            return True

        path = env.get("PATH", "")
        has_gxx = bool(shutil.which("g++", path=path))
        has_mingw32_make = bool(shutil.which("mingw32-make", path=path))
        has_msys64 = "msys64" in path.lower()
        return has_gxx and (has_mingw32_make or has_msys64)

    def _python_xy(self):
        return f"{sys.version_info.major}{sys.version_info.minor}"

    @staticmethod
    def _clean_env_path(value):
        if value is None:
            return ""
        cleaned = str(value).strip().strip("\"'")
        if platform.system() == "Windows" and cleaned:
            cleaned = cleaned.replace("/", "\\")
            cleaned = re.sub(r"^([A-Za-z]):(?=[^\\])", r"\1:\\", cleaned)
            cleaned = re.sub(r"\\msys64(?=(mingw64|mingw32|ucrt64|clang64))", r"\\msys64\\", cleaned, flags=re.IGNORECASE)
        return cleaned

    def _mingw_triplet_prefixes(self, env):
        msystem = self._clean_env_path(env.get("MSYSTEM", "")).upper()
        mingw_prefix = self._clean_env_path(env.get("MINGW_PREFIX", ""))

        names = []
        if msystem == "MINGW64" or "mingw64" in mingw_prefix.lower():
            names.extend(["x86_64-w64-mingw32", "x86_64-w64-mingw64"])
        elif msystem == "MINGW32" or "mingw32" in mingw_prefix.lower():
            names.extend(["i686-w64-mingw32"])
        elif msystem == "UCRT64" or "ucrt64" in mingw_prefix.lower():
            names.extend(["x86_64-w64-mingw32", "x86_64-w64-mingw64"])
        elif msystem == "CLANG64" or "clang64" in mingw_prefix.lower():
            names.extend(["x86_64-w64-mingw32", "x86_64-w64-mingw64"])
        return names

    def _which_mingw_tool(self, tool, env):
        path = env.get("PATH", "")
        found = shutil.which(tool, path=path)
        if found:
            return found

        for triplet in self._mingw_triplet_prefixes(env):
            prefixed = f"{triplet}-{tool}"
            found = shutil.which(prefixed, path=path)
            if found:
                return found

        mingw_prefix = self._clean_env_path(env.get("MINGW_PREFIX", ""))
        if mingw_prefix:
            mingw_bin = os.path.join(mingw_prefix, "bin")
            if os.path.isdir(mingw_bin):
                direct = os.path.join(mingw_bin, f"{tool}.exe")
                if os.path.exists(direct):
                    return direct
                for triplet in self._mingw_triplet_prefixes(env):
                    direct = os.path.join(mingw_bin, f"{triplet}-{tool}.exe")
                    if os.path.exists(direct):
                        return direct
        return None

    def _find_python_dll(self):
        # nuget-cpython layout: python.exe and pythonXY.dll are usually next to each other
        exe_dir = os.path.dirname(sys.executable)
        dll_name = f"python{self._python_xy()}.dll"

        candidates = [
            os.path.join(exe_dir, dll_name),
            os.path.join(sys.base_prefix, dll_name),
            os.path.join(sys.exec_prefix, dll_name),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p

        # last resort: search nearby
        for root in {exe_dir, sys.base_prefix, sys.exec_prefix}:
            for p in glob.glob(os.path.join(root, "**", dll_name), recursive=True):
                if os.path.exists(p):
                    return p

        raise RuntimeError(f"Could not locate {dll_name} near {sys.executable}")

    def _ensure_mingw_python_import_lib(self, build_temp_path, env):
        py_dll = self._find_python_dll()
        xy = self._python_xy()

        # make sure build_temp_path is absolute to avoid weird relative paths
        build_temp_path = os.path.abspath(build_temp_path)

        out_dir = os.path.join(build_temp_path, "_pyimp")
        os.makedirs(out_dir, exist_ok=True)

        def_file = os.path.join(out_dir, f"python{xy}.def")
        imp_lib  = os.path.join(out_dir, f"libpython{xy}.dll.a")

        if os.path.exists(imp_lib):
            return imp_lib

        gendef = self._which_mingw_tool("gendef", env)
        pexports = self._which_mingw_tool("pexports", env)
        dlltool = self._which_mingw_tool("dlltool", env)
        if not dlltool:
            mingw_prefix = self._clean_env_path(env.get("MINGW_PREFIX", ""))
            mingw_dlltool = os.path.join(mingw_prefix, "bin", "dlltool.exe") if mingw_prefix else ""
            raise RuntimeError(
                "Missing dlltool in PATH "
                f"(MSYSTEM={env.get('MSYSTEM','')!r}, "
                f"MINGW_PREFIX={env.get('MINGW_PREFIX','')!r}, "
                f"MSYS2_ROOT={env.get('MSYS2_ROOT','')!r}, "
                f"PATH_has_msys64={'msys64' in env.get('PATH','').lower()}, "
                f"mingw_dlltool_exists={bool(mingw_dlltool and os.path.exists(mingw_dlltool))})"
            )

        def _write_def_via_link_exports() -> bool:
            # Fallback: use MSVC link.exe exports dump (available in cibw VS images).
            try:
                proc = subprocess.run(
                    ["link", "/dump", "/exports", py_dll],
                    cwd=out_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except Exception:
                return False

            names = []
            # Typical line shape:
            # "    1    0 0001A2B0 PyAIter_Check"
            pat = re.compile(r"^\s*\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+(\S+)\s*$")
            for line in proc.stdout.splitlines():
                m = pat.match(line)
                if not m:
                    continue
                name = m.group(1)
                if name.upper() in {"[NONAME]", "NONAME"}:
                    continue
                names.append(name)

            if not names:
                return False

            dll_base = os.path.basename(py_dll)
            with open(def_file, "w", newline="\n", encoding="utf-8") as f:
                f.write(f"LIBRARY {dll_base}\nEXPORTS\n")
                for name in names:
                    f.write(f"{name}\n")
            return True

        # 1) Generate .def
        if gendef:
            # gendef prints to stdout, so capture it into pythonXY.def
            with open(def_file, "w", newline="\n") as f:
                subprocess.check_call([gendef, py_dll], cwd=out_dir, env=env, stdout=f)
        elif pexports:
            with open(def_file, "w", newline="\n") as f:
                subprocess.check_call([pexports, py_dll], cwd=out_dir, env=env, stdout=f)
        elif not _write_def_via_link_exports():
            raise RuntimeError(
                "Missing gendef/pexports in PATH and failed to generate .def via `link /dump /exports`."
            )

        if not os.path.exists(def_file) or os.path.getsize(def_file) == 0:
            raise RuntimeError(f"gendef produced empty def file: {def_file}")

        # 2) because cwd=out_dir, pass basenames (or absolute paths, but be consistent)
        subprocess.check_call(
            [dlltool,
            "-d", os.path.basename(def_file),
            "-l", os.path.basename(imp_lib),
            "-D", os.path.basename(py_dll)],
            cwd=out_dir,
            env=env,
        )

        return imp_lib

    def get_base_env(self):
        env = os.environ.copy()

        sysname = platform.system()

        # -------------------------
        # Linux (manylinux)
        # -------------------------
        if sysname == "Linux":
            gcc_bin = "/opt/rh/gcc-toolset-11/root/usr/bin"
            if os.path.exists(gcc_bin):
                env["PATH"] = gcc_bin + ":" + env.get("PATH", "")
                default_cc = os.path.join(gcc_bin, "gcc")
                default_cxx = os.path.join(gcc_bin, "g++")
                real_cc = env.get("CC", default_cc)
                real_cxx = env.get("CXX", default_cxx)
                # Use wrappers so ccache is optional and never required.
                # This supports both CMake- and make-based sub-builds.
                wrap_cc, wrap_cxx = self._ensure_linux_compiler_wrappers(real_cc, real_cxx)
                env["CC"] = wrap_cc
                env["CXX"] = wrap_cxx
                env.setdefault("AR", os.path.join(gcc_bin, "ar"))
                env.setdefault("RANLIB", os.path.join(gcc_bin, "ranlib"))

            common = "-fPIC -O2 -U_ISOC23_SOURCE -D_DEFAULT_SOURCE -D_GNU_SOURCE"
            env.setdefault("CFLAGS", f"{common} -std=gnu11")
            env.setdefault("CXXFLAGS", f"{common} -std=gnu++17")

            return env

        # -------------------------
        # macOS
        # -------------------------
        if sysname == "Darwin":
            env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:" + env.get("PATH", "")
            for prefix in ["/opt/homebrew", "/usr/local"]:
                if os.path.exists(prefix):
                    env["CPATH"] = f"{prefix}/include:" + env.get("CPATH", "")
                    env["LIBRARY_PATH"] = f"{prefix}/lib:" + env.get("LIBRARY_PATH", "")
                    env["PATH"] = env.get("PATH", "") + f":{prefix}/bin"

            common = "-fPIC -O2"
            env.setdefault("CFLAGS", f"{common} -std=gnu11")
            env.setdefault("CXXFLAGS", f"{common} -std=gnu++17")

            return env

        # -------------------------
        # Windows (MSYS2 MinGW-w64)
        # -------------------------
        if sysname == "Windows":
            import shutil

            msystem = self._clean_env_path(env.get("MSYSTEM", ""))
            mingw_prefix = self._clean_env_path(env.get("MINGW_PREFIX", ""))

            # Try to infer MSYS2 root if not provided
            msys2_root = self._clean_env_path(env.get("MSYS2_ROOT", r"C:\msys64")) or r"C:\msys64"
            usr_bin = os.path.join(msys2_root, "usr", "bin")

            # If MINGW_PREFIX missing, infer from MSYSTEM
            if not mingw_prefix and msystem:
                guess = {
                    "MINGW64": os.path.join(msys2_root, "mingw64"),
                    "UCRT64": os.path.join(msys2_root, "ucrt64"),
                    "CLANG64": os.path.join(msys2_root, "clang64"),
                    "MINGW32": os.path.join(msys2_root, "mingw32"),
                }.get(msystem, "")
                if guess:
                    mingw_prefix = guess

            # Fallback auto-detection for cibuildwheel Windows environments where
            # per-platform env vars are not propagated as expected.
            if not mingw_prefix:
                for candidate, inferred_msystem in (
                    (os.path.join(msys2_root, "mingw64"), "MINGW64"),
                    (os.path.join(msys2_root, "ucrt64"), "UCRT64"),
                    (os.path.join(msys2_root, "clang64"), "CLANG64"),
                    (os.path.join(msys2_root, "mingw32"), "MINGW32"),
                ):
                    if os.path.isdir(os.path.join(candidate, "bin")):
                        mingw_prefix = candidate
                        if not msystem:
                            msystem = inferred_msystem
                            env["MSYSTEM"] = msystem
                        env["MINGW_PREFIX"] = mingw_prefix
                        break

            if mingw_prefix:
                mingw_bin = os.path.join(mingw_prefix, "bin")

                # Put MinGW first, but also keep MSYS tools accessible
                env["PATH"] = mingw_bin + ";" + usr_bin + ";" + env.get("PATH", "")

                # Force GCC toolchain explicitly (avoid MSVC), with wrappers so
                # ccache is optional and never required.
                env["CC"] = "gcc"
                env["CXX"] = "g++"
                env["AR"] = "ar"
                env["RANLIB"] = "ranlib"

                # Flags: keep simple and portable
                common = "-O2"
                env.setdefault("CFLAGS", f"{common} -std=gnu11")
                env.setdefault("CXXFLAGS", f"{common} -std=gnu++17")
                env["HERMAX_WINDOWS_MINGW"] = "1"

                # Pick a generator that actually exists
                if shutil.which("ninja", path=env["PATH"]):
                    env.setdefault("CMAKE_GENERATOR", "Ninja")
                else:
                    env.setdefault("CMAKE_GENERATOR", "MinGW Makefiles")

                return env

            # Not in MSYS2 context (PowerShell/CMD without toolchain)
            return env
        return env

    def _msys_bash(self, env):
        msys2_root = self._clean_env_path(env.get("MSYS2_ROOT", r"C:\msys64")) or r"C:\msys64"
        bash = os.path.join(msys2_root, "usr", "bin", "bash.exe")
        if not os.path.exists(bash):
            raise RuntimeError(f"MSYS2 bash not found at {bash}")
        return bash

    def _normalize_script_line_endings(self, path):
        if platform.system() != "Windows" or not os.path.exists(path):
            return
        with open(path, "rb") as f:
            data = f.read()
        fixed = data.replace(b"\r\n", b"\n")
        if fixed != data:
            with open(path, "wb") as f:
                f.write(fixed)
    
    def _make(self, make_args, *, cwd, env):
        """
        Cross-platform 'make' wrapper that delegates to _bash().
        - Windows (MSYS2 MinGW): uses mingw32-make if available, else make.
        - macOS/Linux: uses make.
        """
        import platform, shutil

        if not isinstance(make_args, (list, tuple)):
            raise TypeError("make_args must be a list/tuple of arguments")

        sysname = platform.system()

        if sysname == "Windows":
            # Prefer mingw32-make in MSYS2 MinGW environments
            path = (env or {}).get("PATH", "")
            make_exe = (
                shutil.which("mingw32-make", path=path)
                or shutil.which("make", path=path)
                or "mingw32-make"  # last resort: let bash resolve it
            )
            # Use basename inside bash to avoid Windows path quoting issues
            make_cmd = "mingw32-make" if make_exe.lower().endswith(("mingw32-make.exe", "mingw32-make")) else "make"
        else:
            make_cmd = "make"

        cmd_args = [make_cmd, *list(make_args)]
        try:
            return self._bash(cmd_args, cwd=cwd, env=env)
        except subprocess.CalledProcessError:
            target0 = str(make_args[0]).lower() if make_args else ""
            if target0 == "clean":
                print(f"Skipping missing/failed clean target in {cwd}")
                return 0
            raise

    def _bash(self, args, *, cwd, env):
        import shlex
        cwd_abs = os.path.abspath(cwd)
        cmd = " ".join(shlex.quote(a) for a in args)
        if platform.system() == "Windows":
            # In some Windows/MSYS2 contexts, bash -lc may not honor the process cwd.
            # Force an explicit directory change in the shell command.
            if len(cwd_abs) >= 3 and cwd_abs[1] == ":":
                drive = cwd_abs[0].lower()
                tail = cwd_abs[2:].replace("\\", "/")
                msys_cwd = f"/{drive}{tail}"
            else:
                msys_cwd = cwd_abs.replace("\\", "/")
            cmd = f"cd {shlex.quote(msys_cwd)} && {cmd}"
            bash = self._msys_bash(env)
        else:
            bash = "bash"
        print(f"Running {cmd}")
        return subprocess.check_call([bash, "-lc", cmd], cwd=cwd_abs, env=env)

    def verify_abi(self, ext, extdir, abi_tag):
        produced_sos = [f for f in os.listdir(extdir) if f.endswith((".so", ".dylib", ".pyd"))]
        ext_base_name = ext.name.split('.')[-1]
        found_correct = False
        for so_file in produced_sos:
            if ext_base_name in so_file:
                if platform.system() == "Linux":
                    if abi_tag in so_file:
                        found_correct = True
                    else:
                        print(f"ERROR: Build of {ext.name} produced WRONG ABI artifact: {so_file}")
                        sys.exit(1)
                else:
                    found_correct = True
        if not found_correct:
            print(f"ERROR: Build of {ext.name} did not produce expected extension in {extdir}")
            sys.exit(1)

class CMakeBuildURMaxSAT(CMakeBuild):
    def run(self):
        # Reuse base run() so setuptools initializes compilers for regular
        # C/C++ Extension modules (non-CMake).
        return super().run()

    def build_extension(self, ext):
        if ext.name == "hermax.core.urmaxsat_py":
            return self.build_urmaxsat(ext)
        if ext.name == "hermax.core.urmaxsat_comp_py":
            return self.build_urmaxsat_comp(ext)
        if ext.name == "hermax.core.cashwmaxsat":
            return self.build_cashwmaxsat(ext)
        if ext.name == "hermax.core.evalmaxsat_latest":
            return self.build_evalmaxsat_latest(ext)
        if ext.name == "hermax.core.evalmaxsat_incr":
            return self.build_evalmaxsat_incr(ext)
        return super().build_extension(ext)

    def _ranlib(self, lib_path, env=None):
        if not os.path.exists(lib_path):
            return

        if platform.system() == "Darwin":
            ranlib = "/usr/bin/ranlib"
        elif platform.system() == "Windows":
            # Use the same MinGW toolchain resolution logic as the solver builds.
            env_lookup = env or self.get_base_env()
            ranlib = self._which_mingw_tool("ranlib", env_lookup)
        else:
            # Linux: should be in PATH.
            ranlib = shutil.which("ranlib")

        if not ranlib:
            raise RuntimeError(f"ranlib not found for {platform.system()} toolchain")

        print(f"Indexing {lib_path} with ranlib: {ranlib}")
        subprocess.check_call([ranlib, lib_path])


    def _darwin_make_env(self, env):
        """Force Apple toolchain for legacy make projects."""
        if platform.system() != "Darwin":
            return env
        e = env.copy()
        e["CC"] = "clang"
        e["CXX"] = "clang++"
        e["AR"] = "/usr/bin/ar"
        e["RANLIB"] = "/usr/bin/ranlib"
        e["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:" + e.get("PATH", "")
        return e

    def _macos_rebuild_archive_if_gnu(self, lib_path):
        """
        If archive contains GNU symbol-table member '/', rebuild as a clean BSD archive.
        This must run BEFORE CMake links against the archive.
        """
        if platform.system() != "Darwin" or not os.path.exists(lib_path):
            return
        res = subprocess.run(["/usr/bin/ar", "-t", lib_path], capture_output=True, text=True)
        if res.returncode != 0:
            return
        members = res.stdout.splitlines()
        if "/" not in members:
            return

        print(f"MacOS: detected GNU archive member '/' in {lib_path}, rebuilding via libtool...")
        with tempfile.TemporaryDirectory() as td:
            subprocess.check_call(["/usr/bin/ar", "-x", lib_path], cwd=td)
            objs = []
            for fn in os.listdir(td):
                if fn in ("/", "__.SYMDEF", "__.SYMDEF SORTED"):
                    continue
                if fn.endswith((".o", ".or", ".op", ".od")):
                    objs.append(os.path.join(td, fn))
            if not objs:
                raise RuntimeError(f"Rebuild failed: no object members extracted from {lib_path}")
            tmp_out = lib_path + ".fixed"
            subprocess.check_call(["/usr/bin/libtool", "-static", "-o", tmp_out] + objs)
            os.replace(tmp_out, lib_path)
            subprocess.check_call(["/usr/bin/ranlib", lib_path])

        # Sanity: ensure '/' is gone
        res2 = subprocess.run(["/usr/bin/ar", "-t", lib_path], capture_output=True, text=True)
        if res2.returncode == 0 and "/" in res2.stdout.splitlines():
            raise RuntimeError(f"{lib_path} still contains '/' after rebuild")


    def build_evalmaxsat_incr(self, ext):
        abi_tag = sysconfig.get_config_var("SOABI") or f"cp{sys.version_info.major}{sys.version_info.minor}"
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        build_temp_path = os.path.join(self.build_temp, f"build_{ext.name}_{abi_tag}")
        os.makedirs(build_temp_path, exist_ok=True)
        env = self.get_base_env()
        eval_src_dir = os.path.abspath("EvalMaxSAT2022")
        
        cfg = os.path.join(eval_src_dir, "build_lib.sh")
        st = os.stat(cfg).st_mode
        os.chmod(cfg, st | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        self._bash(["./build_lib.sh"], cwd=eval_src_dir, env=env)
        eval_lib = os.path.join(eval_src_dir, "libipamirEvalMaxSAT2022.a")
        self._ranlib(eval_lib, env=env)
        cmake_args = [f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}", f"-DPython3_EXECUTABLE={sys.executable}", f"-DPython3_ROOT_DIR={sys.exec_prefix}", f"-Dpybind11_DIR={pybind11.get_cmake_dir()}", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DPYBIND11_FINDPYTHON=ON", "-DCMAKE_BUILD_TYPE=Release", f"-DEVALMAXSAT_INCR_LIB_ABS={eval_lib}", "-DCMAKE_C_STANDARD=11", "-DCMAKE_CXX_STANDARD=17", f"-DCMAKE_CXX_FLAGS={env.get('CXXFLAGS','')}", f"-DCMAKE_C_FLAGS={env.get('CFLAGS','')}"]
        subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=build_temp_path, env=env)
        subprocess.check_call(["cmake", "--build", ".", "-j"], cwd=build_temp_path, env=env)
        self.verify_abi(ext, extdir, abi_tag)

    def build_evalmaxsat_latest(self, ext):
        abi_tag = sysconfig.get_config_var("SOABI") or f"cp{sys.version_info.major}{sys.version_info.minor}"
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        build_temp_path = os.path.join(self.build_temp, f"build_{ext.name}_{abi_tag}")
        os.makedirs(build_temp_path, exist_ok=True)
        env = self.get_base_env()
        eval_src_dir = os.path.abspath("evalmaxsat")
        eval_build_dir = os.path.join(eval_src_dir, f"build_{abi_tag}")
        shutil.rmtree(eval_build_dir, ignore_errors=True)
        os.makedirs(eval_build_dir, exist_ok=True)
        subprocess.check_call(["cmake", "..", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_C_STANDARD=11", "-DCMAKE_CXX_STANDARD=17", f"-DCMAKE_CXX_FLAGS={env.get('CXXFLAGS','')}", f"-DCMAKE_C_FLAGS={env.get('CFLAGS','')}"], cwd=eval_build_dir, env=env)
        subprocess.check_call(["cmake", "--build", ".", "--target", "clean"], cwd=eval_build_dir, env=env)
        subprocess.check_call(["cmake", "--build", ".", "--config", "Release", "-j"], cwd=eval_build_dir, env=env)
        eval_lib = os.path.join(eval_build_dir, "lib", "EvalMaxSAT", "libEvalMaxSAT.a")
        glucose_lib = os.path.join(eval_build_dir, "lib", "glucose", "libglucose.a")
        cadical_lib = os.path.join(eval_build_dir, "lib", "cadical", "libcadical.a")
        # CMake handles ranlib automatically, but we keep it for consistency if needed
        eval_inc, malib_inc, cadical_inc, glucose_inc = [os.path.join(eval_src_dir, "lib", d, "src") for d in ["EvalMaxSAT", "MaLib", "cadical", "glucose"]]
        cmake_args = [f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}", f"-DPython3_EXECUTABLE={sys.executable}", f"-DPython3_ROOT_DIR={sys.exec_prefix}", f"-Dpybind11_DIR={pybind11.get_cmake_dir()}", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DPYBIND11_FINDPYTHON=ON", "-DCMAKE_BUILD_TYPE=Release", f"-DEVALMAXSAT_LIB_ABS={eval_lib}", f"-DGLUCOSE_LIB_ABS={glucose_lib}", f"-DCADICAL_LIB_ABS={cadical_lib}", f"-DEVALMAXSAT_INC_DIR={eval_inc}", f"-DMALIB_INC_DIR={malib_inc}", f"-DCADICAL_INC_DIR={cadical_inc}", f"-DGLUCOSE_INC_DIR={glucose_inc}", "-DCMAKE_C_STANDARD=11", "-DCMAKE_CXX_STANDARD=17", f"-DCMAKE_CXX_FLAGS={env.get('CXXFLAGS','')}", f"-DCMAKE_C_FLAGS={env.get('CFLAGS','')}"]
        subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=build_temp_path, env=env)
        subprocess.check_call(["cmake", "--build", ".", "-j"], cwd=build_temp_path, env=env)
        self.verify_abi(ext, extdir, abi_tag)

    def build_cashwmaxsat(self, ext):
        abi_tag = sysconfig.get_config_var("SOABI") or f"cp{sys.version_info.major}{sys.version_info.minor}"
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        build_temp_path = os.path.join(self.build_temp, f"build_{ext.name}_{abi_tag}")
        os.makedirs(build_temp_path, exist_ok=True)
        env = self.get_base_env()
        env = self._darwin_make_env(env)
        cash_dir = os.path.abspath("CASHWMaxSAT")
        cominisatps_dir = os.path.join(cash_dir, "cominisatps")
        cadical_dir = os.path.join(cash_dir, "cadical")
        uwr_dir = os.path.join(cash_dir, "uwrmaxsat")
        self._make(["clean"], cwd=cominisatps_dir, env=env)
        self._make(["lr", "-j", "LDFLAG_STATIC="], cwd=cominisatps_dir, env=env)
        cominisatps_a = os.path.join(cominisatps_dir, "build", "release", "lib", "libcominisatps.a")
        print('ranlib')
        self._ranlib(cominisatps_a, env=env)
        print('macos rebuild')
        self._macos_rebuild_archive_if_gnu(cominisatps_a)
        print('make clean')
        if os.path.exists(os.path.join(cadical_dir, "Makefile")):
            self._make(["clean"], cwd=cadical_dir, env=env)
        
        cfg = os.path.join(cadical_dir, "configure")
        self._normalize_script_line_endings(cfg)
        st = os.stat(cfg).st_mode
        os.chmod(cfg, st | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        print('configure')
        self._bash(["sh", "./configure"], cwd=cadical_dir, env=env)
        def _materialize_cadical_sources(cadical_dir: str):
            if platform.system() != "Windows":
                return

            src = os.path.join(cadical_dir, "src")
            build = os.path.join(cadical_dir, "build")
            build_src = os.path.join(build, "src")

            # If build/src is missing (common on Windows symlink failure), copy it.
            if not os.path.isdir(build_src):
                shutil.copytree(src, build_src)

            # Extra sanity: ensure at least one expected file exists
            # (pick a file that exists in your cadical version)
            if not any(os.path.exists(os.path.join(build_src, fn)) for fn in ["cadical.cpp", "cadical.cc", "cadical.cxx"]):
                # fallback: copy again, but if this still fails, you need to list src dir
                shutil.rmtree(build_src, ignore_errors=True)
                shutil.copytree(src, build_src)
        print('materialize')
        _materialize_cadical_sources(cadical_dir)
        print('cadical -j')
        # self._make(["cadical", "-j"], cwd=cadical_dir, env=env)
        build_dir = os.path.join(cadical_dir, "build")
        self._make(["-j", "libcadical.a"], cwd=build_dir, env=env)

        cadical_a = os.path.join(cadical_dir, "build", "libcadical.a")
        self._ranlib(cadical_a, env=env)
        self._macos_rebuild_archive_if_gnu(cadical_a)
        if os.path.exists(os.path.join(uwr_dir, "config.mk")):
            os.remove(os.path.join(uwr_dir, "config.mk"))
        print('cp')
        self._bash(["cp", "config.cadical", "config.mk"], cwd=uwr_dir, env=env)
        env_uwr = env.copy()
        env_uwr["MAXPRE"] = ""
        env_uwr["USESCIP"] = "" 
        print('make clean')
        self._make(["clean"], cwd=uwr_dir, env=env_uwr)
        # print('make r')
        self._make(["build/release/lib/libuwrmaxsat.a", "-j", "LDFLAG_STATIC="], cwd=uwr_dir, env=env_uwr)
        uwr_a = os.path.join(uwr_dir, "build", "release", "lib", "libuwrmaxsat.a")
        print ('ranlib')
        self._ranlib(uwr_a, env=env_uwr)
        self._macos_rebuild_archive_if_gnu(uwr_a)
        cmake_args = [f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}", f"-DPython3_EXECUTABLE={sys.executable}", f"-DPython3_ROOT_DIR={sys.exec_prefix}", f"-Dpybind11_DIR={pybind11.get_cmake_dir()}", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DPYBIND11_FINDPYTHON=ON", "-DCMAKE_BUILD_TYPE=Release", f"-DUWR_LIB_ABS={uwr_a}", f"-DCADICAL_A_ABS={cadical_a}", f"-DCOMINISATPS_A_ABS={cominisatps_a}", "-DCMAKE_C_STANDARD=11", "-DCMAKE_CXX_STANDARD=17", f"-DCMAKE_CXX_FLAGS={env.get('CXXFLAGS','')}", f"-DCMAKE_C_FLAGS={env.get('CFLAGS','')}"]


        # project_root = 'C:\\Users\\joshs\\Desktop\\'
        # log_dir = os.path.join(project_root, "_cibw_logs")
        # os.makedirs(log_dir, exist_ok=True)

        # cfg_log   = os.path.join(log_dir, f"cmake_config_{abi_tag}.log")
        # build_log = os.path.join(log_dir, f"cmake_build_{abi_tag}.log")
        
        print('cmake1')
        subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=build_temp_path, env=env)
        print('cmake2')
        subprocess.check_call(["cmake", "--build", ".", "--verbose"], cwd=build_temp_path, env=env)
        self.verify_abi(ext, extdir, abi_tag)

    def build_urmaxsat_comp(self, ext):
        import urllib.request, zipfile
        abi_tag = sysconfig.get_config_var("SOABI") or f"cp{sys.version_info.major}{sys.version_info.minor}"
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        build_temp_path = os.path.join(self.build_temp, f"build_{ext.name}_{abi_tag}")
        os.makedirs(build_temp_path, exist_ok=True)
        env = self.get_base_env()
        env = self._darwin_make_env(env)
        uwr_dir = os.path.abspath(ext.sourcedir)
        cominisatps_dir = os.path.join(uwr_dir, "cominisatps")
        cominisatps_simp_dir = os.path.join(cominisatps_dir, "simp")

        if not os.path.exists(cominisatps_dir):
            url = "https://github.com/satcompetition/2016/raw/refs/heads/main/solvers/main/COMiniSatPSChandrasekharDRUP.zip"
            zip_path = os.path.join(uwr_dir, "cominisatps.zip")
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(uwr_dir)
            os.remove(zip_path)
            src_extracted = os.path.join(uwr_dir, "COMiniSatPS Chandrasekhar DRUP", "cominisatps")
            if os.path.exists(src_extracted):
                shutil.move(src_extracted, cominisatps_dir)
                shutil.rmtree(os.path.join(uwr_dir, "COMiniSatPS Chandrasekhar DRUP"))
            patch_file = os.path.join(uwr_dir, "cominisatps.patch")
            if os.path.exists(patch_file):
                self._bash(["patch", "-p1", "-N", "-r", "-", "-i", patch_file], cwd=cominisatps_dir, env=env)
            hdr = os.path.join(cominisatps_dir, "minisat", "mtl", "Vec.h")
            if not os.path.exists(hdr):
                raise RuntimeError(f"Missing header: {hdr}")

        env_sat = env.copy()
        env_sat["MROOT"] = ".."
        if "CFLAGS" in env_sat and "-std=gnu11" in env_sat["CFLAGS"]:
            env_sat["CFLAGS"] = env_sat["CFLAGS"].replace("-std=gnu11", "")

        try:
            self._bash(["bash", "-lc", "echo PATH=$PATH; which g++; g++ -dumpmachine; g++ --version | head -n 2"], cwd=cominisatps_simp_dir, env=env_sat)
            self._bash(
                ["bash", "-lc", "rm -f -- *.or lib_release.a lib.a depend.mk 2>/dev/null || true"],
                cwd=cominisatps_simp_dir,
                env=env_sat
            )

            self._make(["clean"], cwd=cominisatps_simp_dir, env=env_sat)
            self._make(["libr"], cwd=cominisatps_simp_dir, env=env_sat)
        except Exception as e:
            print(e)
            raise
        cominisatps_a = os.path.join(cominisatps_simp_dir, "lib_release.a")
        self._ranlib(cominisatps_a, env=env_sat)
        # Critical: must happen BEFORE CMake tries to link this archive.
        self._macos_rebuild_archive_if_gnu(cominisatps_a)
        def posix(p): return p.replace("\\", "/")

        with open(os.path.join(uwr_dir, "config.mk"), "w") as f:
            f.write("BUILD_DIR=build\nMAXPRE=\nUSESCIP=\nBIGWEIGHTS=\n")
            f.write(f"MINISATP_REL={env.get('CXXFLAGS','-std=gnu++17')} -O3 -D NDEBUG -Wno-strict-aliasing -D COMINISATPS -U_ISOC23_SOURCE -D_DEFAULT_SOURCE -D_GNU_SOURCE\n")
            f.write("MINISATP_FPIC=-fPIC\n")

            # IMPORTANT: include root must contain "minisat/..."
            f.write(
                "MINISAT_INCLUDE="
                f"-I{posix(cominisatps_dir)} "
                f"-I{posix(os.path.join(cominisatps_dir,'minisat'))} "
                f"-I{posix(os.path.join(uwr_dir,'cadical','src'))}\n"
            )

            # cominisatps/simp contains lib_release.a
            f.write(f"MINISAT_LIB=-L{posix(cominisatps_simp_dir)} -l_release\n")

        self._make(["clean"], cwd=uwr_dir, env=env)
        self._bash(["pwd"], cwd=uwr_dir, env=env)
        self._bash(["cat", "config.mk"], cwd=uwr_dir, env=env)
        self._bash(["ls", "-la", "cominisatps"], cwd=uwr_dir, env=env)
        self._bash(["ls", "-la", "cominisatps/minisat"], cwd=uwr_dir, env=env)
        self._bash(["file", "cominisatps/minisat"], cwd=uwr_dir, env=env)  # MSYS2 has `file`
        def materialize_minisat_tree(cominisatps_dir: str):
            if platform.system() != "Windows":
                return
            minisat_root = os.path.join(cominisatps_dir, "minisat")
            if not os.path.isdir(minisat_root):
                raise RuntimeError(f"Expected directory: {minisat_root}")

            for name in ["core", "mtl", "simp", "utils"]:
                src = os.path.join(cominisatps_dir, name)
                dst = os.path.join(minisat_root, name)

                if not os.path.isdir(src):
                    raise RuntimeError(f"Missing expected source dir: {src}")

                # If dst is a file (zip-flattened symlink), remove it.
                if os.path.exists(dst) and not os.path.isdir(dst):
                    os.remove(dst)

                # If dst is missing, create it by copying the real directory.
                if not os.path.isdir(dst):
                    shutil.copytree(src, dst)

        materialize_minisat_tree(cominisatps_dir)
    

        self._make(["lr", "-j", "LDFLAG_STATIC="], cwd=uwr_dir, env=env)
        uwr_a = os.path.join(uwr_dir, "build", "release", "lib", "libuwrmaxsat.a")
        self._ranlib(uwr_a, env=env)
        self._macos_rebuild_archive_if_gnu(uwr_a)
        cmake_args = [f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}", f"-DPython3_EXECUTABLE={sys.executable}", f"-DPython3_ROOT_DIR={sys.exec_prefix}", f"-Dpybind11_DIR={pybind11.get_cmake_dir()}", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DPYBIND11_FINDPYTHON=ON", "-DCMAKE_BUILD_TYPE=Release", f"-DUWR_LIB_ABS={uwr_a}", f"-DCOMINISATPS_A_ABS={cominisatps_a}", "-DCMAKE_C_STANDARD=11", "-DCMAKE_CXX_STANDARD=17", f"-DCMAKE_CXX_FLAGS={env.get('CXXFLAGS','')}", f"-DCMAKE_C_FLAGS={env.get('CFLAGS','')}"]
        # project_root = 'C:\\Users\\joshs\\Desktop\\'
        # log_dir = os.path.join(project_root, "_cibw_logs")
        # os.makedirs(log_dir, exist_ok=True)

        # cfg_log   = os.path.join(log_dir, f"cmake_config_{abi_tag}.log")
        # build_log = os.path.join(log_dir, f"cmake_build_{abi_tag}.log")

        # configure must run in build_temp_path
        try:
            subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=build_temp_path, env=env)

            # build must run in build_temp_path, not uwr_dir
            subprocess.check_call(["cmake", "--build", ".", "--verbose"], cwd=build_temp_path, env=env)
        except Exception as e:
            print(e)
            raise
        # subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=build_temp_path, env=env)
        # # subprocess.check_call(["cmake", "--build", ".", "-j"], cwd=build_temp_path, env=env)
        # # subprocess.check_call(["cmake", "--build", ".", "--verbose"], cwd=build_temp_path, env=env)
        # subprocess.check_call(
        #     ["cmake", "--build", ".", "--verbose"],
        #     cwd=build_temp_path,
        #     env=env,
        #     stdout=open(os.path.join(build_temp_path, "cmake_build.log"), "w", encoding="utf-8"),
        #     stderr=subprocess.STDOUT,
        # )


        self.verify_abi(ext, extdir, abi_tag)

    def build_urmaxsat(self, ext):
        abi_tag = sysconfig.get_config_var("SOABI") or f"cp{sys.version_info.major}{sys.version_info.minor}"
        ext_fullpath = self.get_ext_fullpath(ext.name)
        extdir = os.path.abspath(os.path.dirname(ext_fullpath))
        build_temp_path = os.path.join(self.build_temp, f"build_{ext.name}_{abi_tag}")
        os.makedirs(build_temp_path, exist_ok=True)
        env = self.get_base_env()
        source_root = os.path.abspath(ext.sourcedir)
        cadical_dir = os.path.join(source_root, "cadical")
        uwr_dir = os.path.join(source_root, "uwrmaxsat")
        if os.path.exists(os.path.join(cadical_dir, "Makefile")):
            self._make(["clean"], cwd=cadical_dir, env=env)
        self._normalize_script_line_endings(os.path.join(cadical_dir, "configure"))
        self._bash(["sh", "./configure"], cwd=cadical_dir, env=env)

        self._make(["cadical", "-j"], cwd=cadical_dir, env=env)
        cadical_a = os.path.join(cadical_dir, "build", "libcadical.a")
        self._ranlib(cadical_a, env=env)
        self._bash(["cp", "config.cadical", "config.mk"], cwd=uwr_dir, env=env)
        env2 = env.copy()
        env2["MAXPRE"] = ""
        env2["USESCIP"] = "" 

        self._make(["clean"], cwd=uwr_dir, env=env2)
        self._bash(["pwd"], cwd=uwr_dir, env=env2)
        self._bash(["ls", "-la"], cwd=uwr_dir, env=env2)

        # Show what Make thinks the key vars are
        # self._bash(["make", "-pn"], cwd=uwr_dir, env=env2)

        # Targeted grep (less spam)
        # subprocess.check_call([r"mingw32-make -pn | egrep '^(CXX|CXXFLAGS|MINISAT_INCLUDE|includedir|prefix)[[:space:]]*[:?]?='"], cwd=uwr_dir, env=env2)
        self._make(["r", "-j", "LDFLAG_STATIC="], cwd=uwr_dir, env=env2)
        uwr_a = os.path.join(uwr_dir, "build", "release", "lib", "libuwrmaxsat.a")
        self._ranlib(uwr_a, env=env2)
        cmake_args = [f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}", f"-DPython3_EXECUTABLE={sys.executable}", f"-DPython3_ROOT_DIR={sys.exec_prefix}", f"-Dpybind11_DIR={pybind11.get_cmake_dir()}", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DPYBIND11_FINDPYTHON=ON", "-DCMAKE_BUILD_TYPE=Release", f"-DUWR_LIB_ABS={uwr_a}", f"-DCADICAL_A_ABS={cadical_a}", "-DCMAKE_C_STANDARD=11", "-DCMAKE_CXX_STANDARD=17", f"-DCMAKE_CXX_FLAGS={env.get('CXXFLAGS','')}", f"-DCMAKE_C_FLAGS={env.get('CFLAGS','')}"]
        self._bash(["cmake", ext.sourcedir] + cmake_args, cwd=build_temp_path, env=env)
        self._bash(["cmake", "--build", ".", "-j"], cwd=build_temp_path, env=env)
        self.verify_abi(ext, extdir, abi_tag)

ROOT = Path(__file__).resolve().parent
README_TEXT = (ROOT / "README.md").read_text(encoding="utf-8")
PBLIB_ROOT_DIR = os.path.join("pblib", "pblib", "pblib")
PBLIB_ENC_DIR = os.path.join(PBLIB_ROOT_DIR, "encoder")
PBLIB_BINDINGS_DIR = os.path.join("pblib", "src")
PBLIB_SRCS = sorted(glob.glob(os.path.join(PBLIB_ROOT_DIR, "*.cpp")))
PBLIB_SRCS.extend(sorted(glob.glob(os.path.join(PBLIB_ENC_DIR, "*.cpp"))))
PBLIB_BINDING_SRCS = [os.path.join(PBLIB_BINDINGS_DIR, "pblib_capi.cpp"), *PBLIB_SRCS]


def _parse_csv_env(name: str) -> set[str]:
    raw = (os.environ.get(name, "") or "").strip()
    if not raw:
        return set()
    return {tok.strip() for tok in raw.split(",") if tok.strip()}


def _filter_solver_extensions(exts):
    include = _parse_csv_env("HERMAX_SOLVER_INCLUDE")
    if include and {tok.lower() for tok in include} <= {"none", "off", "null"}:
        print("HERMAX_SOLVER_INCLUDE active: (none)")
        return []
    if not include:
        return exts
    filtered = [e for e in exts if e.name in include]
    missing = sorted(include - {e.name for e in exts})
    if missing:
        print(f"HERMAX_SOLVER_INCLUDE ignored unknown names: {', '.join(missing)}")
    print("HERMAX_SOLVER_INCLUDE active:", ", ".join(e.name for e in filtered))
    return filtered


SOLVER_EXTENSIONS = _filter_solver_extensions([
    CMakeExtension('hermax.core.openwbo', sourcedir='open-wbo'),
    CMakeExtension('hermax.core.openwbo_inc', sourcedir='open-wbo-inc'),
    CMakeExtension('hermax.core.urmaxsat_py', sourcedir='urmaxsat-py'),
    CMakeExtension('hermax.core.urmaxsat_comp_py', sourcedir='urmaxsat-comp-py'),
    CMakeExtension('hermax.core.cashwmaxsat', sourcedir='cashwmaxsat-py'),
    CMakeExtension('hermax.core.evalmaxsat_latest', sourcedir='evalmaxsat-latest-py'),
    CMakeExtension('hermax.core.evalmaxsat_incr', sourcedir='evalmaxsat-incr-py'),
    CMakeExtension('hermax.core.wmaxcdcl', sourcedir='wmaxcdcl-py'),
    CMakeExtension('hermax.core.spb_maxsat_c_fps', sourcedir='spb-maxsat-c-fps-py'),
    CMakeExtension('hermax.core.nuwls_c_ibr', sourcedir='nuwls-c-ibr-py'),
    CMakeExtension('hermax.core.loandra', sourcedir='loandra-py'),
])


setup(
    name="hermax",
    version="1.0.0",
    author="Josep Maria Salvia Hornos",
    author_email="josh.salvia@gmail.com",
    description="A Python library of incremental MaxSAT solvers",
    long_description=README_TEXT,
    long_description_content_type="text/markdown",
    url="https://github.com/josalhor/hermax",
    project_urls={
        "Documentation": "https://hermax.readthedocs.io",
        "Repository": "https://github.com/josalhor/hermax",
        "Issues": "https://github.com/josalhor/hermax/issues",
    },
    license="Apache-2.0",
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Scientific/Engineering",
    ],
    packages=find_packages(include=["hermax", "hermax.*"]),
    ext_modules=[
        Extension(
            "hermax_pycard",
            ["cardenc/pycard.cc"],
            include_dirs=[
                "cardenc",
                *[
                    p
                    for p in [
                        sysconfig.get_paths().get("include"),
                        sysconfig.get_paths().get("platinclude"),
                    ]
                    if p
                ],
            ],
            extra_compile_args=(
                (["/O2", "/std:c++17"] if platform.system() == "Windows" else ["-O3", "-Wall", "-std=c++17", "-DNDEBUG"])
                + [f"-DHERMAX_PYCARD_ENABLE_PYINT_CACHE={1 if os.environ.get('HERMAX_PYCARD_PYINT_CACHE', '1') == '1' else 0}"]
            ),
            language="c++",
        ),
        Extension(
            "hermax.internal._pblib",
            PBLIB_BINDING_SRCS,
            include_dirs=[
                PBLIB_ROOT_DIR,
                PBLIB_ENC_DIR,
                PBLIB_BINDINGS_DIR,
                *[
                    p
                    for p in [
                        sysconfig.get_paths().get("include"),
                        sysconfig.get_paths().get("platinclude"),
                    ]
                    if p
                ],
            ],
            extra_compile_args=(
                ([ "/O2", "/std:c++17"] if platform.system() == "Windows"
                 else ["-O3", "-Wall", "-std=c++17", "-DNDEBUG"])
                + [f"-DHERMAX_PBLIB_ENABLE_PYINT_CACHE={1 if os.environ.get('HERMAX_PBLIB_PYINT_CACHE', '1') == '1' else 0}"]
            ),
            language="c++",
        ),
        *SOLVER_EXTENSIONS,
    ],
    cmdclass={'build_ext': CMakeBuildURMaxSAT},
    include_package_data=False,
    exclude_package_data={"": ["*.pyc", "__pycache__/*"]},
    zip_safe=False,
    install_requires=['python-sat'],
    extras_require={
        "optilog": ["optilog==0.6.1"],
    },
)
