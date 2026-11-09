cmake_minimum_required(VERSION 3.15)
project(hermax.core.imaxhs_py LANGUAGES CXX)

# --------------------------------------------------------
# Python C API
# --------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter REQUIRED)
find_package(Python3 COMPONENTS Development.Module REQUIRED)

# --------------------------------------------------------
# Paths injected from setup.py
# --------------------------------------------------------
set(IMAXHS_LIB_ABS "" CACHE FILEPATH "Absolute path to prebuilt libipamirmaxhs.a")
set(CPLEX_LIB_DIR  "" CACHE PATH "Path to CPLEX library directory")

if (NOT EXISTS "${IMAXHS_LIB_ABS}")
  message(FATAL_ERROR "IMAXHS_LIB_ABS not set/does not exist")
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

# Fallback to static if shared/import library not found
if (NOT CPLEX_LIB AND CPLEX_LIB_DIR)
  find_library(CPLEX_LIB NAMES libcplex.a cplex2212.a cplex.a PATHS "${CPLEX_LIB_DIR}")
endif()

if (NOT CPLEX_LIB)
  message(FATAL_ERROR "CPLEX library not found. Set CPLEX_LIB_DIR or ensure it is in system paths.")
endif()

message(STATUS "Found CPLEX: ${CPLEX_LIB}")

find_library(M_LIB m)

# Build Python C API module
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(hermax.core.imaxhs_py MODULE python/imaxhs_bindings.cpp)
set_target_properties(hermax.core.imaxhs_py PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_link_libraries(hermax.core.imaxhs_py PRIVATE Python3::Module)
target_compile_definitions(hermax.core.imaxhs_py PRIVATE IL_STD)

target_link_libraries(hermax.core.imaxhs_py PRIVATE
  "${IMAXHS_LIB_ABS}"
  "${CPLEX_LIB}"
  ZLIB::ZLIB
  "${M_LIB}"
  pthread
  dl
)

# --------------------------------------------------------
# Output
# --------------------------------------------------------
set_target_properties(hermax.core.imaxhs_py PROPERTIES
  OUTPUT_NAME "imaxhs_py"
  PREFIX ""
)
