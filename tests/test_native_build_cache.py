"""Exercise setup.py's cache policy without running package setup or compilers."""
import ast
from pathlib import Path

import pytest


@pytest.fixture
def builder():
    setup_path = Path(__file__).resolve().parents[1] / "setup.py"
    if not setup_path.exists():
        pytest.skip("Build source is unavailable in installed-wheel tests")
    tree = ast.parse(setup_path.read_text())
    tree.body = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                 or isinstance(node, ast.ClassDef) and node.name == "CMakeBuild"]
    namespace = {}
    exec(compile(tree, str(setup_path), "exec"), namespace)
    return namespace["CMakeBuild"].__new__(namespace["CMakeBuild"])


def test_cache_is_automatic_only_for_wheel_jobs(builder, monkeypatch):
    monkeypatch.delenv("HERMAX_REUSE_NATIVE_CORES", raising=False)
    monkeypatch.delenv("CIBUILDWHEEL", raising=False)
    assert not builder._native_core_reuse_enabled()
    monkeypatch.setenv("CIBUILDWHEEL", "1")
    assert builder._native_core_reuse_enabled()
    monkeypatch.setenv("HERMAX_REUSE_NATIVE_CORES", "0")
    assert not builder._native_core_reuse_enabled()


def test_source_fingerprint_tracks_content_not_timestamps_or_objects(builder, tmp_path):
    source = tmp_path / "solver.cc"
    source.write_text("int value = 1;\n")
    fingerprint = lambda: builder._native_source_fingerprint([tmp_path])
    original = fingerprint()
    source.touch()
    for name in ("solver.o", "solver.oh.d", "libsolver.a", "depend.mk"):
        (tmp_path / name).write_text("generated output")
    assert fingerprint() == original
    source.write_text("int value = 2;\n")
    assert fingerprint() != original


def test_cached_archive_is_invalidated_by_source_changes(builder, tmp_path, monkeypatch):
    monkeypatch.setenv("CIBUILDWHEEL", "1")
    monkeypatch.delenv("HERMAX_REUSE_NATIVE_CORES", raising=False)
    source = tmp_path / "src"
    source.mkdir()
    (source / "solver.cc").write_text("int value = 1;")
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(builder, "_native_core_cache_dir", lambda env: cache)
    archive = cache / "solver.a"
    archive.write_bytes(b"archive")
    builder._mark_native_core("solver", [str(archive)], {}, [source])
    assert builder._load_cached_native_core("solver", {}, [source]) == [str(archive)]
    (source / "solver.cc").write_text("int value = 2;")
    assert builder._load_cached_native_core("solver", {}, [source]) is None


@pytest.mark.parametrize("compiler_type", ["unix", "msvc"])
def test_regular_extensions_keep_abi_objects_and_toolchains_separate(builder, monkeypatch, tmp_path, compiler_type):
    from types import SimpleNamespace
    from setuptools.command.build_ext import build_ext

    calls = []
    original_spawn = lambda cmd, **kwargs: calls.append((cmd, kwargs))
    builder.compiler = SimpleNamespace(compiler_type=compiler_type, spawn=original_spawn)
    builder.build_temp = str(tmp_path)
    builder.debug = False
    ext = SimpleNamespace(name="probe", extra_compile_args=[])
    monkeypatch.setattr(builder, "get_base_env", lambda: {"CC": "/cache/cc", "CXX": "/cache/cxx"})
    directories = []

    def compile_extension(command, extension):
        directories.append(command.build_temp)
        command.compiler.spawn(["original-cxx", "-c", "probe.cpp"])
        command.compiler.spawn(["original-linker", "-shared", "probe.o"])

    monkeypatch.setattr(build_ext, "build_extension", compile_extension)
    config = builder._build_regular_extension.__globals__["sysconfig"]
    monkeypatch.setattr(config, "get_config_var", lambda name: "cpython-310-test")
    builder._build_regular_extension(ext)
    monkeypatch.setattr(config, "get_config_var", lambda name: "cpython-311-test")
    builder._build_regular_extension(ext)
    assert directories == [str(tmp_path / "cpython-310-test"),
                           str(tmp_path / "cpython-311-test")]
    assert calls[0][0][0] == ("/cache/cxx" if compiler_type == "unix" else "original-cxx")
    assert calls[1][0][0] == "original-linker"
    assert builder.build_temp == str(tmp_path)
    assert builder.compiler.spawn is original_spawn


def test_regular_extension_restores_state_after_compile_failure(builder, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from setuptools.command.build_ext import build_ext

    original_spawn = lambda *args, **kwargs: None
    builder.compiler = SimpleNamespace(compiler_type="unix", spawn=original_spawn)
    builder.build_temp = str(tmp_path)
    builder.debug = True
    args = ["-O3"]
    ext = SimpleNamespace(name="hermax.internal._clauses", extra_compile_args=args)
    monkeypatch.setattr(builder, "get_base_env", lambda: {})

    def fail(*args):
        raise RuntimeError("compile failed")

    monkeypatch.setattr(build_ext, "build_extension", fail)
    with pytest.raises(RuntimeError, match="compile failed"):
        builder._build_regular_extension(ext)
    assert builder.compiler.spawn is original_spawn
    assert builder.build_temp == str(tmp_path)
    assert ext.extra_compile_args is args


def test_source_fingerprint_ignores_dangling_build_links(builder, tmp_path):
    (tmp_path / "solver.cc").write_text("int value = 1;")
    expected = builder._native_source_fingerprint([tmp_path])
    try:
        (tmp_path / "makefile").symlink_to(tmp_path / "old-checkout" / "makefile")
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is unavailable")
    assert builder._native_source_fingerprint([tmp_path]) == expected


def test_source_fingerprint_tracks_valid_symlink_content(builder, tmp_path):
    source = tmp_path / "solver.cc"
    source.write_text("int value = 1;")
    try:
        (tmp_path / "linked.cc").symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is unavailable")
    expected = builder._native_source_fingerprint([tmp_path])
    source.write_text("int value = 2;")
    assert builder._native_source_fingerprint([tmp_path]) != expected
