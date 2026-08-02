from setuptools import Extension, setup

base_compile_args = [
    "-O3",
    "-DNDEBUG",
    "-std=c++17",
    "-DGlucose=RC2Glucose",
    "-fvisibility=hidden",
    "-ffunction-sections",
    "-fdata-sections",
    "-fno-semantic-interposition",
    "-fomit-frame-pointer",
    "-ffp-contract=fast",
    "-flto=auto",
]
base_link_args = [
    "-Wl,--gc-sections",
    "-s",
    "-flto=auto",
]

compile_args = list(base_compile_args)
link_args = list(base_link_args)

ext = Extension(
    name="coretrail_native",
    sources=[
        "src/python/module.cc",
        "src/core/coretrail_solver.cc",
        "src/core/glucose_backend.cc",
        "third_party/glucose-syrup-4.1/core/Solver.cc",
        "third_party/glucose-syrup-4.1/utils/Options.cc",
        "third_party/glucose-syrup-4.1/utils/System.cc",
    ],
    include_dirs=[
        "include",
        "third_party/glucose-syrup-4.1",
        "third_party/cardenc",
    ],
    language="c++",
    extra_compile_args=compile_args,
    extra_link_args=link_args,
)

setup(
    name="coretrail",
    version="0.0.1",
    ext_modules=[ext],
    py_modules=["coretrail"],
    package_dir={"": "python"},
    zip_safe=False,
)
