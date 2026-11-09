cmake_minimum_required(VERSION 3.15)
project(hermax.core.maxhs_py LANGUAGES CXX)

# --------------------------------------------------------
# Python C API
# --------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter REQUIRED)
find_package(Python3 COMPONENTS Development.Module REQUIRED)

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

# Build Python C API module
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(hermax.core.maxhs_py MODULE python/maxhs_bindings.cpp)
set_target_properties(hermax.core.maxhs_py PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_link_libraries(hermax.core.maxhs_py PRIVATE Python3::Module)
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
  PREFIX ""
)
