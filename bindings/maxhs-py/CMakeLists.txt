cmake_minimum_required(VERSION 3.15)
project(hermax.core.maxhs_py LANGUAGES CXX)

# --------------------------------------------------------
# pybind11 + Python
# --------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter REQUIRED)
find_package(Python3 COMPONENTS Development QUIET)

set(PYBIND11_FINDPYTHON ON)

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -m pybind11 --cmakedir
  OUTPUT_VARIABLE _pybind11_dir OUTPUT_STRIP_TRAILING_WHITESPACE
)
if (EXISTS "${_pybind11_dir}/pybind11Config.cmake")
  list(APPEND CMAKE_PREFIX_PATH "${_pybind11_dir}")
  find_package(pybind11 REQUIRED)
endif()
if (NOT pybind11_FOUND)
  include(FetchContent)
  FetchContent_Declare(pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.12.0
  )
  FetchContent_MakeAvailable(pybind11)
endif()

# --------------------------------------------------------
# Paths injected from setup.py
# --------------------------------------------------------
set(MAXHS_LIB_ABS "" CACHE FILEPATH "Absolute path to prebuilt libmaxhs.a")
set(CPLEX_LIB_DIR  "" CACHE PATH "Path to CPLEX library directory")
set(MAXHS_INC_DIR "" CACHE PATH "Path to MaxHS source directory")

if (NOT EXISTS "${MAXHS_LIB_ABS}")
  message(FATAL_ERROR "MAXHS_LIB_ABS not set/does not exist")
endif()

# --------------------------------------------------------
# Build settings
# --------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# --------------------------------------------------------
# Link static/shared libs
# --------------------------------------------------------
find_package(ZLIB REQUIRED)

# Try to find CPLEX shared library specifically for dynamic linking
if (CPLEX_LIB_DIR)
  find_library(CPLEX_LIB 
    NAMES libcplex2212.so libcplex.so libcplex2212.dylib libcplex.dylib cplex2212 cplex cplex2212.lib cplex.lib
    PATHS "${CPLEX_LIB_DIR}" 
    NO_DEFAULT_PATH
  )
endif()

# Fallback to system search
if (NOT CPLEX_LIB)
  find_library(CPLEX_LIB NAMES libcplex2212.so libcplex.so libcplex2212.dylib libcplex.dylib cplex2212 cplex cplex2212.lib cplex.lib)
endif()

# Fallback to static if shared not found (not ideal for python extensions but maybe needed)
if (NOT CPLEX_LIB AND CPLEX_LIB_DIR)
  find_library(CPLEX_LIB NAMES libcplex.a PATHS "${CPLEX_LIB_DIR}")
endif()

if (NOT CPLEX_LIB)
  message(FATAL_ERROR "CPLEX library not found. Set CPLEX_LIB_DIR or ensure it is in system paths.")
endif()

message(STATUS "Found CPLEX: ${CPLEX_LIB}")

find_library(M_LIB m)

# Build pybind module
pybind11_add_module(hermax.core.maxhs_py python/maxhs_bindings.cpp)
target_compile_definitions(hermax.core.maxhs_py PRIVATE IL_STD)

# MaxHS headers
target_include_directories(hermax.core.maxhs_py PRIVATE "${MAXHS_INC_DIR}")

target_link_libraries(hermax.core.maxhs_py PRIVATE
  "${MAXHS_LIB_ABS}"
  "${CPLEX_LIB}"
  ZLIB::ZLIB
  "${M_LIB}"
  pthread
  dl
)

# --------------------------------------------------------
# Output
# --------------------------------------------------------
set_target_properties(hermax.core.maxhs_py PROPERTIES
  OUTPUT_NAME "maxhs_py"
)
